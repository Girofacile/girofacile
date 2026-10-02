"""
Servizio piani abbonamento.
Definisce i limiti per piano e le funzioni di controllo.
"""
from datetime import datetime
from fastapi import HTTPException
from ..core.utils import parse_date_value
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import User, Customer, Vehicle, Driver, Deposit, RoutePlan
from ..core.utils import local_today_iso

# -----------------------------------------------------------------------
# Definizione limiti per piano
# -----------------------------------------------------------------------
from .plan_catalog import PLAN_LIMITS, PLAN_PRICES


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
    if getattr(user, "billing_suspended", False):
        return "cancelled"
    status = user.plan_status or "trial"
    if status == "past_due":
        grace = getattr(user, "billing_grace_until", None)
        return "past_due" if grace and datetime.utcnow() < grace else "expired"
    if status == "trial":
        if user.trial_ends_at and datetime.utcnow() > user.trial_ends_at:
            return "expired"
    if status == "active":
        if user.plan_expires_at and datetime.utcnow() > user.plan_expires_at:
            return "expired"
    return status


def is_plan_active(user: User) -> bool:
    return get_user_plan_status(user) in ("trial", "active", "past_due")


def require_active_plan(user: User):
    """Lancia 403 se il piano dell'utente non è attivo."""
    if not is_plan_active(user):
        raise HTTPException(
            status_code=403,
            detail="Il tuo piano è scaduto. Rinnova l'abbonamento per continuare ad usare GiroFacile."
        )


def require_feature(user: User, feature: str):
    """Lancia 403 se la feature non è disponibile nel piano dell'utente."""
    if feature not in ("has_export", "has_reports"):
        require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    if not limits.get(feature, False):
        plan_name = limits["name"]
        raise HTTPException(
            status_code=403,
            detail=f"La funzionalità richiesta non è disponibile nel piano {plan_name}. Effettua l'upgrade per sbloccarla."
        )


def check_customer_limit(user: User, db: Session, additional: int = 1):
    """Controlla se l'utente ha raggiunto il limite clienti del piano."""
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    db.query(User).filter(User.id == user.id).with_for_update().first()
    max_c = limits.get("max_customers")
    if max_c is None:
        return  # illimitato
    count = db.query(Customer).filter(Customer.user_id == user.id, Customer.deleted_at.is_(None)).count()
    if additional > 0 and count + additional > max_c:
        raise HTTPException(
            status_code=403,
            detail=f"Hai raggiunto il limite di {max_c} clienti per il piano {limits['name']}. Effettua l'upgrade per aggiungerne altri."
        )


def check_deposit_limit(user: User, db: Session):
    require_active_plan(user)
    db.query(User).filter(User.id == user.id).with_for_update().first()
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


def is_electric_vehicle(alimentazione) -> bool:
    """Only fully electric vehicles qualify; hybrids and unknown values do not."""
    return str(alimentazione or "").strip().lower() == "elettrico"


def lock_vehicle_owner(user: User, db: Session) -> User:
    """Serialize fleet changes and refresh entitlements within the same transaction."""
    return db.query(User).filter(User.id == user.id).with_for_update().populate_existing().one()


def _vehicle_counts(user: User, db: Session) -> tuple[int, int]:
    counts = db.query(Vehicle.alimentazione, func.count(Vehicle.id)).filter(
        Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None)
    ).group_by(Vehicle.alimentazione).all()
    total = sum(int(count) for _, count in counts)
    electric = sum(int(count) for fuel, count in counts if is_electric_vehicle(fuel))
    return total, electric


