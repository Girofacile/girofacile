"""Company-owned connectors and authenticated provider deliveries."""
import hashlib
import json
import re
import secrets
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session
from ..core.dependencies import current_user
from ..database import get_db
from ..models import User
from ..order_models import OrderSource, OrderImportRun
from ..schemas.order_sources import Acquisition, MAX_BYTES
from ..services import order_ingestion as service
from ..services import order_connectors as adapter
from ..services.order_source_security import throttle_ip

router = APIRouter(tags=['order-connectors'])


class ConnectorCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=160)
    provider: Literal['email','shopify','woocommerce']
    store: str = Field(default='',max_length=253)
    secret: str = Field(default='',max_length=500)


@router.post('/api/order-sources/connectors',status_code=201)
def create(data:ConnectorCreate,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    if getattr(request.state,'company_collaborator',None):
        raise HTTPException(403,'Il titolare configura i collegamenti automatici.')
    if data.provider=='email':
        raise HTTPException(503, 'Inoltro email in fase di sviluppo: configurazione non ancora disponibile.')
    db.query(User).filter_by(id=user.id).with_for_update().one()
    if db.query(OrderSource).filter(OrderSource.user_id==user.id,OrderSource.kind.in_(('api','file'))).count()>=100:
        raise HTTPException(422,'Massimo 100 fonti per azienda.')
    key='c'+secrets.token_hex(12)
    config={'connector':data.provider,'software':data.provider,'mapping':{},'excluded_fields':['requested_date'], 'validated':True}
    store=data.store.lower().strip().removeprefix('https://').rstrip('/')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',store) or '.' not in store or '..' in store:
        raise HTTPException(422,'Indica il dominio del negozio, senza percorsi.')
    if data.provider=='shopify' and not store.endswith('.myshopify.com'):
        raise HTTPException(422,'Usa il dominio originale del negozio: nome.myshopify.com.')
    if len(data.secret)<16:
        raise HTTPException(422,'Inserisci la chiave di firma del collegamento (almeno 16 caratteri).')
    config.update(store=store,connector_secret=adapter.seal(data.secret))
    src=OrderSource(user_id=user.id,key=key,name=data.name,kind='api',status='active',configuration=config)
    db.add(src);db.commit()
    return service.public_source(db,src)


async def bounded_body(request):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>MAX_BYTES:
            raise HTTPException(413,'Messaggio oltre 2 MB.')
    return bytes(raw)


def locked_source(db,key):
    hint=db.query(OrderSource).filter_by(key=key).first()
    if hint is None:
        raise HTTPException(404,'Collegamento non trovato.')
    src=service.source(db,hint.user_id,hint.id,lock=True)
    if src.status!='active':
        raise HTTPException(503,'Collegamento in pausa.')
    from ..services.plans import require_active_plan
    require_active_plan(db.get(User,src.user_id))
    return src


def receive(db,src,body,event_id,raw,parse):
    fingerprint=hashlib.sha256(raw).hexdigest()
    key='connector:'+hashlib.sha256(event_id.encode()).hexdigest()
    previous=db.query(OrderImportRun).filter_by(source_id=src.id,idempotency_key=key).first()
    if previous:
        if previous.payload_hash!=fingerprint:
            raise HTTPException(409,'Evento gia ricevuto con contenuto diverso.')
        return {'received':True,'status':previous.status,'run_id':previous.id}
    item=OrderImportRun(user_id=src.user_id,source_id=src.id,idempotency_key=key,payload_hash=fingerprint,status='received',report={})
    db.add(item);db.flush()
    try:
        rows=parse(body)
        data=Acquisition(batch_id='connector',orders=rows)
        service.execute(db,src,item,data.orders,{k:k for k in adapter.FIELDS},'source:'+str(src.id))
    except (ValueError,TypeError,KeyError,AttributeError,HTTPException,ValidationError):
        item.status='failed'
        error='Ordine da verificare nel negozio: controlla identificativo, destinatario, indirizzo di spedizione e articoli.'
        if src.configuration['connector']=='email':
            error='Email da verificare nella casella originale. Usa CSV/Excel o righe Numero ordine: / Destinatario: / Indirizzo:. PDF e testo libero richiedono inserimento manuale.'
        item.report={'total':1,'invalid':1,'error':error}
    item.report={**item.report,'provider_event':event_id[:500]}
    if src.configuration['connector']=='email':
        item.report={**item.report,'email_subject':str(body.get('Subject',''))[:200]}
    src.configuration={**src.configuration,'connector_received':True}
    db.commit()
    # A persisted business error is visible in history, not retried as a transport failure.
    return {'received':True,'status':item.status,'run_id':item.id}


@router.post('/api/order-connectors/hooks/{key}')
async def commerce_hook(key:str,request:Request,db:Session=Depends(get_db)):
    throttle_ip(request)
    raw=await bounded_body(request)
    # WooCommerce sends an unsigned reachability ping. It must never acquire orders.
    if request.headers.get('content-type','').startswith('application/x-www-form-urlencoded') and re.fullmatch(rb'webhook_id=[0-9]+',raw):
        return {'received':False,'ping':True}
    src=locked_source(db,key)
    provider=src.configuration.get('connector')
    if provider not in ('shopify','woocommerce'):
        raise HTTPException(404,'Collegamento non trovato.')
    prefix='x-shopify-' if provider=='shopify' else 'x-wc-webhook-'
    signature=request.headers.get(prefix+('hmac-sha256' if provider=='shopify' else 'signature'))
    adapter.verify_signature(raw,signature,adapter.unseal(src.configuration['connector_secret']))
    store=request.headers.get('x-shopify-shop-domain') if provider=='shopify' else request.headers.get('x-wc-webhook-source','').removeprefix('https://').rstrip('/')
    if store!=src.configuration['store']:
        raise HTTPException(401,'Negozio non corrispondente al collegamento.')
    topic=request.headers.get(prefix+'topic')
    if topic!=('orders/create' if provider=='shopify' else 'order.created'):
        raise HTTPException(422,'Configura soltanto l evento di creazione ordine.')
    event=request.headers.get(prefix+('webhook-id' if provider=='shopify' else 'delivery-id'),'')
    if not event or len(event)>200:
        raise HTTPException(422,'Identificativo evento mancante.')
    try:
        body=json.loads(raw)
    except (ValueError,UnicodeError):
        raise HTTPException(422,'JSON non valido.')
    return receive(db,src,body,event,raw,lambda data:[adapter.shop_order(data,provider,src.configuration.get('excluded_fields',[]))])


@router.post('/api/order-connectors/email')
async def email_hook(request:Request,db:Session=Depends(get_db)):
    raise HTTPException(503, 'Inoltro email in fase di sviluppo: ricezione non disponibile.')
