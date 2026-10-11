"""Company-scoped orders and auditable, versioned operational corrections."""
from datetime import datetime, date
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, or_
from ..models import User
from ..order_models import Order, OrderSource, OrderEvent, OrderItem, RouteOrderAssignment
from .occasional_stops import verify_stop_address, sign_stop_address
from .customer_planning import has_verified_coordinates

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
    from .order_customers import auto_link
    auto_link(db, order, actor)
    auto_verify_linked_customer(db, order, actor)
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
    if order.customer_resolution == 'automatic' and {'recipient_name','delivery_address'} & changes.keys():
        order.customer_id = None; order.customer_resolution = 'pending'
    from .order_customers import auto_link
    auto_link(db, order, actor)
    order.verification_status = 'pending'
    order.status = 'da_verificare'
    touch(order)
    auto_verify_linked_customer(db, order, actor)
    record(db, order, actor, 'corrected', changes)
    return order



def address_is_verified(db, order):
    """Only a valid proof for the current effective destination permits planning."""
    from .order_customers import effective
    values, _ = effective(db, order)
    proof = order.address_verification or {}
    return (bool(values.get('recipient_name')) and bool(values.get('delivery_address'))
            and proof.get('input_address') == values['delivery_address']
            and has_verified_coordinates(proof.get('stato_geocodifica'), proof.get('lat'), proof.get('lon'))
            and bool(proof.get('geocoding_token')))


def _trusted_customer_proof(db, order, address):
    """Reuse previously verified coordinates only for the exact same customer destination."""
    from .order_customers import linked, normalize
    customer = linked(db, order)
    if not customer or normalize(customer.indirizzo) != normalize(address):
        return None
    if not has_verified_coordinates(customer.stato_geocodifica, customer.lat, customer.lon):
        return None
    canonical = customer.indirizzo_geocodificato or customer.indirizzo
    return {'indirizzo': canonical, 'indirizzo_geocodificato': canonical,
            'lat': customer.lat, 'lon': customer.lon, 'stato_geocodifica': 'verificato',
            'geocoding_token': sign_stop_address(order.user_id, canonical, customer.lat, customer.lon)}


def _mark_verified(db, order, proof, address, actor, method):
    if not has_verified_coordinates(proof.get('stato_geocodifica'), proof.get('lat'), proof.get('lon')):
        raise HTTPException(422, 'Impossibile confermare le coordinate della consegna.')
    before = order.status
    order.address_verification = {**proof, 'input_address': address}
    order.verification_status = 'verified'
    order.status = 'pronto'
    touch(order)
    record(db, order, actor, 'address_verified', {'address': address, 'method': method})
    if before != 'pronto':
        record(db, order, actor, 'status_changed', {'before': before, 'after': 'pronto', 'method': 'automatic'})


def auto_verify_linked_customer(db, order, actor):
    """No geocoding API call for a destination already verified in the customer registry."""
    from .order_customers import effective
    if order.status not in EDITABLE or (address_is_verified(db, order) and order.status == 'pronto'):
        return False
    values, _ = effective(db, order)
    address = values.get('delivery_address')
    if not values.get('recipient_name') or not address:
        return False
    proof = _trusted_customer_proof(db, order, address)
    if not proof:
        return False
    _mark_verified(db, order, proof, address, actor, 'verified_customer')
    return True

def verify_address(db, order, version, actor, reusable=None):
    editable(db, order, version)
    from .order_customers import effective
    values, _ = effective(db, order)
    address = values.get('delivery_address')
    if not values.get('recipient_name') or not address:
        raise HTTPException(422, 'Per verificare inserisci destinatario e indirizzo completi.')
    if address_is_verified(db, order) and order.status == 'pronto':
        return order  # The previous verification remains valid; no new API request.
    proof = _trusted_customer_proof(db, order, address)
    method = 'verified_customer' if proof else 'geocoding'
    if proof is None and reusable and reusable.get('input_address') == address:
        if (has_verified_coordinates(reusable.get('stato_geocodifica'), reusable.get('lat'), reusable.get('lon'))
                and reusable.get('geocoding_token') == sign_stop_address(
                    order.user_id, reusable.get('indirizzo'), reusable['lat'], reusable['lon'])):
            proof = reusable
            method = 'reused_batch'
    if proof is None:
        proof = verify_stop_address(db, order.user_id, address)
    # Geocoding usage logging may commit. Reacquire and recheck after the call.
    order = get_order(db, order.user_id, order.id, lock=True)
    editable(db, order, version)
    if effective(db, order)[0].get('delivery_address') != address:
        raise HTTPException(409, 'Indirizzo cambiato: ripeti la verifica.')
    _mark_verified(db, order, proof, address, actor, method)
    return order


