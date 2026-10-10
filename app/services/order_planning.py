"""Persistent actor selections and conversion into the existing planning schema."""
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL
from fastapi import HTTPException
from sqlalchemy import or_
from ..models import User, RoutePlan, Vehicle
from ..order_models import Order, OrderPlanningSelection, RouteOrderAssignment
from ..schemas.order_planning import MAX_SELECTION
from .customer_planning import has_verified_coordinates

ORDER_FIELDS = ('order_refs', 'order_stop_key', 'order_numbers', 'order_operational')


def stop_key(user_id, order_id):
    return str(uuid5(NAMESPACE_URL, f'girofacile-order:{user_id}:{order_id}'))


def selection(db, user_id, actor, lock=False):
    query = db.query(OrderPlanningSelection).filter_by(user_id=user_id, actor=actor)
    return (query.with_for_update().populate_existing() if lock else query).first()


def selection_response(db, row):
    if row is None:
        return {'version': 0, 'order_ids': [], 'configuration': {}, 'stops': None, 'routes': []}
    routes = db.query(RoutePlan).join(RouteOrderAssignment, RouteOrderAssignment.route_plan_id == RoutePlan.id).filter(
        RouteOrderAssignment.user_id == row.user_id, RouteOrderAssignment.order_id.in_(row.order_ids)).distinct().all()
    return {'version': row.version, 'order_ids': row.order_ids, 'configuration': row.configuration,
            'stops': row.stops, 'updated_at': row.updated_at,
            'routes': [{'id': r.id, 'name': r.nome, 'status': r.status} for r in routes]}


def check_version(row, version):
    if (row.version if row else 0) != version:
        raise HTTPException(409, 'Selezione modificata in un’altra scheda. Ricarica la pagina Ordini.')


def filtered_ready(db, user_id, filters):
    query = db.query(Order).filter_by(user_id=user_id, status='pronto')
    query = query.filter(~Order.id.in_(db.query(RouteOrderAssignment.order_id)))
    if filters.status and filters.status != 'pronto':
        return query.filter(False)
    if filters.q.strip():
        value = '%' + filters.q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + '%'
        query = query.filter(or_(*(c.ilike(value, escape='\\') for c in (Order.number, Order.recipient_name, Order.delivery_address))))
    if filters.source_id is not None: query = query.filter(Order.source_id == filters.source_id)
    if filters.date_from: query = query.filter(Order.requested_date >= filters.date_from)
    if filters.date_to: query = query.filter(Order.requested_date <= filters.date_to)
    return query


def change_selection(db, user_id, actor, data):
    db.query(User).filter_by(id=user_id).with_for_update().one()
    row = selection(db, user_id, actor, lock=True)
    check_version(row, data.version)
    ids = set(row.order_ids if row else [])
    if data.action == 'clear': ids = set()
    elif data.action == 'remove': ids -= set(data.order_ids)
    else:
        query = filtered_ready(db, user_id, data.filters)
        if data.action == 'add': query = query.filter(Order.id.in_(data.order_ids))
        added = {o.id for o in query.order_by(Order.id).limit(MAX_SELECTION + 1)}
        if data.action == 'add' and added != set(data.order_ids):
            raise HTTPException(409, 'Seleziona solo ordini pronti e non già riservati a un giro.')
        ids |= added
        if len(ids) > MAX_SELECTION:
            raise HTTPException(422, f'Prepara al massimo {MAX_SELECTION} ordini per selezione. Restringi i filtri e prepara più giri.')
    if row is None:
        row = OrderPlanningSelection(user_id=user_id, actor=actor, version=0)
        db.add(row)
    row.order_ids = sorted(ids)
    row.stops = None
    row.version += 1
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def snapshot(db, user_id, actor, data):
    row = selection(db, user_id, actor, lock=True)
    check_version(row, data.version)
    if row is None: raise HTTPException(404, 'Selezione non trovata')
    stops = [s.model_dump(mode='json') for s in data.stops] if data.stops is not None else None
    if stops is not None:
        ids = [r['id'] for s in stops for r in s.get('order_refs', [])]
        if len(ids) != len(set(ids)) or not set(ids) <= set(row.order_ids):
            raise HTTPException(422, 'La bozza contiene ordini estranei alla selezione o ripetuti.')
    row.configuration = data.configuration.model_dump(mode='json')
    row.stops = stops
    if stops is not None:
        # Removing a stop only removes it from this actor's selection.
        row.order_ids = sorted(ids)
    row.version += 1
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def to_stop(order):
    from sqlalchemy.orm import object_session
    from .order_customers import effective
    values, _ = effective(object_session(order), order)
    verified = order.address_verification or {}
    if not values.get('recipient_name') or not values.get('delivery_address') or verified.get('input_address') != values['delivery_address'] or not has_verified_coordinates(verified.get('stato_geocodifica'), verified.get('lat'), verified.get('lon')):
        raise HTTPException(409, f'Ordine {order.number}: completa e verifica il destinatario prima di pianificare.')
    return dict(customer_id=None, cliente_nome=values['recipient_name'], indirizzo=verified['indirizzo'],
                lat=verified['lat'], lon=verified['lon'], geocoding_token=verified['geocoding_token'],
                stato_geocodifica='verificato', indirizzo_geocodificato=verified['indirizzo'],
                peso_kg=values.get('weight_kg') or 0, colli=values.get('packages') or 0,
                scarico_mattina_da=values.get('time_from') or values.get('scarico_mattina_da'), scarico_mattina_a=values.get('time_to') or values.get('scarico_mattina_a'),
                scarico_pomeriggio_da=values.get('scarico_pomeriggio_da'), scarico_pomeriggio_a=values.get('scarico_pomeriggio_a'), tempo_scarico_min=values.get('tempo_scarico_min') or 10,
                sponda=values.get('tail_lift') is True, ztl=values.get('ztl') is True,
                note=values.get('notes'), order_refs=[{'id':order.id,'version':order.version}],
                order_stop_key=stop_key(order.user_id, order.id), order_numbers=[order.number],
                order_operational={key:values.get(key) for key in ('pallet_truck','pallets','volume_m3','requirements')})


