"""Planning drafts: a giro left before scheduling (from orders or customers) that can be resumed later."""
from datetime import date
from fastapi import HTTPException
from ..core.clock import utc_now
from sqlalchemy import func
from ..models import RoutePlan, Delivery, Vehicle, Driver
from ..order_models import Order, PlanningDraft, RouteOrderAssignment
from .order_planning import selection, selection_response, check_version

READY = ('nuovo', 'da_verificare', 'pronto')


def draft_name(configuration, source):
    name = (configuration or {}).get('nome', '').strip()
    if name:
        return name[:200]
    day = (configuration or {}).get('data_giro')
    label = 'Giro da ordini' if source == 'orders' else 'Giro da clienti'
    try:
        return f'{label} del {date.fromisoformat(day).strftime("%d/%m")}'
    except (TypeError, ValueError):
        return label


def summary(row):
    configuration = row.configuration or {}
    stops = len(row.stops) if row.stops is not None else len(row.order_ids)
    return {'id': row.id, 'source': row.source, 'name': row.name, 'data_giro': configuration.get('data_giro') or None,
            'planning_mode': configuration.get('planning_mode', 'single'),
            'vehicles': len(configuration.get('fleet_resources') or []) if configuration.get('planning_mode') == 'fleet' else 1,
            'stops': stops, 'orders': len(row.order_ids), 'stage': row.stage, 'fleet_plan_id': row.fleet_plan_id,
            'created_at': row.created_at, 'updated_at': row.updated_at}


def list_drafts(db, user_id, actor):
    drafts = db.query(PlanningDraft).filter_by(user_id=user_id, actor=actor).order_by(PlanningDraft.updated_at.desc()).limit(50).all()
    # Giri già calcolati e salvati come bozza (non ancora programmati): si riaprono dal pianificatore.
    routes = db.query(RoutePlan.id, RoutePlan.nome, RoutePlan.data_giro, RoutePlan.orario_partenza, RoutePlan.created_at,
                      RoutePlan.vehicle_id, RoutePlan.driver_id).filter(
        RoutePlan.user_id == user_id, RoutePlan.status == 'bozza').order_by(RoutePlan.id.desc()).limit(50).all()
    ids = [r.id for r in routes]
    stops = dict(db.query(Delivery.route_plan_id, func.count(Delivery.id)).filter(Delivery.route_plan_id.in_(ids)).group_by(Delivery.route_plan_id)) if ids else {}
    from_orders = {rid for (rid,) in db.query(RouteOrderAssignment.route_plan_id).filter(RouteOrderAssignment.route_plan_id.in_(ids)).distinct()} if ids else set()
    vehicles = {v.id: v.nome for v in db.query(Vehicle.id, Vehicle.nome).filter(Vehicle.id.in_({r.vehicle_id for r in routes if r.vehicle_id}))}
    drivers = {d.id: ' '.join(x for x in (d.nome, d.cognome) if x) for d in db.query(Driver.id, Driver.nome, Driver.cognome).filter(Driver.id.in_({r.driver_id for r in routes if r.driver_id}))}
    return {'drafts': [summary(row) for row in drafts],
            'routes': [{'id': r.id, 'name': r.nome or 'Giro consegne', 'data_giro': r.data_giro.isoformat() if r.data_giro else None,
                        'orario_partenza': r.orario_partenza.strftime('%H:%M') if r.orario_partenza else None,
                        'source': 'orders' if r.id in from_orders else 'customers', 'stops': stops.get(r.id, 0),
                        'vehicle': vehicles.get(r.vehicle_id), 'driver': drivers.get(r.driver_id),
                        'created_at': r.created_at} for r in routes]}


def create(db, user_id, actor, data):
    if data.source == 'orders':
        row = selection(db, user_id, actor, lock=True)
        check_version(row, data.selection_version)
        if row is None or not row.order_ids:
            raise HTTPException(422, 'Nessun ordine selezionato da mettere in bozza.')
        draft = PlanningDraft(user_id=user_id, actor=actor, source='orders', order_ids=list(row.order_ids),
                              configuration=dict(row.configuration or {}), stops=row.stops)
        # La selezione si svuota: aprendo Ordini non resta spuntato il giro lasciato in bozza.
        row.order_ids, row.stops, row.configuration = [], None, {}
        row.version += 1
        row.updated_at = utc_now()
    else:
        if not data.stops:
            raise HTTPException(422, 'Nessuna consegna da mettere in bozza.')
        draft = PlanningDraft(user_id=user_id, actor=actor, source='customers', order_ids=[],
                              configuration=data.configuration.model_dump(mode='json') if data.configuration else {},
                              stops=[s.model_dump(mode='json') for s in data.stops])
    draft.name = draft_name(draft.configuration, draft.source)
    draft.stage = data.stage
    draft.fleet_plan_id = data.fleet_plan_id if data.stage == 'suddivisione' else None
    db.add(draft)
    db.flush()
    return draft


def owned(db, user_id, actor, draft_id, lock=False):
    query = db.query(PlanningDraft).filter_by(id=draft_id, user_id=user_id, actor=actor)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise HTTPException(404, 'Bozza non trovata.')
    return row


def resume(db, user_id, actor, draft_id, data):
    draft = owned(db, user_id, actor, draft_id, lock=True)
    dropped = 0
    result = {'source': draft.source, 'configuration': draft.configuration, 'stops': draft.stops,
              'stage': draft.stage, 'fleet_plan_id': draft.fleet_plan_id}
    if draft.source == 'orders':
        row = selection(db, user_id, actor, lock=True)
        check_version(row, data.selection_version)
        if row is not None and row.order_ids:
            raise HTTPException(409, 'Hai già degli ordini selezionati: mettili in bozza o svuota la selezione prima di riprendere questa bozza.')
        # Solo gli ordini ancora da pianificare: quelli annullati o già in un giro restano fuori.
        ready = {o.id for o in db.query(Order.id).filter(
            Order.user_id == user_id, Order.id.in_(draft.order_ids), Order.status.in_(READY),
            ~Order.id.in_(db.query(RouteOrderAssignment.order_id)))}
        if not ready:
            raise HTTPException(409, 'Nessun ordine di questa bozza è ancora da pianificare: puoi eliminarla.')
        dropped = len(draft.order_ids) - len(ready)
        if row is None:
            from ..order_models import OrderPlanningSelection
            row = OrderPlanningSelection(user_id=user_id, actor=actor, version=0)
            db.add(row)
        row.order_ids = sorted(ready)
        row.configuration = dict(draft.configuration or {})
        # Le fermate salvate valgono solo se tutti gli ordini sono ancora disponibili.
        row.stops = draft.stops if not dropped else None
        row.version += 1
        row.updated_at = utc_now()
        db.flush()
        result['selection'] = selection_response(db, row)
    db.delete(draft)
    db.flush()
    return result | {'dropped': dropped}


def delete(db, user_id, actor, draft_id):
    db.delete(owned(db, user_id, actor, draft_id, lock=True))
    db.flush()