def _vehicle_usage_report(user: User, total: int, electric: int, plan: str | None = None) -> dict:
    """Allocate bonus first; validate N <= standard and N + E <= standard + bonus."""
    plan = plan or user.plan or "starter"
    limits = get_plan_limits(plan)
    standard = limits.get("max_vehicles")
    bonus = max(0, int(limits.get("electric_vehicle_bonus") or 0))
    non_electric = total - electric
    bonus_used = min(electric, bonus)
    standard_used = non_electric + electric - bonus_used
    total_limit = None if standard is None else standard + bonus
    over_standard = 0 if standard is None else max(0, non_electric - standard)
    over_total = 0 if total_limit is None else max(0, total - total_limit)
    over_limit = bool(over_standard or over_total)
    standard_remaining = None if standard is None else max(0, standard - standard_used)
    total_remaining = None if total_limit is None else max(0, total_limit - total)
    bonus_remaining = max(0, bonus - bonus_used)
    active = is_plan_active(user)
    if over_limit:
        message = (
            f"I mezzi registrati superano i limiti del piano {limits['name']}: "
            f"{non_electric} non elettrici su {standard} slot standard, "
            f"{total} mezzi totali su {total_limit}. "
            "I dati sono conservati. Elimina i mezzi eccedenti, converti un mezzo "
            "non elettrico se appropriato oppure scegli un piano superiore "
            "prima di aggiungere altri mezzi."
        )
    elif standard_remaining == 0 and bonus_remaining:
        noun = "slot bonus disponibile" if bonus_remaining == 1 else "slot bonus disponibili"
        message = (
            "Hai raggiunto il limite dei mezzi inclusi nel tuo piano. "
            f"Hai ancora {bonus_remaining} {noun} per "
            f"{'un veicolo elettrico' if bonus_remaining == 1 else 'veicoli elettrici'}."
        )
    elif total_remaining == 0:
        message = (
            f"Hai raggiunto il limite di {total_limit} mezzi del piano {limits['name']}, "
            f"inclusi {bonus} bonus elettrici. Elimina un mezzo o scegli un piano superiore."
        )
    else:
        message = (
            f"GiroFacile incentiva la mobilità elettrica: il tuo piano include fino a "
            f"{bonus} {'veicolo elettrico aggiuntivo' if bonus == 1 else 'veicoli elettrici aggiuntivi'} "
            "senza consumare gli slot mezzi standard."
        )
    return {
        "plan": plan, "plan_name": limits["name"],
        "standard_limit": standard, "electric_bonus": bonus, "total_limit": total_limit,
        "total_used": total, "electric_used": electric, "non_electric_used": non_electric,
        "standard_used": standard_used, "bonus_used": bonus_used,
        "standard_remaining": standard_remaining, "bonus_remaining": bonus_remaining,
        "total_remaining": total_remaining,
        "can_add_electric": active and not over_limit and (total_remaining is None or total_remaining > 0),
        "can_add_non_electric": active and not over_limit and (standard_remaining is None or standard_remaining > 0),
        "over_limit": over_limit, "over_standard": over_standard, "over_total": over_total,
        "plan_active": active, "message": message,
    }


def vehicle_usage(user: User, db: Session, plan: str | None = None) -> dict:
    """One fleet quota report used by API, billing/downgrades and every client."""
    total, electric = _vehicle_counts(user, db)
    return _vehicle_usage_report(user, total, electric, plan)


def check_vehicle_limit(user: User, db: Session, alimentazione: str = "gasolio", vehicle: Vehicle | None = None):
    user = lock_vehicle_owner(user, db)
    require_active_plan(user)
    total, electric = _vehicle_counts(user, db)
    incoming_electric = is_electric_vehicle(alimentazione)
    if vehicle is not None:
        # A second concurrent edit may have changed the fuel while this call waited.
        db.refresh(vehicle)
        if vehicle.user_id != user.id or vehicle.deleted_at is not None:
            raise HTTPException(404, "Mezzo non trovato")
        previous_electric = is_electric_vehicle(vehicle.alimentazione)
        if previous_electric == incoming_electric or incoming_electric:
            return  # Same allocation or corrective conversion, including after downgrade.
        projected = _vehicle_usage_report(user, total, electric - 1)
        if projected["over_standard"]:
            raise HTTPException(
                403,
                "Non puoi cambiare questo mezzo elettrico a un'altra alimentazione: "
                f"supereresti i {projected['standard_limit']} slot standard del piano "
                f"{projected['plan_name']}. Libera uno slot standard o scegli un piano superiore. "
                "Gli slot bonus sono riservati ai veicoli elettrici."
            )
        return  # Total unchanged and non-electric vehicles still within the standard cap.
    projected = _vehicle_usage_report(user, total + 1, electric + int(incoming_electric))
    if projected["over_limit"]:
        current = _vehicle_usage_report(user, total, electric)
        if not incoming_electric and projected["over_standard"] and current["bonus_remaining"]:
            detail = current["message"]
        elif current["over_limit"]:
            detail = current["message"]
        else:
            detail = (
                f"Il piano {current['plan_name']} consente {current['standard_limit']} mezzi "
                f"standard e {current['electric_bonus']} bonus riservati ai veicoli elettrici "
                f"(massimo {current['total_limit']} mezzi). Hai raggiunto il limite "
                "disponibile per questa alimentazione. Elimina un mezzo o scegli un piano superiore."
            )
        raise HTTPException(403, detail)


def check_driver_limit(user: User, db: Session):
    require_active_plan(user)
    db.query(User).filter(User.id == user.id).with_for_update().first()
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


def check_daily_route_limit(user: User, db: Session, data_giro: str, exclude_route_id: int | None = None):
    require_active_plan(user)
    limits = get_plan_limits(user.plan or "starter")
    db.query(User).filter(User.id == user.id).with_for_update().first()
    max_r = limits.get("max_routes_per_day")
    if max_r is None:
        return
    count = (
        db.query(RoutePlan)
        .filter(RoutePlan.user_id == user.id, RoutePlan.data_giro == parse_date_value(data_giro))
        .filter(RoutePlan.id != exclude_route_id if exclude_route_id is not None else True)
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
        "price_eur": PLAN_PRICES[user.plan or "starter"]["price_eur"],
        "billing_source": getattr(user, "billing_source", None) or "legacy",
        "cancel_at_period_end": bool(getattr(user, "billing_cancel_at_period_end", False)),
        "grace_until": user.billing_grace_until.isoformat() if getattr(user, "billing_grace_until", None) else None,
        "pending_plan": getattr(user, "billing_pending_plan", None),
    }
