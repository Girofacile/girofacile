"""Shared atomic commands for the driver, operator and company portals."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from ..core.utils import local_now, local_today
from ..models import RoutePlan, DeliveryStatus, User, Customer, Driver, Vehicle
from .delivery_pod import save_delivery_evidence, commit_delivery_update


class DeliveryUpdate(BaseModel):
    tempo_scarico: int | None = Field(default=None, ge=1, le=1440)
    motivo: Literal['assente', 'chiuso', 'rifiutato', 'altro'] = 'altro'
    note: str | None = Field(default=None, max_length=500)
    signature_data: str | None = Field(default=None, max_length=2_000_000)
    delivery_photo_data: str | None = Field(default=None, max_length=16_000_100)
    signed_by_name: str | None = Field(default=None, max_length=200)
    signature_note: str | None = Field(default=None, max_length=2000)


def lock_route_resources(db, route):
    """Serialize assignments/starts that touch the same driver or vehicle."""
    if route.driver_id:
        db.query(Driver).filter(
            Driver.id == route.driver_id, Driver.user_id == route.user_id
        ).with_for_update().one_or_none()
    if route.vehicle_id:
        db.query(Vehicle).filter(
            Vehicle.id == route.vehicle_id, Vehicle.user_id == route.user_id
        ).with_for_update().one_or_none()


def ensure_no_running_resource_conflict(db, route):
    """A driver/vehicle cannot start a second route while another is in progress."""
    lock_route_resources(db, route)
    base = db.query(RoutePlan).filter(
        RoutePlan.user_id == route.user_id,
        RoutePlan.id != route.id,
        RoutePlan.status == 'in_corso',
    )
    if route.driver_id:
        other = base.filter(RoutePlan.driver_id == route.driver_id).first()
        if other:
            raise HTTPException(409, f"Autista già impegnato nel giro '{other.nome}'")
    if route.vehicle_id:
        other = base.filter(RoutePlan.vehicle_id == route.vehicle_id).first()
        if other:
            raise HTTPException(409, f"Mezzo già impegnato nel giro '{other.nome}'")


def get_or_create_delivery_status(delivery_id, route_plan_id, db):
    # Serialize creation even before a DeliveryStatus row exists.
    db.query(RoutePlan).filter_by(id=route_plan_id).with_for_update().one()
    status = db.query(DeliveryStatus).filter_by(delivery_id=delivery_id, route_plan_id=route_plan_id).first()
    if status is None:
        status = DeliveryStatus(delivery_id=delivery_id, route_plan_id=route_plan_id, status='in_attesa')
        db.add(status)
        db.flush()
    return status


def update_customer_unload_time(customer, tempo):
    count = int(customer.tempo_scarico_rilevazioni or 0)
    customer.tempo_scarico_min = round(((customer.tempo_scarico_min or 10) * count + tempo) / (count + 1))
    customer.tempo_scarico_rilevazioni = count + 1


def mark_completed(route):
    from .live_position import clear_position
    clear_position(route)
    route.status = 'completato'
    route.completed_at = local_now().replace(tzinfo=None)
    route.completed_at_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    from sqlalchemy.orm import object_session
    from .route_orders import sync_route_orders
    db = object_session(route)
    if db is not None: sync_route_orders(db, route, "completed")


def refresh_route_completion(route_plan_id, db):
    route = db.get(RoutePlan, route_plan_id)
    if not route or route.status in ('annullato', 'completato'):
        return
    db.flush()
    statuses = {s.delivery_id: s.status for s in db.query(DeliveryStatus).filter_by(route_plan_id=route_plan_id)}
    if route.deliveries and all(statuses.get(d.id) in ('completata', 'mancata') for d in route.deliveries):
        mark_completed(route)


def _apply_delivery_update(db, delivery, payload, action):
    try:
        data = DeliveryUpdate.model_validate(payload).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_input=False, include_url=False))
    from .route_orders import lock_company
    from ..models import Delivery
    user_id = db.query(RoutePlan.user_id).filter_by(id=delivery.route_plan_id).scalar()
    if user_id is None: raise HTTPException(409, 'Il giro non è più disponibile')
    lock_company(db, user_id)
    route = db.query(RoutePlan).filter_by(id=delivery.route_plan_id).with_for_update().populate_existing().one()
    if db.query(Delivery.id).filter_by(id=delivery.id, route_plan_id=route.id).first() is None:
        raise HTTPException(409, 'Le fermate sono cambiate: ricarica il giro')
    if route.status == 'annullato':
        raise HTTPException(409, 'Il giro è annullato')
    status = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id, route_plan_id=route.id).first()
    target = {'complete': 'completata', 'missed': 'mancata'}.get(action)
    if target and status and status.status == target:
        return status  # Retries never change evidence, timestamps or statistics.
    if route.status == 'completato' or (status and status.status in ('completata', 'mancata')):
        raise HTTPException(409, 'La consegna o il giro è già chiuso')
    if status is None:
        status = DeliveryStatus(delivery_id=delivery.id, route_plan_id=route.id, status='in_attesa')
    owner = db.get(User, route.user_id)
    if action in ('complete', 'signature'):
        if action == 'signature' and not owner.delivery_signature_enabled:
            raise HTTPException(400, 'Firma cliente non attiva per questa azienda')
    from .usage_limits import start_route_usage
    start_route_usage(db, route)
    db.add(status)
    if target:
        status.status = target
        status.note_operatore = data['note'] or None
        status.completata_il = local_now().replace(tzinfo=None)
        if action == 'complete':
            status.tempo_scarico_effettivo = data['tempo_scarico']
            status.motivo_mancata = None
            if data['tempo_scarico'] and delivery.customer_id:
                customer = db.query(Customer).filter_by(id=delivery.customer_id).with_for_update().one()
                update_customer_unload_time(customer, data['tempo_scarico'])
        else:
            status.motivo_mancata = data['motivo']
        from .route_orders import sync_route_orders
        sync_route_orders(db, route, "delivered" if action == "complete" else "missed", delivery)
        refresh_route_completion(route.id, db)
    elif action == 'note':
        status.note_operatore = (data['note'] or '').strip() or None
    if action in ('complete', 'signature'):
        save_delivery_evidence(db, route, delivery, status, data, owner, action)
    return status


def apply_delivery_update(db, delivery, payload, action):
    try:
        return _apply_delivery_update(db, delivery, payload, action)
    except Exception:
        db.rollback()
        raise
