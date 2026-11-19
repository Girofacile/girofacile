"""Superadmin overview and company account management."""


from datetime import datetime, timedelta
from ..core.clock import utc_now
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.dependencies import is_admin_user, require_superadmin
from ..database import get_db
from ..core.utils import date_to_iso
from ..models import Customer, RoutePlan, SupportTicket, User
from ..services.plans import PLAN_LIMITS, get_user_plan_status, vehicle_usage, lock_vehicle_owner
from .admin_helpers import (
    PLAN_MRR,
    _activity,
    _require_perm,
    ticket_to_dict,
    user_to_dict,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_overview")
    all_users = db.query(User).all()
    non_admin = [u for u in all_users if not is_admin_user(u)]

    now = utc_now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    trial_active = [u for u in non_admin if get_user_plan_status(u) == "trial"]
    paying = [u for u in non_admin if get_user_plan_status(u) == "active" and u.billing_source == "stripe_live"]
    expired = [u for u in non_admin if get_user_plan_status(u) in ("expired", "cancelled")]
    new_this_month = [u for u in non_admin if u.created_at and u.created_at >= first_of_month]

    # MRR stimato dagli abbonamenti attivi
    mrr = sum(PLAN_MRR.get(u.plan or "starter", 0) for u in paying)

    # Distribuzione per piano
    by_plan = {}
    for u in non_admin:
        p = u.plan or "starter"
        by_plan[p] = by_plan.get(p, 0) + 1

    # Ticket
    open_tickets = db.query(SupportTicket).filter(SupportTicket.status == "aperto").count()
    total_tickets = db.query(SupportTicket).count()

    # Attività piattaforma
    total_routes = db.query(RoutePlan).count()
    total_customers = db.query(Customer).filter(Customer.deleted_at.is_(None)).count()
    routes_this_month = db.query(RoutePlan).filter(RoutePlan.created_at >= first_of_month).count()

    # Ultimi 6 mesi - nuovi iscritti per mese
    monthly_signups = []
    for i in range(5, -1, -1):
        start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
        count = sum(1 for u in non_admin if u.created_at and start <= u.created_at < end)
        monthly_signups.append({
            "mese": start.strftime("%b %Y"),
            "nuovi": count
        })

    # Ultimi iscritti
    recent_users = sorted(non_admin, key=lambda u: u.created_at or datetime.min, reverse=True)[:8]
    recent_tickets = db.query(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(5).all()

    return {
        "kpi": {
            "utenti_totali": len(non_admin),
            "trial_attivi": len(trial_active),
            "abbonamenti_paganti": len(paying),
            "scaduti_cancellati": len(expired),
            "nuovi_questo_mese": len(new_this_month),
            "mrr_stimato": mrr,
            "ticket_aperti": open_tickets,
            "ticket_totali": total_tickets,
            "giri_totali": total_routes,
            "clienti_totali": total_customers,
            "giri_questo_mese": routes_this_month,
        },
        "distribuzione_piani": [
            {"piano": k, "nome": PLAN_LIMITS.get(k, {}).get("name", k), "utenti": v}
            for k, v in by_plan.items()
        ],
        "andamento_iscrizioni": monthly_signups,
        "ultimi_iscritti": [user_to_dict(u, db) for u in recent_users],
        "ultimi_ticket": [ticket_to_dict(t, db) for t in recent_tickets],
    }


@router.get("/users")
def admin_users(
    q: str = "",
    plan: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_users")
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(
            User.username.ilike(like) |
            User.email.ilike(like) |
            User.company_name.ilike(like)
        )
    if plan:
        query = query.filter(User.plan == plan)
    rows = query.order_by(User.created_at.desc()).all()

    result = []
    for u in rows:
        if is_admin_user(u):
            continue
        real_status = get_user_plan_status(u)
        if status and real_status != status:
            continue
        result.append(user_to_dict(u, db))
    return result


@router.get("/users/{user_id}")
def admin_user_detail(user_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_users")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utente non trovato")
    base = user_to_dict(user, db)
    # Attività dettagliata
    routes = db.query(RoutePlan).filter(RoutePlan.user_id == user_id).order_by(RoutePlan.created_at.desc()).limit(5).all()
    base["recent_routes"] = [{
        "id": r.id, "nome": r.nome, "data_giro": date_to_iso(r.data_giro),
        "status": r.status, "consegne": len(r.deliveries or []),
        "km": r.totale_km,
    } for r in routes]
    base["tickets"] = [ticket_to_dict(t, db) for t in
                       db.query(SupportTicket).filter(SupportTicket.user_id == user_id).all()]
    return base


@router.put("/users/{user_id}/plan")
def admin_update_plan(user_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_users")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Utente non trovato")
    user = lock_vehicle_owner(user, db)
    # Un abbonamento Stripe che incassa ancora non si sovrascrive: si annulla prima su Stripe.
    # Uno annullato, rimborsato o mai pagato non blocca più l'assegnazione dal pannello.
    paying = user.plan_status in ("active", "past_due") and not user.billing_cancel_at_period_end
    if user.stripe_subscription_id and paying:
        raise HTTPException(409, "Account collegato a un abbonamento Stripe ancora attivo: annullalo prima su Stripe")
    reason = (payload.get("reason") or "Assegnazione amministrativa dal pannello").strip()[:500]
    complimentary = payload.get("complimentary") is True
    if user.stripe_subscription_id or user.stripe_customer_id:
        # L'account non dipende più da Stripe: i vecchi riferimenti restano solo nell'attività.
        reason += f" Stripe scollegato (cliente {user.stripe_customer_id or '-'}, abbonamento {user.stripe_subscription_id or '-'})."
        user.stripe_subscription_id = user.stripe_customer_id = None
        user.billing_checkout_id = user.billing_checkout_url = user.billing_checkout_expires = user.billing_checkout_plan = None
        user.billing_pending_plan = user.billing_change_key = None
        user.billing_cancel_at_period_end = False
        user.billing_grace_until = None
    user.billing_source = "complimentary" if complimentary else "manual"
    label = "Accesso gratuito senza scadenza" if complimentary else "Assegnazione manuale"
    _activity(db, superadmin.get("username"), "manual_plan_change", f"Account {user.id}: {user.plan} -> {payload.get('plan', user.plan)}. {label}. {reason}", "warning")
    valid_plans = ("starter", "business", "pro")
    valid_statuses = ("trial", "active", "expired", "cancelled")
    if payload.get("plan") in valid_plans:
        user.plan = payload["plan"]
    if payload.get("plan_status") in valid_statuses:
        user.plan_status = payload["plan_status"]
    if payload.get("plan_expires_at"):
        try:
            user.plan_expires_at = datetime.fromisoformat(payload["plan_expires_at"])
        except Exception:
            pass
    if complimentary:
        # Accesso gratuito: piano attivo finché non lo cambi tu, senza pagamento né scadenza.
        user.plan_status = "active"
        user.plan_expires_at = None
        user.billing_suspended = False
    db.commit()
    fleet = vehicle_usage(user, db)
    return {"ok": True, "plan": user.plan, "plan_status": user.plan_status,
            "vehicle_usage": fleet, "warning": fleet["message"] if fleet["over_limit"] else None}


@router.put("/users/{user_id}/disable")
def admin_toggle_user(user_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "suspend_users")
    """Disabilita o riattiva un utente impostando plan_status = cancelled o active."""
    user = db.get(User, user_id)
    if not user or is_admin_user(user):
        raise HTTPException(404, "Utente non trovato")
    disable = payload.get("disable", True)
    user.billing_suspended = bool(disable)
    if not user.stripe_subscription_id:
        user.plan_status = "cancelled" if disable else "active"
        user.billing_source = "manual"
    _activity(db, superadmin.get("username"), "account_suspension_changed", f"Account {user.id}: sospensione={bool(disable)}", "warning")
    db.commit()
    return {"ok": True, "plan_status": user.plan_status}


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_users")
    user = db.query(User).filter_by(id=user_id).with_for_update().populate_existing().first()
    if not user or is_admin_user(user):
        raise HTTPException(400, "Impossibile eliminare questo utente")
    # Blocca solo un abbonamento ancora vivo: uno annullato o scaduto lascia salvato
    # il suo identificativo ma non incassa più nulla.
    if user.stripe_subscription_id and user.plan_status not in ("cancelled", "expired"):
        raise HTTPException(409, "L'azienda ha un abbonamento Stripe ancora attivo: annullalo prima di eliminarla, "
                                 "altrimenti i pagamenti continuerebbero")
    delete_company_orders(db, user.id)
    _activity(db, superadmin.get("username"), "company_deleted", f"Eliminata azienda {user.id} con tutti i dati", "warning")
    db.delete(user)
    db.commit()
    return {"ok": True}


def delete_company_orders(db, user_id):
    """Gli ordini importati non si cancellano da soli con l'azienda: si tolgono qui, dai più dipendenti."""
    from ..order_models import (Order, OrderItem, OrderEvent, OrderImportRun, OrderSource, CustomerSourceMapping,
                                RouteOrderAssignment, OrderPlanningSelection, PlanningDraft)
    order_ids = db.query(Order.id).filter(Order.user_id == user_id)
    for model in (RouteOrderAssignment, OrderPlanningSelection, PlanningDraft):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
    for model in (OrderItem, OrderEvent):
        db.query(model).filter(model.order_id.in_(order_ids.scalar_subquery())).delete(synchronize_session=False)
    for model in (CustomerSourceMapping, Order, OrderImportRun, OrderSource):
        db.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
    db.flush()
