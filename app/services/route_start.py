"""Shared checks for every command that first starts a route."""
from fastapi import HTTPException

from ..core.utils import local_today
from ..models import Driver, RoutePlan, Vehicle


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


def ensure_new_route_can_start(db, route):
    """Already-running legacy routes remain recoverable, including after expiry."""
    if route.status in ('in_corso', 'completato'):
        return
    if route.status == 'annullato':
        raise HTTPException(409, 'Il giro è annullato')
    if route.data_giro > local_today():
        raise HTTPException(409, 'Non puoi avviare un giro programmato per una data futura')
    ensure_no_running_resource_conflict(db, route)
