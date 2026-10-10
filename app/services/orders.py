"""Company-scoped orders and auditable, versioned operational corrections."""
from datetime import datetime, date
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func
from ..models import User
from ..order_models import Order, OrderSource, OrderEvent, OrderItem, RouteOrderAssignment
from .occasional_stops import verify_stop_address

STATUSES = ('nuovo', 'da_verificare', 'pronto', 'assegnato', 'in_consegna', 'consegnato', 'non_consegnato', 'annullato')
EDITABLE = ('nuovo', 'da_verificare', 'pronto')


def get_order(db, user_id, order_id, lock=False):
    query = db.query(Order).filter_by(user_id=user_id, id=order_id)
    if lock:
        query = query.with_for_update().populate_existing()
    order = query.first()
    if order is None:
        raise HTTPException(404, 'Ordine non trovato')
    return order


def editable(db, order, version):
    if order.version != version:
        raise HTTPException(409, 'Ordine aggiornato da un altro operatore. Riapri il dettaglio prima di salvare.')
    if order.status not in EDITABLE or db.query(RouteOrderAssignment.id).filter_by(order_id=order.id).first():
        raise HTTPException(409, 'Ordine annullato o collegato a un giro: modifica non consentita.')


def record(db, order, actor, kind, changes):
    db.add(OrderEvent(order_id=order.id, actor=actor, kind=kind, changes=changes))


def touch(order):
    order.version += 1
    order.updated_at = datetime.utcnow()


def project(order, values):
    order.operational_data = values
    for key in ('number', 'recipient_name', 'delivery_address'):
        setattr(order, key, values.get(key))
    order.requested_date = date.fromisoformat(values['requested_date']) if values.get('requested_date') else None


def create_order(db, user_id, data, actor):
    # Serializes first-source creation; the uniqueness constraint is a second guard.
    db.query(User).filter_by(id=user_id).with_for_update().one()
    source = db.query(OrderSource).filter_by(user_id=user_id, key='manual').first()
    if source is None:
        source = OrderSource(user_id=user_id, key='manual', name='Inserimento manuale', kind='manual', status='active')
        db.add(source); db.flush()
    original = data.model_dump(mode='json')
    order = Order(user_id=user_id, source_id=source.id, external_id=str(uuid4()),
                  original_payload=original, operational_data={}, number=data.number)
    project(order, data.model_dump(mode='json', exclude={'items'}))
    db.add(order); db.flush()
    for index, item in enumerate(original['items'], 1):
        db.add(OrderItem(order_id=order.id, line_number=index, data=item))
    record(db, order, actor, 'created', {'source': 'manual'})
    return order


def update_order(db, order, data, actor):
    editable(db, order, data.version)
    values = data.model_dump(mode='json', exclude={'version'})
    changes = {key: {'before': order.operational_data.get(key), 'after': value}
               for key, value in values.items() if order.operational_data.get(key) != value}
    if not changes:
        return order
    if 'delivery_address' in changes:
        order.address_verification = None
    project(order, values)
    order.verification_status = 'pending'
    order.status = 'da_verificare'
    touch(order)
    record(db, order, actor, 'corrected', changes)
    return order


def verify_address(db, order, version, actor):
    editable(db, order, version)
    if not order.delivery_address:
        raise HTTPException(422, 'Inserisci un indirizzo di consegna completo.')
    user_id, order_id, address = order.user_id, order.id, order.delivery_address
    verified = verify_stop_address(db, user_id, address)
    # Geocoding usage logging may commit. Reacquire and recheck after the call.
    order = get_order(db, user_id, order_id, lock=True)
    editable(db, order, version)
    order.address_verification = {**verified, 'input_address': order.delivery_address}
    touch(order)
    record(db, order, actor, 'address_verified', {'address': order.delivery_address})
    return order


def transition(db, order, data, actor):
    editable(db, order, data.version)
    if data.status == 'pronto':
        if not order.recipient_name or not order.delivery_address:
            raise HTTPException(422, 'Completa destinatario e indirizzo prima di confermare l’ordine.')
        verification = order.address_verification or {}
        if verification.get('input_address') != order.delivery_address or verification.get('stato_geocodifica') != 'verificato':
            raise HTTPException(422, 'Verifica l’indirizzo prima di rendere pronto l’ordine.')
    before = order.status
    order.status = data.status
    if data.status != 'annullato':
        order.verification_status = 'verified' if data.status == 'pronto' else 'pending'
    touch(order)
    record(db, order, actor, 'status_changed', {'before': before, 'after': order.status})
    return order


def summary(order, source_name):
    return {key: getattr(order, key) for key in ('id', 'number', 'recipient_name', 'delivery_address',
            'requested_date', 'status', 'received_at', 'updated_at', 'version')} | {
        'source_name': source_name, 'source_id': order.source_id,
        'weight_kg': order.operational_data.get('weight_kg'), 'packages': order.operational_data.get('packages')}


def detail(db, order):
    source = db.get(OrderSource, order.source_id)
    assignments = db.query(RouteOrderAssignment).filter_by(user_id=order.user_id, order_id=order.id).all()
    events = db.query(OrderEvent).filter_by(order_id=order.id).order_by(OrderEvent.id.desc()).limit(100).all()
    return summary(order, source.name) | {
        'external_id': order.external_id, 'external_customer_id': order.external_customer_id,
        'customer_id': order.customer_id, 'operational_data': order.operational_data,
        'original_payload': order.original_payload, 'address_verification': order.address_verification,
        'acquisition_status': order.acquisition_status, 'verification_status': order.verification_status,
        'delivery_status': order.delivery_status,
        'items': [item.data for item in db.query(OrderItem).filter_by(order_id=order.id).order_by(OrderItem.line_number)],
        'assignments': [{'route_id': a.route_plan_id, 'stop_key': a.stop_key} for a in assignments],
        'events': [{'kind': e.kind, 'actor': e.actor, 'changes': e.changes, 'created_at': e.created_at} for e in events],
        'history_limit': 100,
    }
