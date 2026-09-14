"""
Servizio piani abbonamento.
Definisce i limiti per piano e le funzioni di controllo.
"""
from datetime import datetime
from fastapi import HTTPException
from ..core.utils import parse_date_value
from sqlalchemy.orm import Session

from ..models import User, Customer, Vehicle, Driver, Deposit, RoutePlan
from ..core.utils import local_today_iso

# -----------------------------------------------------------------------
# Definizione limiti per piano
# -----------------------------------------------------------------------
PLAN_LIMITS = {
    "starter": {
        "name": "Starter",
        "max_customers": 30,
        "max_routes_per_day": 5,
        "max_deposits": 2,
        "max_vehicles": 3,
        "max_drivers": 3,
        "has_agents": False,
        "has_reports": False,
        "has_export": False,
        "has_geocoding": True,
        "has_mobile": True,
        "has_driver_chat": False,
    },
    "business": {
        "name": "Business",
        "max_customers": 150,
        "max_routes_per_day": 30,
        "max_deposits": 10,
        "max_vehicles": 20,
        "max_drivers": 20,
        "has_agents": True,
        "has_reports": True,
        "has_export": True,
        "has_geocoding": True,
        "has_mobile": True,
        "has_driver_chat": True,
    },
    "pro": {
        "name": "Pro",
        "max_customers": None,       # illimitato
        "max_routes_per_day": None,  # illimitato
        "max_deposits": None,
        "max_vehicles": None,
        "max_drivers": None,
        "has_agents": True,
        "has_reports": True,
        "has_export": True,
        "has_geocoding": True,
        "has_mobile": True,
        "has_driver_chat": True,
    },
}


def get_plan_limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])


def get_user_plan_status(user: User) -> str:
    """
    Ritorna lo stato effettivo del piano:
    - trial   → periodo di prova attivo
    - active  → abbonamento pagato attivo
    - expired → trial o abbonamento scaduto
    - cancelled → abbonamento cancellato
    """
    status = user.plan_status or "trial"
    if status == "trial":
        if user.trial_ends_at and datetime.utcnow() > user.trial_ends_at:
            return "expired"
    if status == "active":
        if user.plan_expires_at and datetime.utcnow() > user.plan_expires_at:
            return "expired"
    return status


def is_plan_active(user: User) -> bool:
    return get_user_plan_status(user) in ("trial", "active")


def require_active_plan(user: User):
    """Lancia 403 se il piano dell'utente non è attivo."""
    if not is_plan_active(user):
        raise HTTPException(
            status_code=403,
            detail="Il tuo piano è scaduto. Rinnova l'abbonamento per continuare ad usare GiroFacile."
        )


def require_feature(user: User, feature: str):
    """Lancia 403 se la feature non è disponibile nel piano dell'utente."""
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    if not limits.get(feature, False):
        plan_name = limits["name"]
        raise HTTPException(
            status_code=403,
            detail=f"La funzionalità richiesta non è disponibile nel piano {plan_name}. Effettua l'upgrade per sbloccarla."
        )


def check_customer_limit(user: User, db: Session):
    """Controlla se l'utente ha raggiunto il limite clienti del piano."""
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    max_c = limits.get("max_customers")
    if max_c is None:
        return  # illimitato
    count = db.query(Customer).filter(Customer.user_id == user.id, Customer.deleted_at.is_(None)).count()
    if count >= max_c:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_c} clienti per il piano {limits['name']}. Effettua l'upgrade per aggiungerne altri."
        )


def check_deposit_limit(user: User, db: Session):
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    max_d = limits.get("max_deposits")
    if max_d is None:
        return
    count = db.query(Deposit).filter(Deposit.user_id == user.id, Deposit.deleted_at.is_(None)).count()
    if count >= max_d:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_d} depositi per il piano {limits['name']}. Effettua l'upgrade per aggiungerne altri."
        )


def check_vehicle_limit(user: User, db: Session):
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    max_v = limits.get("max_vehicles")
    if max_v is None:
        return
    count = db.query(Vehicle).filter(Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None)).count()
    if count >= max_v:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_v} mezzi per il piano {limits['name']}. Effettua l'upgrade per aggiungerne altri."
        )


def check_driver_limit(user: User, db: Session):
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    max_dr = limits.get("max_drivers")
    if max_dr is None:
        return
    count = db.query(Driver).filter(Driver.user_id == user.id, Driver.deleted_at.is_(None)).count()
    if count >= max_dr:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_dr} autisti per il piano {limits['name']}. Effettua l'upgrade per aggiungerne altri."
        )


def check_daily_route_limit(user: User, db: Session, data_giro: str):
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    max_r = limits.get("max_routes_per_day")
    if max_r is None:
        return
    count = (
        db.query(RoutePlan)
        .filter(RoutePlan.user_id == user.id, RoutePlan.data_giro == parse_date_value(data_giro))
        .count()
    )
    if count >= max_r:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_r} giri al giorno per il piano {limits['name']}. Effettua l'upgrade per crearne altri."
        )


def user_plan_info(user: User) -> dict:
    """Ritorna le info complete del piano per il frontend."""
    limits = get_plan_limits(user.plan or "starter")
    return {
        "plan": user.plan or "starter",
        "plan_name": limits["name"],
        "plan_status": get_user_plan_status(user),
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "limits": limits,
    }
