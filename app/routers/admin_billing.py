"""Admin billing: extracted from the SaaS administration router."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.dependencies import is_admin_user, require_superadmin
from ..database import get_db
from ..models import User
from ..services.plans import PLAN_LIMITS, get_user_plan_status
from ..services.api_usage import api_usage_summary
from ..services.platform_settings import google_maps_api_key, google_geocoding_enabled, google_routes_enabled, openai_api_key, openai_model, ai_enabled as platform_ai_enabled

from .admin_helpers import (
    PLAN_MRR,
    _require_perm,
    user_to_dict,
)

router = APIRouter()


@router.get("/api-usage")
def admin_api_usage(
    period: str = "today",
    service: str = "",
    start: str = "",
    end: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_revenue")
    data = api_usage_summary(db, period=period, service=service, start=start, end=end)
    data["ai"] = {
        "enabled": platform_ai_enabled(db),
        "api_key_configured": bool(openai_api_key(db)),
        "model": openai_model(db),
        "services": [
            {"key": "openai_route_explanation", "label": "AI spiegazione sequenza giro"},
            {"key": "openai_support_ticket_text", "label": "AI testo assistito ticket"},
            {"key": "openai_admin_error_analysis", "label": "AI analisi errori/ticket"},
            {"key": "openai_report_summary", "label": "AI report aziendale"},
        ],
    }
    data["google"] = {
        "api_key_configured": bool(google_maps_api_key(db)),
        "geocoding_enabled": bool(google_geocoding_enabled(db)),
        "routes_enabled": bool(google_routes_enabled(db)),
        "services": [
            {"key": "google_geocoding", "label": "Google Geocoding / Verifica indirizzi"},
            {"key": "google_routes_matrix", "label": "Google Routes API / Calcolo giri"},
            {"key": "google_maps_link", "label": "Link Google Maps"},
        ],
    }
    return data


@router.get("/revenue")
def admin_revenue(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_revenue")
    all_users = [u for u in db.query(User).all() if not is_admin_user(u)]
    paying = [u for u in all_users if get_user_plan_status(u) == "active"]
    trial = [u for u in all_users if get_user_plan_status(u) == "trial"]

    mrr = sum(PLAN_MRR.get(u.plan or "starter", 0) for u in paying)
    arr = mrr * 12

    by_plan = {}
    for u in paying:
        p = u.plan or "starter"
        info = by_plan.setdefault(p, {
            "piano": p,
            "nome": PLAN_LIMITS.get(p, {}).get("name", p),
            "utenti": 0,
            "prezzo": PLAN_MRR.get(p, 0),
            "mrr": 0,
        })
        info["utenti"] += 1
        info["mrr"] += PLAN_MRR.get(p, 0)

    trial_converting = [u for u in trial if u.trial_ends_at and
                        u.trial_ends_at - datetime.utcnow() <= timedelta(days=3)]

    return {
        "mrr": mrr,
        "arr": arr,
        "abbonamenti_attivi": len(paying),
        "trial_attivi": len(trial),
        "trial_in_scadenza": len(trial_converting),
        "breakdown_piani": list(by_plan.values()),
        "utenti_in_trial_scadenza": [user_to_dict(u, db) for u in trial_converting],
    }
