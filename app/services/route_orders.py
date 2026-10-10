"""Transactional order reservations and delivery lifecycle, independent of Delivery IDs."""
import json
from fastapi import HTTPException
from ..order_models import Order, RouteOrderAssignment
from .orders import record, touch
from .order_planning import ORDER_FIELDS, to_stop
from .order_grouping import group_key, compatible, merge


def require_planning_permission(request, rows, db=None, route_id=None):
    actor = getattr(request.state, 'company_collaborator', None)
    if actor is None: return
    existing = route_id and db is not None and db.query(RouteOrderAssignment.id).filter_by(user_id=actor.user_id, route_plan_id=route_id).first()
    if not existing and not any(row.get('order_refs') for row in rows): return
    from .company_permissions import permissions_for
    if 'orders.plan' not in permissions_for(actor):
        raise HTTPException(403, 'Il tuo account non può trasferire ordini alla pianificazione.')


def lock_company(db, user_id):
    # Match save_route_result's company -> route -> orders lock hierarchy.
    from ..models import User
    db.query(User).filter_by(id=user_id).with_for_update().one()


def validate_references(db, user_id, rows, route_id=None, route_date=None, lock=False):
    refs = [ref for row in rows for ref in row.get('order_refs', [])]
    ids = [r['id'] for r in refs]
    if len(ids) > 1000: raise HTTPException(422, 'Prepara al massimo 1000 ordini per giro.')
    if len(ids) != len(set(ids)):
        raise HTTPException(422, 'Lo stesso ordine compare in più fermate.')
    query = db.query(Order).filter(Order.user_id == user_id, Order.id.in_(ids)).order_by(Order.id)
    if lock: query = query.with_for_update().populate_existing()
    orders = {o.id:o for o in query}
    if set(ids) != set(orders): raise HTTPException(404, 'Uno o più ordini non sono disponibili.')
    assigned = {a.order_id:a for a in db.query(RouteOrderAssignment).filter(RouteOrderAssignment.order_id.in_(ids))}
    for row in rows:
        if not row.get('order_refs'):
            for key in ORDER_FIELDS: row.pop(key, None)
            continue
        for ref in row['order_refs']:
            order = orders[ref['id']]
            existing = assigned.get(order.id)
            if existing and existing.route_plan_id != route_id:
                raise HTTPException(409, f'Ordine {order.number} già riservato a un altro giro. Rimuovilo dalla selezione.')
            if not existing and order.status != 'pronto':
                raise HTTPException(409, f'Ordine {order.number} non più pronto per la pianificazione.')
            if existing and order.status not in ('pronto', 'assegnato'):
                raise HTTPException(409, 'Ordine già avviato o chiuso: non può essere ripianificato.')
            if order.version != ref['version']:
                raise HTTPException(409, f'Ordine {order.number} aggiornato: ricarica la selezione o il giro.')
            if route_date and order.requested_date and order.requested_date.isoformat() != str(route_date):
                raise HTTPException(422, f'Ordine {order.number}: data del giro diversa dalla data richiesta.')
        if row.get('customer_id') is not None:
            raise HTTPException(422, 'La fermata usa l’indirizzo dell’ordine senza sostituire l’anagrafica cliente.')
        expected = group_key(user_id,[ref['id'] for ref in row['order_refs']])
        if row.get('order_stop_key') != expected:
            raise HTTPException(422, 'Riferimento della fermata ordine non valido.')
        members = [orders[ref['id']] for ref in row['order_refs']]
        if len(members)>1:
            stops = [to_stop(order) for order in members]
            if not compatible(stops): raise HTTPException(422,'Gli ordini della fermata hanno destinazioni, orari o requisiti incompatibili. Separali.')
            metadata = merge(user_id,stops)
            row['order_operational'] = metadata['order_operational']
        else:
            from .order_customers import effective
            values,_ = effective(db,members[0])
            row['order_operational'] = {key:values.get(key) for key in ('pallet_truck','pallets','volume_m3','requirements')}
        row['order_numbers'] = [order.number for order in members]
    return orders


