"""Transactional, idempotent acquisition. Original payloads and operator corrections survive updates."""
import hashlib
import json
from datetime import datetime,timedelta
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func
from ..models import User
from ..order_models import Order,OrderSource,OrderImportRun,OrderItem,RouteOrderAssignment
from .orders import project,record,touch,EDITABLE
from .order_customers import auto_link,recognize
from .order_files import mapped,FIELDS


class ImportIssue(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def source(db,uid,sid,lock=False):
    if lock: db.query(User).filter_by(id=uid).with_for_update().one()
    query=db.query(OrderSource).filter_by(user_id=uid,id=sid)
    if lock: query=query.with_for_update().populate_existing()
    row=query.first()
    if row is None or row.kind not in ('file','api'): raise HTTPException(404,'Fonte non trovata.')
    return row


def run(db,uid,sid,rid):
    row=db.query(OrderImportRun).filter_by(user_id=uid,source_id=sid,id=rid).with_for_update().populate_existing().first()
    if row is None: raise HTTPException(404,'Importazione non trovata.')
    return row


def public_source(db,row):
    recent=db.query(OrderImportRun).filter_by(source_id=row.id).order_by(OrderImportRun.id.desc()).first()
    success=db.query(func.max(OrderImportRun.created_at)).filter_by(source_id=row.id,status='completed').scalar()
    return {'id':row.id,'name':row.name,'kind':row.kind,'status':row.status,'version':row.version,
            'software':row.configuration.get('software',''),'mapping':row.configuration.get('mapping',{}),
            'has_credential':bool(row.credential_hash),'last_success':success,
            'order_count':db.query(Order).filter_by(user_id=row.user_id,source_id=row.id).count(),
            'last_run':{'id':recent.id,'status':recent.status,'summary':{k:v for k,v in recent.report.items() if k!='rows'}} if recent else None}


def public_run(row,offset=0):
    report=dict(row.report);rows=report.pop('rows',[])
    return {'id':row.id,'status':row.status,'created_at':row.created_at,'expires_at':row.expires_at,
            'report':report,'rows':rows[offset:offset+100],'offset':offset,'has_more':offset+100<len(rows)}


def stage(db,src,headers,rows):
    if src.status not in ('draft','active'): raise HTTPException(409,'La fonte è in pausa o rimossa.')
    now=datetime.utcnow()
    db.query(OrderImportRun).filter(OrderImportRun.user_id==src.user_id,OrderImportRun.expires_at<now,OrderImportRun.payload.isnot(None)).update({OrderImportRun.payload:None},synchronize_session=False)
    item=OrderImportRun(user_id=src.user_id,source_id=src.id,status='uploaded',payload={'headers':headers,'rows':rows},
                        report={'total':len(rows)},expires_at=now+timedelta(hours=24),source_version=src.version)
    db.add(item);db.flush();return item


def check_payload(item):
    if not item.payload or not item.expires_at or item.expires_at<datetime.utcnow():
        raise HTTPException(410,'Anteprima scaduta: carica nuovamente il file o il campione.')


def preflight(db,src,rows,mapping,expected=None):
    report={'total':len(rows),'new':0,'updated':0,'unchanged':0,'invalid':0,'unmatched':0,'rows':[]}
    parsed=[];seen=set()
    for index,raw in enumerate(rows,1):
        entry={'row':index};data=None
        try:
            if src.kind=='api' and not set(raw)<=set(FIELDS)|set(mapping.values()):
                raise ImportIssue('Campi API non riconosciuti: usa il formato standard o completa le associazioni della fonte.')
            data=mapped(raw,mapping)
            eid=data['external_id'];entry['external_id']=eid
            if eid in seen: raise ImportIssue('Identificativo ordine ripetuto nello stesso invio.')
            seen.add(eid)
            existing=db.query(Order).filter_by(user_id=src.user_id,source_id=src.id,external_id=eid).with_for_update().populate_existing().first()
            entry['version']=existing.version if existing else 0
            if expected is not None and expected.get(eid)!=entry['version']:
                raise ImportIssue('Ordine cambiato dopo l’anteprima: ripeti la verifica prima di importare.')
            if existing and existing.ingested_payload==data:
                action='unchanged'
            elif existing:
                if existing.status not in EDITABLE or db.query(RouteOrderAssignment.id).filter_by(order_id=existing.id).first():
                    raise ImportIssue('Ordine già assegnato, avviato, chiuso o annullato: aggiornamento bloccato.')
                action='updated'
            else: action='new'
            probe=Order(user_id=src.user_id,source_id=src.id,external_customer_id=data.get('external_customer_id'),
                        recipient_name=data.get('recipient_name'),delivery_address=data.get('delivery_address'),customer_resolution='pending')
            match=recognize(db,probe)['kind'];entry['customer_match']=match
            if match not in ('certain','linked'): report['unmatched']+=1
            entry['warnings']=[label for key,label in [('recipient_name','Destinatario mancante'),('delivery_address','Indirizzo mancante'),('weight_kg','Peso non indicato')] if data.get(key) is None or data.get(key)=='']
            entry['action']=action;report[action]+=1
        except ImportIssue as exc:
            entry['error']=str(exc)
        except ValidationError as exc:
            entry['error']='; '.join(f"{'.'.join(map(str,e['loc']))}: formato o valore non valido" for e in exc.errors(include_input=False,include_url=False))[:1000]
        except (ValueError,TypeError,OverflowError):
            entry['error']='Controlla identificativi univoci, formati, date e valori; gli ordini già assegnati o modificati dopo l’anteprima richiedono una nuova verifica.'
        if 'error' in entry: report['invalid']+=1
        report['rows'].append(entry);parsed.append(data)
    return report,parsed


def preview(db,src,item):
    check_payload(item)
    if src.status not in ('draft','active'): raise HTTPException(409,'La fonte è in pausa o rimossa.')
    mapping=src.configuration.get('mapping',{})
    if not {'external_id','number'}<=mapping.keys(): raise HTTPException(422,'Associa identificativo esterno e numero ordine.')
    if not set(mapping.values())<=set(item.payload['headers']): raise HTTPException(422,'Le colonne del file non corrispondono alla configurazione. Correggi le associazioni.')
    effective_mapping={**{key:key for key in FIELDS},**mapping} if src.kind=='api' else mapping
    report,parsed=preflight(db,src,item.payload['rows'],effective_mapping)
    item.report=report;item.status='preview_invalid' if report['invalid'] else 'preview_ready'
    item.source_version=src.version;item.payload_hash=digest(parsed)
    db.flush();return item


def apply_orders(db,src,parsed,actor,report):
    for data,entry in zip(parsed,report['rows']):
        if entry['action']=='unchanged': continue
        values={k:v for k,v in data.items() if k not in ('external_id','external_customer_id','items')}
        order=db.query(Order).filter_by(user_id=src.user_id,source_id=src.id,external_id=data['external_id']).first()
        if order is None:
            order=Order(user_id=src.user_id,source_id=src.id,external_id=data['external_id'],external_customer_id=data.get('external_customer_id'),
                        number=data['number'],original_payload=data,ingested_payload=data,operational_data={},status='da_verificare')
            project(order,values);db.add(order);db.flush()
            record(db,order,actor,'received',{'source_id':src.id})
        else:
            previous=order.ingested_payload or order.original_payload
            operative=dict(order.operational_data);preserved=[]
            for key,value in values.items():
                if operative.get(key)==previous.get(key): operative[key]=value
                else: preserved.append(key)
            old_address=order.delivery_address
            old_identity=(order.recipient_name,order.external_customer_id)
            project(order,operative)
            order.external_customer_id=data.get('external_customer_id')
            if old_address!=order.delivery_address: order.address_verification=None
            if order.customer_resolution=='automatic' and (old_address!=order.delivery_address or old_identity!=(order.recipient_name,order.external_customer_id)):
                order.customer_id=None;order.customer_resolution='pending'
            order.ingested_payload=data;order.status='da_verificare';order.verification_status='pending';touch(order)
            record(db,order,actor,'source_updated',{'source_id':src.id,'received':data,'preserved_corrections':preserved})
            db.query(OrderItem).filter_by(order_id=order.id).delete(synchronize_session=False)
        for index,line in enumerate(data['items'],1): db.add(OrderItem(order_id=order.id,line_number=index,data=line))
        auto_link(db,order,actor)
    db.flush()


def execute(db,src,item,rows,mapping,actor,expected=None):
    report,parsed=preflight(db,src,rows,mapping,expected)
    if report['invalid']:
        item.status='failed';item.report=report;return item
    try:
        with db.begin_nested(): apply_orders(db,src,parsed,actor,report)
    except Exception:
        # No payload/credentials in the error report; savepoint rolls back every order.
        report={'total':len(rows),'invalid':len(rows),'new':0,'updated':0,'unchanged':0,'error':'Importazione annullata per un errore interno. Nessun ordine modificato. Riprova con una nuova richiesta.'}
        item.status='failed';item.report=report;return item
    item.status='completed';item.report=report;item.payload=None
    return item


def commit_file(db,src,item,actor):
    if src.status!='active': raise HTTPException(409,'Attiva la fonte prima di importare.')
    if src.kind!='file': raise HTTPException(422,'I campioni API servono alla verifica e non vengono importati dalla pagina.')
    if item.status=='completed': return item
    check_payload(item)
    if item.status!='preview_ready' or item.source_version!=src.version: raise HTTPException(409,'Configurazione cambiata o anteprima non valida: ripeti la verifica.')
    expected={r['external_id']:r['version'] for r in item.report['rows']}
    return execute(db,src,item,item.payload['rows'],src.configuration['mapping'],actor,expected)


def acquire(db,src,data):
    key='api:'+data.batch_id;fingerprint=digest(data.orders)
    previous=db.query(OrderImportRun).filter_by(source_id=src.id,idempotency_key=key).first()
    if previous and not data.dry_run:
        if previous.payload_hash!=fingerprint: raise HTTPException(409,'batch_id già usato con dati diversi. Usa una nuova chiave.')
        return previous
    mapping={**{key:key for key in FIELDS},**src.configuration.get('mapping',{})}
    report,parsed=preflight(db,src,data.orders,mapping)
    item=OrderImportRun(user_id=src.user_id,source_id=src.id,status='preview_invalid' if report['invalid'] else 'preview_ready',
                        idempotency_key=None if data.dry_run else key,payload_hash=fingerprint,report=report)
    db.add(item);db.flush()
    if not data.dry_run: execute(db,src,item,data.orders,mapping,'source:'+str(src.id))
    return item
