"""Widget per iPhone del Super Admin (Scriptable, Widgy, Numerics…).

GET /api/widget/stats restituisce solo numeri aggregati della piattaforma, in sola lettura,
con una chiave dedicata (intestazione «Authorization: Bearer gfw_…»). La chiave si genera,
si mostra una sola volta e si revoca dal Super Admin; nel database resta solo la sua impronta.
"""
from collections import OrderedDict
from datetime import timedelta, timezone
import hashlib
import hmac
import secrets
import threading
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..core.clock import utc_now
from ..core.dependencies import is_admin_user, require_superadmin
from ..core.http_security import _client_ip
from ..core.utils import local_now, local_today
from ..database import get_db
from ..models import RoutePlan, SupportTicket, SystemErrorLog, User
from ..services.plans import get_user_plan_status
from .admin_helpers import PLAN_MRR, _activity, _require_perm, _set_setting_value, _setting_value

router = APIRouter(tags=["admin"])
KEY_HASH, KEY_CREATED, KEY_USED = "widget_key_sha256", "widget_key_created_at", "widget_key_last_used_at"
NO_STORE = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
_requests: OrderedDict = OrderedDict()
_lock = threading.Lock()


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _throttle(request: Request):
    """Al massimo 60 letture al minuto per indirizzo: il widget ne fa poche all'ora."""
    now, ip = time.monotonic(), _client_ip(request)
    with _lock:
        start, count = _requests.pop(ip, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        _requests[ip] = (start, count + 1)
        while len(_requests) > 5000:
            _requests.popitem(last=False)
        if count >= 60:
            raise HTTPException(429, "Riprova tra un minuto", headers={**NO_STORE, "Retry-After": "60"})


def widget_stats(db: Session) -> dict:
    """Numeri della piattaforma per il widget (solo conteggi, nessun dato personale)."""
    now = utc_now()
    today = local_today()
    companies = [u for u in db.query(User).all() if not is_admin_user(u)]
    status = {u.id: get_user_plan_status(u) for u in companies}
    paying = [u for u in companies if status[u.id] == "active" and u.billing_source == "stripe_live"]
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Mezzanotte italiana espressa in UTC, come le date salvate nel database.
    day_start = local_now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
    return {
        "aggiornato_alle": now.isoformat() + "Z",
        "ticket_aperti": db.query(SupportTicket).filter(SupportTicket.status == "aperto").count(),
        "ticket_nuovi_oggi": db.query(SupportTicket).filter(SupportTicket.created_at >= day_start).count(),
        "aziende_registrate": len(companies),
        "aziende_in_prova": sum(1 for u in companies if status[u.id] == "trial"),
        "aziende_abbonate": len(paying),
        "nuove_aziende_mese": sum(1 for u in companies if u.created_at and u.created_at >= month_start),
        "mrr_stimato": sum(PLAN_MRR.get(u.plan or "starter", 0) for u in paying),
        "giri_in_corso": db.query(RoutePlan).filter(RoutePlan.status == "in_corso").count(),
        "giri_oggi": db.query(RoutePlan).filter(RoutePlan.data_giro == today, RoutePlan.status != "bozza").count(),
        "errori_24h": db.query(SystemErrorLog).filter(SystemErrorLog.created_at >= now - timedelta(hours=24)).count(),
    }


@router.get("/api/widget/stats")
def read_widget_stats(request: Request, authorization: str = Header(default=""), db: Session = Depends(get_db)):
    _throttle(request)
    stored = _setting_value(db, KEY_HASH, "")
    key = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not stored or not key.startswith("gfw_") or not hmac.compare_digest(_digest(key), stored):
        raise HTTPException(401, "Chiave del widget non valida o revocata", headers=NO_STORE)
    _set_setting_value(db, KEY_USED, utc_now().isoformat())
    db.commit()
    return JSONResponse(widget_stats(db), headers=NO_STORE)


def _key_state(db: Session) -> dict:
    return {"configured": bool(_setting_value(db, KEY_HASH, "")),
            "created_at": _setting_value(db, KEY_CREATED, "") or None,
            "last_used_at": _setting_value(db, KEY_USED, "") or None}


@router.get("/api/admin/widget-key")
def get_widget_key(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    return _key_state(db)


@router.post("/api/admin/widget-key")
def create_widget_key(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    """Nuova chiave: sostituisce la precedente e si mostra una sola volta."""
    _require_perm(superadmin, "manage_service_keys")
    key = "gfw_" + secrets.token_urlsafe(32)
    _set_setting_value(db, KEY_HASH, _digest(key))
    _set_setting_value(db, KEY_CREATED, utc_now().isoformat())
    _set_setting_value(db, KEY_USED, "")
    _activity(db, superadmin.get("username"), "widget_key_created", "Generata la chiave del widget iPhone", "warning")
    db.commit()
    return {**_key_state(db), "key": key}


@router.delete("/api/admin/widget-key")
def revoke_widget_key(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_service_keys")
    for name in (KEY_HASH, KEY_CREATED, KEY_USED):
        _set_setting_value(db, name, "")
    _activity(db, superadmin.get("username"), "widget_key_revoked", "Revocata la chiave del widget iPhone", "warning")
    db.commit()
    return _key_state(db)