def reserve_orders(db, plan, rows):
    """Called after the company/route lock, before any commit or delivery replacement."""
    previous = db.query(RouteOrderAssignment).filter_by(user_id=plan.user_id, route_plan_id=plan.id).all()
    ids = {r['id'] for row in rows for r in row.get('order_refs', [])} | {a.order_id for a in previous}
    # Sorted lock order also covers removed orders. The second validation runs
    # after any external routing provider's usage logger has committed.
    if ids:
        db.query(Order).filter(Order.user_id == plan.user_id, Order.id.in_(ids)).order_by(Order.id).with_for_update().populate_existing().all()
    orders = validate_references(db, plan.user_id, rows, plan.id, plan.data_giro, lock=True)
    previous_map = {a.order_id:a for a in previous}
    for assignment in previous:
        if assignment.order_id not in orders:
            order = db.get(Order, assignment.order_id)
            order.status = 'pronto'; order.delivery_status = 'not_assigned'; touch(order)
            record(db, order, 'route:'+str(plan.id), 'route_released', {'route_id':plan.id,'reason':'removed_from_route'})
            db.delete(assignment)
    for row in rows:
        for ref in row.get('order_refs', []):
            order = orders[ref['id']]
            if order.id not in previous_map:
                db.add(RouteOrderAssignment(user_id=plan.user_id, order_id=order.id, route_plan_id=plan.id, stop_key=row['order_stop_key']))
                order.status = 'assegnato'
                order.delivery_status = 'draft' if plan.status == 'bozza' else 'scheduled'
            if order.id in previous_map:
                previous_map[order.id].stop_key = row['order_stop_key']
            touch(order)
            record(db, order, 'route:'+str(plan.id), 'route_snapshot', {
                'route_id':plan.id,'stop_key':row['order_stop_key'],
                'delivery':{key:value for key,value in row.items() if key not in ('geocoding_token','order_refs')}})
            ref['version'] = order.version
    db.flush()


def sync_route_orders(db, plan, phase, delivery=None):
    assignments = db.query(RouteOrderAssignment).filter_by(user_id=plan.user_id, route_plan_id=plan.id).all()
    if delivery is not None:
        key = json.loads(delivery.optimizer_details or '{}').get('order_stop_key')
        assignments = [a for a in assignments if a.stop_key == key]
    ids = [a.order_id for a in assignments]
    orders = db.query(Order).filter(Order.user_id == plan.user_id, Order.id.in_(ids)).order_by(Order.id).with_for_update().populate_existing().all()
    by_id = {o.id:o for o in orders}
    for assignment in assignments:
        order = by_id[assignment.order_id]
        if order.status in ('consegnato','non_consegnato'): continue
        target, delivery_status = {
            'scheduled':('assegnato','scheduled'), 'started':('in_consegna','in_progress'),
            'delivered':('consegnato','delivered'), 'missed':('non_consegnato','not_delivered'),
            'completed':('non_consegnato','not_delivered'), 'cancelled':('pronto','not_assigned'),
        }[phase]
        if order.status == target and order.delivery_status == delivery_status: continue
        previous = order.status
        order.status, order.delivery_status = target, delivery_status
        touch(order)
        record(db, order, 'route:'+str(plan.id), 'route_status', {'route_id':plan.id,'before':previous,'after':target,'event':phase})
        if phase == 'cancelled': db.delete(assignment)
    db.flush()


def order_metadata(delivery):
    data = json.loads(delivery.optimizer_details or '{}')
    return {key:data[key] for key in ORDER_FIELDS if key in data}


def refresh_references(plan, rows):
    from sqlalchemy.orm import object_session
    db = object_session(plan)
    if db is None: return
    pairs = db.query(RouteOrderAssignment, Order).join(Order, Order.id == RouteOrderAssignment.order_id).filter(
        RouteOrderAssignment.user_id == plan.user_id, RouteOrderAssignment.route_plan_id == plan.id).all()
    current = {}
    for a,o in pairs: current.setdefault(a.stop_key,[]).append({'id':o.id,'version':o.version})
    for row in rows:
        key = row.get('order_stop_key')
        if key in current: row['order_refs'] = sorted(current[key],key=lambda r:r['id'])
