"""Admin users: extracted from the SaaS administration router."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.dependencies import is_admin_user, require_superadmin
from ..database import get_db
from ..core.utils import date_to_iso
from ..models import Customer, RoutePlan, SupportTicket, User
from ..services.plans import PLAN_LIMITS, get_user_plan_status

from .admin_helpers import (
    PLAN_MRR,
    _require_perm,
    ticket_to_dict,
    user_to_dict,
)

router = APIRouter()


@router.get("/overview")
def admin_overview(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_overview")
    all_users = db.query(User).all()
    non_admin = [u for u in all_users if not is_admin_user(u)]

    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    trial_active = [u for u in non_admin if get_user_plan_status(u) == "trial"]
    paying = [u for u in non_admin if get_user_plan_status(u) == "active"]
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
    db.commit()
    return {"ok": True, "plan": user.plan, "plan_status": user.plan_status}


@router.put("/users/{user_id}/disable")
def admin_toggle_user(user_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "suspend_users")
    """Disabilita o riattiva un utente impostando plan_status = cancelled o active."""
    user = db.get(User, user_id)
    if not user or is_admin_user(user):
        raise HTTPException(404, "Utente non trovato")
    disable = payload.get("disable", True)
    user.plan_status = "cancelled" if disable else "active"
    db.commit()
    return {"ok": True, "plan_status": user.plan_status}


@router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_users")
    user = db.get(User, user_id)
    if not user or is_admin_user(user):
        raise HTTPException(400, "Impossibile eliminare questo utente")
    db.delete(user)
    db.commit()
    return {"ok": True}
