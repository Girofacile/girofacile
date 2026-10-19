"""Lazy verification of actor-selected orders and explicit, audited manual positions."""
from copy import deepcopy
from datetime import datetime,timedelta
from fastapi import HTTPException
from . import orders,order_planning as planning
from ..core.clock import utc_now
from ..order_models import Order
from ..schemas.orders import OrderUpdate
from .occasional_stops import sign_stop_address


def selected(db,user_id,actor,version,ids):
    row=planning.selection(db,user_id,actor,lock=True)
    planning.check_version(row,version)
    if row is None or not set(ids)<=set(row.order_ids):
        raise HTTPException(409,'Gli ordini non appartengono più alla selezione. Ricarica la pagina Ordini.')
    return row


def issue(order,detail,status=422):
    info=detail if isinstance(detail,dict) else {'message':str(detail)}
    return {'id':order.id,'version':order.version,'number':order.number,
            'recipient_name':order.recipient_name or '', 'address':order.delivery_address or '',
            'kind':'service' if status>=500 else info.get('kind','address'),
            'message':info.get('message','Verifica non riuscita.'),'candidate':info.get('candidate')}


def cached_failure(db,order):
    proofs=db.query(Order.address_verification).filter(Order.user_id==order.user_id,
        Order.delivery_address==order.delivery_address,Order.address_verification.isnot(None)).order_by(Order.id.desc()).limit(100).all()
    for (proof,) in proofs:
        try:
            if proof.get('input_address')==order.delivery_address and proof.get('failure') and datetime.fromisoformat(proof['attempted_at'])>utc_now()-timedelta(seconds=60):
                return proof['failure']
        except (TypeError,ValueError,KeyError,AttributeError):pass
    return None


def verify_selected(db,user_id,actor,data):
    version=data.version
    selected(db,user_id,actor,version,data.order_ids)
    issues=[];aborted=False
    for order_id in dict.fromkeys(data.order_ids):
        selected(db,user_id,actor,version,[order_id])
        order=orders.get_order(db,user_id,order_id,lock=True)
        orders.editable(db,order,order.version)
        if orders.address_is_verified(db,order) and order.status=='pronto':continue
        proof=orders._existing_order_proof(db,order,order.delivery_address)
        previous=None if data.retry or proof else cached_failure(db,order)
        if previous:
            if order.status!='da_verificare':
                order.status='da_verificare';order.verification_status='pending';orders.touch(order)
                orders.record(db,order,actor,'address_verification_reused_failure',{'message':previous.get('message')})
                db.commit()
            issues.append(issue(order,previous));continue
        attempt_version=order.version
        try:
            orders.verify_address(db,order,order.version,actor,strict=True)
            row=selected(db,user_id,actor,version,[order_id])
            row.stops=None;row.version+=1;row.updated_at=utc_now();version=row.version
            db.commit()
        except HTTPException as exc:
            db.rollback()
            if exc.status_code in (403,404,409):raise
            selected(db,user_id,actor,version,[order_id])
            order=orders.get_order(db,user_id,order_id,lock=True)
            orders.editable(db,order,attempt_version)
            info=issue(order,exc.detail,exc.status_code)
            if exc.status_code>=500:
                aborted=True
                # One provider failure stops the queue, avoiding repeated paid requests.
                pending=db.query(Order).filter(Order.user_id==user_id,Order.id.in_(planning.selection(db,user_id,actor).order_ids)).all()
                issues=[issue(o,exc.detail,503) for o in pending if not orders.address_is_verified(db,o)]
                break
            order.address_verification={'input_address':order.delivery_address,'attempted_at':utc_now().isoformat(),
                'failure':{k:info[k] for k in ('message','candidate','kind')}}
            order.status='da_verificare';order.verification_status='pending'
            orders.touch(order);orders.record(db,order,actor,'address_verification_failed',{'message':info['message']})
            db.commit();info['version']=order.version;issues.append(info)
    db.commit()
    return {'selection':planning.selection_response(db,planning.selection(db,user_id,actor)), 'issues':issues,'aborted':aborted}


def resolve(db,user_id,actor,data):
    row=selected(db,user_id,actor,data.version,[data.order_id])
    order=orders.get_order(db,user_id,data.order_id,lock=True)
    if data.action=='exclude':
        row.order_ids=[i for i in row.order_ids if i!=order.id]
    else:
        orders.editable(db,order,data.order_version)
        if not data.address or not data.recipient_name:
            raise HTTPException(422,'Inserisci destinatario e indirizzo prima di proseguire.')
        values=deepcopy(order.operational_data)
        values.update(delivery_address=data.address,recipient_name=data.recipient_name)
        orders.update_order(db,order,OrderUpdate(version=data.order_version,**values),actor)
        if data.action=='manual':
            if data.lat is None or data.lon is None:
                raise HTTPException(422,'Scegli una posizione sulla mappa prima di confermare.')
            proof={'indirizzo':data.address,'indirizzo_geocodificato':data.address,
                   'lat':data.lat,'lon':data.lon,'stato_geocodifica':'verificato','confirmed_manually':True,
                   'geocoding_token':sign_stop_address(user_id,data.address,data.lat,data.lon)}
            orders._mark_verified(db,order,proof,data.address,actor,'manual_position')
    row.stops=None;row.version+=1;row.updated_at=utc_now()
    db.commit()
    return {'selection':planning.selection_response(db,row)}