def preview(db, user, actor, data):
    row = snapshot(db, user.id, actor, data)
    config = row.configuration
    from ..routers.routes import _require_owned_entity, build_vehicle_dict, ensure_not_past_route_date
    from ..models import Deposit, Driver
    from ..core.utils import minutes_from_hhmm
    from ..optimizer import validate_vehicle_load
    if not config['data_giro'] or minutes_from_hhmm(config['orario_partenza']) is None:
        raise HTTPException(422, 'Completa data e orario di partenza.')
    ensure_not_past_route_date(config['data_giro'])
    _require_owned_entity(db, Deposit, user, config['deposit_id'], 'Deposito')
    vehicle = _require_owned_entity(db, Vehicle, user, config['vehicle_id'], 'Mezzo')
    _require_owned_entity(db, Driver, user, config['driver_id'], 'Autista')
    if not row.order_ids: raise HTTPException(422, 'Seleziona almeno un ordine pronto.')
    orders = db.query(Order).filter(Order.user_id == user.id, Order.id.in_(row.order_ids)).order_by(Order.id).all()
    if len(orders) != len(row.order_ids) or any(o.status != 'pronto' for o in orders):
        raise HTTPException(409, 'Uno o più ordini non sono più pronti. Torna a Ordini e aggiorna la selezione.')
    if db.query(RouteOrderAssignment.id).filter(RouteOrderAssignment.order_id.in_(row.order_ids)).first():
        raise HTTPException(409, 'Un ordine è già riservato a un giro. Apri il giro dalla pagina Ordini.')
    warnings = []
    for order in orders:
        if order.requested_date and order.requested_date.isoformat() != config['data_giro']:
            raise HTTPException(422, f'Ordine {order.number}: la data richiesta è {order.requested_date.isoformat()}. Modifica la selezione o correggi esplicitamente l’ordine.')
        if order.operational_data.get('weight_kg') is None or order.operational_data.get('packages') is None:
            warnings.append(f'Ordine {order.number}: peso o colli non indicati; verifica il carico prima del calcolo.')
        if any(order.operational_data.get(k) for k in ('pallet_truck','pallets','volume_m3','requirements')):
            warnings.append(f'Ordine {order.number}: verifica anche transpallet, pallet, volume e requisiti operativi; le capacità automatiche sono controllate su peso e colli.')
    from .order_grouping import group_stops
    if row.stops is None:
        stops = [to_stop(o) for o in orders]
        if config.get('group_orders'): stops = group_stops(user.id,stops)
    else:
        stops = row.stops
        from .route_orders import validate_references
        validate_references(db,user.id,stops,route_date=config['data_giro'])
    if config.get('group_orders'):
        warnings.append(f"{len(orders)} ordini preparati in {len(stops)} fermate. Apri il dettaglio per vedere gli ordini inclusi.")
    try: validate_vehicle_load(stops, build_vehicle_dict(vehicle))
    except ValueError as exc:
        warnings.append(str(exc) + ' Modifica la selezione o il mezzo, oppure prepara più giri.')
    row.stops = stops
    return row, warnings