def transition(db, order, data, actor):
    editable(db, order, data.version)
    if data.status == 'pronto':
        from .order_customers import anomalies
        problems = [a['message'] for a in anomalies(db,order)[0] if a['blocking']]
        if problems: raise HTTPException(422, ' '.join(problems))
    before = order.status
    order.status = data.status
    if data.status != 'annullato':
        order.verification_status = 'verified' if data.status == 'pronto' else 'pending'
    touch(order)
    record(db, order, actor, 'status_changed', {'before': before, 'after': order.status})
    return order



def verify_multiple(db, user_id, actor, *, after_id=0, limit=10, q='', source_id=None, status=None, date_from=None, date_to=None):
    """Small resumable chunks prevent long web requests and keep geocoding usage bounded."""
    limit = max(1, min(10, limit))
    query = db.query(Order.id).filter(Order.user_id == user_id, Order.id > after_id,
        Order.status.in_(('nuovo', 'da_verificare', 'pronto')),
        ~Order.id.in_(db.query(RouteOrderAssignment.order_id)))
    if q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(or_(Order.number.ilike('%' + escaped + '%', escape='\\'),
            Order.recipient_name.ilike('%' + escaped + '%', escape='\\'),
            Order.delivery_address.ilike('%' + escaped + '%', escape='\\')))
    if source_id is not None:
        query = query.filter(Order.source_id == source_id)
    if status is not None:
        query = query.filter(Order.status == status)
    if date_from:
        query = query.filter(Order.requested_date >= date_from)
    if date_to:
        query = query.filter(Order.requested_date <= date_to)
    identifiers = [id_ for (id_,) in query.order_by(Order.id).limit(limit).all()]
    result = {'processed': len(identifiers), 'verified': 0, 'already_verified': 0,
        'failed': 0, 'issues': [], 'next_after': identifiers[-1] if identifiers else after_id,
        'has_more': len(identifiers) == limit}
    proofs = {}
    for oid in identifiers:
        try:
            order = get_order(db, user_id, oid, lock=True)
            if address_is_verified(db, order):
                if order.status != 'pronto':
                    order.status = 'pronto'
                    order.verification_status = 'verified'
                    touch(order)
                    record(db, order, actor, 'status_changed', {'after': 'pronto', 'method': 'automatic'})
                    db.commit()
                    result['verified'] += 1
                else:
                    result['already_verified'] += 1
                continue
            from .order_customers import effective
            address = effective(db, order)[0].get('delivery_address')
            proof = proofs.get(address)
            updated = verify_address(db, order, order.version, actor, reusable=proof)
            db.commit()
            if address and updated.address_verification:
                proofs[address] = dict(updated.address_verification)
            result['verified'] += 1
        except HTTPException as exc:
            db.rollback()
            result['failed'] += 1
            if len(result['issues']) < 10:
                result['issues'].append({'order_id': oid, 'reason': str(exc.detail)})
        except Exception:
            db.rollback()
            result['failed'] += 1
            if len(result['issues']) < 10:
                result['issues'].append({'order_id': oid, 'reason': 'Verifica non riuscita. Riprova o controlla l’indirizzo.'})
    return result

def summary(order, source_name):
    return {key: getattr(order, key) for key in ('id', 'number', 'recipient_name', 'delivery_address',
            'requested_date', 'status', 'received_at', 'updated_at', 'version')} | {
        'source_name': source_name, 'source_id': order.source_id,
        'weight_kg': order.operational_data.get('weight_kg'), 'packages': order.operational_data.get('packages')}


def detail(db, order):
    from .order_customers import anomalies
    issues, effective_values, inherited = anomalies(db, order)
    source = db.get(OrderSource, order.source_id)
    assignments = db.query(RouteOrderAssignment).filter_by(user_id=order.user_id, order_id=order.id).all()
    events = db.query(OrderEvent).filter_by(order_id=order.id).order_by(OrderEvent.id.desc()).limit(100).all()
    return summary(order, source.name) | {
        'external_id': order.external_id, 'external_customer_id': order.external_customer_id,
        'customer_resolution': order.customer_resolution, 'anomalies': issues, 'effective_data': effective_values, 'inherited_fields': inherited,
        'customer_id': order.customer_id, 'operational_data': order.operational_data,
        'original_payload': order.original_payload, 'latest_received_payload': order.ingested_payload, 'address_verification': order.address_verification,
        'acquisition_status': order.acquisition_status, 'verification_status': order.verification_status,
        'delivery_status': order.delivery_status,
        'items': [item.data for item in db.query(OrderItem).filter_by(order_id=order.id).order_by(OrderItem.line_number)],
        'assignments': [{'route_id': a.route_plan_id, 'stop_key': a.stop_key} for a in assignments],
        'events': [{'kind': e.kind, 'actor': e.actor, 'changes': e.changes, 'created_at': e.created_at} for e in events],
        'history_limit': 100,
    }
