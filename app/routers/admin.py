"""
Admin router - Pannello di controllo SaaS per il proprietario.
Accessibile solo dall'utente admin.
"""
from datetime import datetime, timedelta
import csv
import io
import json
import os
import platform
import shutil
import secrets
import string
import sys
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from ..core.config import PLAN_PRICES, SUPERADMIN_USERNAME, APP_BASE_URL, ERROR_NOTIFICATIONS_EMAIL, GOOGLE_MAPS_API_KEY
from ..core.dependencies import is_admin_user, require_superadmin
from ..database import get_db, engine, database_kind
from ..core.utils import date_to_iso, time_to_hhmm
from ..models import Customer, Delivery, Driver, RoutePlan, SupportTicket, SystemErrorLog, User, Vehicle, SaaSPlatformSetting, SuperAdminProfile, SuperAdminActivityLog, SuperAdminCollaborator, ApiUsageLog
from ..services.plans import PLAN_LIMITS, get_user_plan_status
from ..services.error_monitor import error_log_to_dict
from ..services.email import send_ticket_resolved, send_superadmin_collaborator_invitation
from ..services.api_usage import api_usage_summary
from ..services.ai_assistant import run_ai_text
from ..services.platform_settings import google_maps_api_key, google_geocoding_enabled, google_routes_enabled, openai_api_key, openai_model, ai_enabled as platform_ai_enabled
from ..core.security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])

PLAN_MRR = {"starter": 19, "business": 39, "pro": 79}


COLLABORATOR_PERMISSIONS = {
    "view_overview": "Vedere overview e KPI generali",
    "view_users": "Vedere aziende/clienti",
    "manage_users": "Modificare piani e dati aziende",
    "suspend_users": "Sospendere o riattivare aziende",
    "view_tickets": "Vedere ticket assistenza",
    "manage_tickets": "Aggiornare e chiudere ticket",
    "view_errors": "Vedere errori sistema",
    "manage_errors": "Aggiornare stato errori",
    "view_revenue": "Vedere revenue, abbonamenti e consumi API",
    "view_activity": "Vedere registro attività",
    "manage_platform": "Modificare impostazioni SaaS",
    "manage_collaborators": "Creare e gestire collaboratori",
    "view_server_maintenance": "Vedere Server, chiavi e manutenzione",
    "manage_service_keys": "Gestire chiavi e servizi collegati",
    "test_service_connections": "Eseguire test connessioni servizi",
    "create_backups": "Creare backup database",
    "download_backups": "Scaricare backup",
    "restart_application": "Riavviare applicazione",
    "toggle_maintenance": "Attivare modalità manutenzione",
    "advanced_server_access": "Accesso avanzato server",
    "view_database": "Vedere Database Viewer in sola lettura",
    "export_database": "Esportare tabelle database in CSV",
}

def _has_perm(superadmin: dict, perm: str) -> bool:
    if not superadmin:
        return False
    if superadmin.get("role") == "superadmin":
        return True
    perms = superadmin.get("permissions") or {}
    return bool(perms.get("all") or perms.get(perm))

def _require_perm(superadmin: dict, perm: str):
    if not _has_perm(superadmin, perm):
        raise HTTPException(status_code=403, detail="Permesso collaboratore non abilitato")

def _temporary_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def _permissions_to_json(payload: dict) -> str:
    permissions = payload.get("permissions") or {}
    clean = {key: bool(permissions.get(key)) for key in COLLABORATOR_PERMISSIONS}
    return json.dumps(clean, ensure_ascii=False)

def _collaborator_permissions(c: SuperAdminCollaborator) -> dict:
    try:
        return json.loads(c.permissions_json or "{}")
    except Exception:
        return {}

def collaborator_to_dict(c: SuperAdminCollaborator) -> dict:
    return {
        "id": c.id,
        "full_name": c.full_name,
        "email": c.email,
        "phone": c.phone or "",
        "role_label": c.role_label or "Collaboratore",
        "permissions": _collaborator_permissions(c),
        "is_active": bool(c.is_active),
        "invitation_sent": bool(c.invitation_sent),
        "invited_at": c.invited_at.isoformat() if c.invited_at else None,
        "last_access_at": c.last_access_at.isoformat() if c.last_access_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _setting_value(db: Session, key: str, default: str = "") -> str:
    row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == key).first()
    return row.value if row and row.value is not None else default


def _set_setting_value(db: Session, key: str, value: str | None):
    row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == key).first()
    if not row:
        row = SaaSPlatformSetting(key=key, value=value or "")
        db.add(row)
    else:
        row.value = value or ""
        row.updated_at = datetime.utcnow()
    return row


def _bool_to_str(value) -> str:
    return "true" if bool(value) else "false"


def _str_to_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "si", "sì", "on")


def _get_or_create_superadmin_profile(db: Session, username: str = None) -> SuperAdminProfile:
    username = (username or SUPERADMIN_USERNAME or "admin").strip() or "admin"
    profile = db.query(SuperAdminProfile).filter(SuperAdminProfile.username == username).first()
    if not profile:
        initials = ''.join([part[:1] for part in username.replace('.', ' ').replace('_', ' ').split()])[:2].upper() or "A"
        profile = SuperAdminProfile(
            username=username,
            display_name="Proprietario GiroFacile",
            email=ERROR_NOTIFICATIONS_EMAIL or "",
            avatar_initials=initials,
            notify_errors=True,
            notify_tickets=True,
            notify_new_companies=True,
            last_access_at=datetime.utcnow(),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _profile_to_dict(profile: SuperAdminProfile) -> dict:
    return {
        "username": profile.username,
        "display_name": profile.display_name or profile.username,
        "email": profile.email or "",
        "phone": profile.phone or "",
        "avatar_initials": profile.avatar_initials or (profile.username[:1].upper() if profile.username else "A"),
        "notify_errors": bool(profile.notify_errors),
        "notify_tickets": bool(profile.notify_tickets),
        "notify_new_companies": bool(profile.notify_new_companies),
        "last_access_at": profile.last_access_at.isoformat() if profile.last_access_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _activity(db: Session, actor: str, action: str, description: str = "", severity: str = "info"):
    try:
        db.add(SuperAdminActivityLog(actor_username=actor, action=action, description=description, severity=severity))
    except Exception:
        pass



def _mask_secret(value: str | None, left: int = 6, right: int = 4) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= left + right:
        return value[:2] + "***"
    return value[:left] + "•" * 10 + value[-right:]


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _database_file_path() -> Path:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        return Path(db_url.replace("sqlite:///", "")).resolve()
    default = _project_root() / "data" / "girofacile.db"
    return default.resolve()


def _backup_dir() -> Path:
    path = _project_root() / "data" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _list_backups() -> list[dict]:
    items = []
    backup_files = list(_backup_dir().glob("*.dump")) + list(_backup_dir().glob("*.sql")) + list(_backup_dir().glob("*.zip"))
    for f in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        st = f.stat()
        items.append({
            "filename": f.name,
            "size_bytes": st.st_size,
            "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
        })
    return items


def _safe_backup_name(filename: str) -> Path:
    clean = Path(filename).name
    path = (_backup_dir() / clean).resolve()
    if not str(path).startswith(str(_backup_dir().resolve())) or not path.exists() or path.suffix.lower() != ".zip":
        raise HTTPException(404, "Backup non trovato")
    return path


def _service_key_status(db: Session) -> list[dict]:
    google_key = google_maps_api_key(db)
    openai_key = openai_api_key(db)
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    stripe_key = _setting_value(db, "stripe_secret_key", os.getenv("STRIPE_SECRET_KEY", ""))
    shopify_domain = _setting_value(db, "shopify_domain", "")
    backup_target = _setting_value(db, "backup_storage_target", "locale")
    return [
        {"key":"google", "name":"Google Maps Platform", "configured": bool(google_key), "masked": _mask_secret(google_key), "details":"Geocoding, verifica indirizzi, Routes API", "last_error":"Controlla Errori sistema / Consumi API"},
        {"key":"openai", "name":"OpenAI / AI", "configured": bool(openai_key), "masked": _mask_secret(openai_key), "details":"Spiegazione giri, ticket, report AI", "last_error":"Controlla Consumi API e chiavi"},
        {"key":"smtp", "name":"SMTP Email", "configured": bool(smtp_host and smtp_user and smtp_password), "masked": _mask_secret(smtp_user), "details": f"Host: {smtp_host or 'non configurato'}", "last_error":"Errore registrato se password SMTP mancante o invio fallito"},
        {"key":"stripe", "name":"Stripe / Pagamenti", "configured": bool(stripe_key), "masked": _mask_secret(stripe_key), "details":"Preparato per abbonamenti e fatture", "last_error":"Non ancora collegato a billing reale"},
        {"key":"shopify", "name":"Shopify", "configured": bool(shopify_domain), "masked": shopify_domain, "details":"Preparato per settore e-commerce", "last_error":"Integrazione API reale da completare"},
        {"key":"backup", "name":"Backup storage", "configured": True, "masked": backup_target, "details":"Backup locale database", "last_error":""},
    ]


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def user_to_dict(u: User, db: Session) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email or "",
        "company_name": u.company_name or "",
        "company_email": u.company_email or u.email or "",
        "company_phone": u.company_phone or "",
        "company_vat": u.company_vat or "",
        "company_sector": u.company_sector or u.company_activity_type or "",
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "is_admin": is_admin_user(u),
        "plan": u.plan or "starter",
        "plan_status": get_user_plan_status(u),
        "plan_status_raw": u.plan_status or "trial",
        "trial_ends_at": u.trial_ends_at.isoformat() if u.trial_ends_at else None,
        "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
        "stripe_customer_id": u.stripe_customer_id or "",
        "stripe_subscription_id": u.stripe_subscription_id or "",
        "customers_count": db.query(Customer).filter(Customer.user_id == u.id, Customer.deleted_at.is_(None)).count(),
        "routes_count": db.query(RoutePlan).filter(RoutePlan.user_id == u.id).count(),
        "vehicles_count": db.query(Vehicle).filter(Vehicle.user_id == u.id, Vehicle.deleted_at.is_(None)).count(),
        "drivers_count": db.query(Driver).filter(Driver.user_id == u.id, Driver.deleted_at.is_(None)).count(),
    }


def ticket_to_dict(t: SupportTicket, db: Session) -> dict:
    linked = db.get(User, t.user_id) if t.user_id else None
    return {
        "id": t.id,
        "tipo": t.tipo,
        "email": t.email,
        "company_email": linked.company_email if linked else None,
        "account_email": linked.email if linked else None,
        "oggetto": t.oggetto or "",
        "messaggio": t.messaggio or "",
        "status": t.status,
        "admin_note": t.admin_note or "",
        "system_error_id": getattr(t, "system_error_id", None),
        "notify_on_resolution": bool(getattr(t, "notify_on_resolution", True)),
        "resolved_email_sent": bool(getattr(t, "resolved_email_sent", False)),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "user_id": linked.id if linked else None,
        "username": linked.username if linked else None,
        "company_name": linked.company_name if linked else None,
        "plan": linked.plan if linked else None,
    }





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

# -----------------------------------------------------------------------
# Profilo Super Admin / Impostazioni SaaS
# -----------------------------------------------------------------------

@router.get("/profile")
def admin_profile(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_platform")
    profile = _get_or_create_superadmin_profile(db, superadmin.get("username"))
    profile.last_access_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return _profile_to_dict(profile)


@router.put("/profile")
def admin_update_profile(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_platform")
    profile = _get_or_create_superadmin_profile(db, superadmin.get("username"))
    profile.display_name = (payload.get("display_name") or profile.display_name or "").strip()[:160]
    profile.email = (payload.get("email") or "").strip()[:200]
    profile.phone = (payload.get("phone") or "").strip()[:80]
    initials = (payload.get("avatar_initials") or profile.avatar_initials or "A").strip().upper()[:4]
    profile.avatar_initials = initials or "A"
    profile.notify_errors = bool(payload.get("notify_errors", profile.notify_errors))
    profile.notify_tickets = bool(payload.get("notify_tickets", profile.notify_tickets))
    profile.notify_new_companies = bool(payload.get("notify_new_companies", profile.notify_new_companies))
    profile.updated_at = datetime.utcnow()
    _activity(db, superadmin.get("username"), "superadmin_profile_updated", "Profilo Super Admin aggiornato")
    db.commit()
    db.refresh(profile)
    return _profile_to_dict(profile)


@router.get("/platform-settings")
def admin_platform_settings(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_platform")
    defaults = {
        "platform_name": "GiroFacile",
        "support_email": "info@girofacile.it",
        "error_notification_email": ERROR_NOTIFICATIONS_EMAIL or "info@girofacile.it",
        "main_domain": APP_BASE_URL or "https://girofacile.it",
        "maintenance_mode": "false",
        "registrations_enabled": "true",
        "trial_days": "14",
        "default_plan": "starter",
        "support_phone": "",
        "ai_enabled": "false",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "ai_monthly_limit_business": "1500",
        "ai_monthly_limit_pro": "3000",
        "google_maps_api_key": GOOGLE_MAPS_API_KEY or "",
        "google_geocoding_enabled": "true" if GOOGLE_MAPS_API_KEY else "false",
        "google_routes_enabled": "true" if GOOGLE_MAPS_API_KEY else "false",
        "stripe_secret_key": os.getenv("STRIPE_SECRET_KEY", ""),
        "shopify_domain": "",
        "backup_storage_target": "locale",
        "backup_frequency": "manuale",
        "server_console_url": "",
    }
    return {key: _setting_value(db, key, value) for key, value in defaults.items()}


@router.put("/platform-settings")
def admin_update_platform_settings(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_platform")
    allowed = {
        "platform_name", "support_email", "error_notification_email", "main_domain",
        "maintenance_mode", "registrations_enabled", "trial_days", "default_plan", "support_phone",
        "ai_enabled", "openai_api_key", "openai_model", "ai_monthly_limit_business", "ai_monthly_limit_pro",
        "google_maps_api_key", "google_geocoding_enabled", "google_routes_enabled", "stripe_secret_key", "shopify_domain", "backup_storage_target", "backup_frequency", "server_console_url"
    }
    for key in allowed:
        if key not in payload:
            continue
        value = payload.get(key)
        if key in ("maintenance_mode", "registrations_enabled", "ai_enabled", "google_geocoding_enabled", "google_routes_enabled"):
            value = _bool_to_str(value)
        if key == "trial_days":
            try:
                value = str(max(0, min(int(value), 365)))
            except Exception:
                value = "14"
        _set_setting_value(db, key, str(value or "").strip())
    _activity(db, superadmin.get("username"), "platform_settings_updated", "Impostazioni SaaS aggiornate")
    db.commit()
    return admin_platform_settings(db, superadmin)


@router.get("/activity")
def admin_activity(limit: int = 80, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_activity")
    limit = max(1, min(limit, 200))
    rows = db.query(SuperAdminActivityLog).order_by(SuperAdminActivityLog.created_at.desc()).limit(limit).all()
    return [{
        "id": r.id,
        "actor_username": r.actor_username or "",
        "action": r.action,
        "description": r.description or "",
        "severity": r.severity,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]




# -----------------------------------------------------------------------
# Collaboratori Super Admin
# -----------------------------------------------------------------------

@router.get("/collaborator-permissions")
def admin_collaborator_permissions(superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    return COLLABORATOR_PERMISSIONS


@router.get("/collaborators")
def admin_collaborators(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    rows = db.query(SuperAdminCollaborator).order_by(SuperAdminCollaborator.created_at.desc()).all()
    return [collaborator_to_dict(c) for c in rows]


@router.post("/collaborators")
def admin_create_collaborator(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    if len(full_name) < 2:
        raise HTTPException(400, "Inserisci il nome del collaboratore")
    if "@" not in email:
        raise HTTPException(400, "Inserisci una email valida")
    exists = db.query(SuperAdminCollaborator).filter(SuperAdminCollaborator.email == email).first()
    if exists:
        raise HTTPException(400, "Esiste già un collaboratore con questa email")
    temporary = _temporary_password()
    permissions_json = _permissions_to_json(payload)
    collab = SuperAdminCollaborator(
        full_name=full_name,
        email=email,
        phone=(payload.get("phone") or "").strip(),
        role_label=(payload.get("role_label") or "Collaboratore").strip(),
        password_hash=hash_password(temporary),
        permissions_json=permissions_json,
        is_active=bool(payload.get("is_active", True)),
        invited_at=datetime.utcnow(),
    )
    db.add(collab)
    db.commit()
    db.refresh(collab)
    perms = _collaborator_permissions(collab)
    labels = [label for key, label in COLLABORATOR_PERMISSIONS.items() if perms.get(key)]
    sent = send_superadmin_collaborator_invitation(
        email, full_name, temporary, ", ".join(labels[:4]) + ("..." if len(labels) > 4 else "") or "Nessun permesso operativo",
        f"{APP_BASE_URL.rstrip('/')}/admin/login"
    )
    collab.invitation_sent = bool(sent)
    _activity(db, superadmin.get("username"), "collaborator_created", f"Creato collaboratore {full_name} ({email})")
    db.commit()
    db.refresh(collab)
    result = collaborator_to_dict(collab)
    result["temporary_password"] = temporary if not sent else ""
    result["email_sent"] = bool(sent)
    return result


@router.put("/collaborators/{collaborator_id}")
def admin_update_collaborator(collaborator_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    collab = db.get(SuperAdminCollaborator, collaborator_id)
    if not collab:
        raise HTTPException(404, "Collaboratore non trovato")
    collab.full_name = (payload.get("full_name") or collab.full_name).strip()[:180]
    collab.phone = (payload.get("phone") or "").strip()[:80]
    collab.role_label = (payload.get("role_label") or "Collaboratore").strip()[:120]
    collab.permissions_json = _permissions_to_json(payload)
    collab.is_active = bool(payload.get("is_active", collab.is_active))
    collab.updated_at = datetime.utcnow()
    _activity(db, superadmin.get("username"), "collaborator_updated", f"Aggiornato collaboratore {collab.full_name}")
    db.commit()
    db.refresh(collab)
    return collaborator_to_dict(collab)


@router.post("/collaborators/{collaborator_id}/resend")
def admin_resend_collaborator(collaborator_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    collab = db.get(SuperAdminCollaborator, collaborator_id)
    if not collab:
        raise HTTPException(404, "Collaboratore non trovato")
    temporary = _temporary_password()
    collab.password_hash = hash_password(temporary)
    collab.invited_at = datetime.utcnow()
    perms = _collaborator_permissions(collab)
    labels = [label for key, label in COLLABORATOR_PERMISSIONS.items() if perms.get(key)]
    sent = send_superadmin_collaborator_invitation(
        collab.email, collab.full_name, temporary, ", ".join(labels[:4]) + ("..." if len(labels) > 4 else "") or "Nessun permesso operativo",
        f"{APP_BASE_URL.rstrip('/')}/admin/login"
    )
    collab.invitation_sent = bool(sent)
    collab.updated_at = datetime.utcnow()
    _activity(db, superadmin.get("username"), "collaborator_invitation_resent", f"Reinvitato collaboratore {collab.full_name}")
    db.commit()
    result = collaborator_to_dict(collab)
    result["temporary_password"] = temporary if not sent else ""
    result["email_sent"] = bool(sent)
    return result


@router.delete("/collaborators/{collaborator_id}")
def admin_delete_collaborator(collaborator_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_collaborators")
    collab = db.get(SuperAdminCollaborator, collaborator_id)
    if not collab:
        raise HTTPException(404, "Collaboratore non trovato")
    _activity(db, superadmin.get("username"), "collaborator_deleted", f"Eliminato collaboratore {collab.full_name}", "warning")
    db.delete(collab)
    db.commit()
    return {"ok": True}



# -----------------------------------------------------------------------
# Database Viewer v71 - helper sicuri
# -----------------------------------------------------------------------

SENSITIVE_DB_FIELD_PATTERNS = (
    "password", "password_hash", "token", "secret", "api_key", "apikey",
    "key", "smtp_password", "reset", "session", "cookie", "authorization",
    "access", "refresh", "credential", "pepper"
)

DATABASE_VIEWER_EXCLUDED_TABLES = {
    }


def _database_kind_label() -> str:
    try:
        return database_kind()
    except Exception:
        return "unknown"


def _db_inspector():
    return inspect(engine)


def _allowed_database_tables() -> list[str]:
    insp = _db_inspector()
    tables = []
    for name in insp.get_table_names():
        lname = name.lower()
        if lname.startswith("pg_") or lname.startswith("sql_") or lname in DATABASE_VIEWER_EXCLUDED_TABLES:
            continue
        tables.append(name)
    return sorted(tables)


def _is_sensitive_db_column(column: str) -> bool:
    c = (column or "").lower()
    return any(pattern in c for pattern in SENSITIVE_DB_FIELD_PATTERNS)


def _mask_db_value(column: str, value):
    if value is None:
        return None
    if _is_sensitive_db_column(column):
        text = str(value)
        if not text:
            return ""
        return "••••••••••••"
    if isinstance(value, bytes):
        return f"<BLOB {len(value)} byte>"
    text = str(value)
    if len(text) > 600:
        return text[:600] + "…"
    return value


def _safe_db_table_name(table_name: str) -> str:
    table_name = (table_name or "").strip()
    if not table_name:
        raise HTTPException(400, "Tabella non indicata")
    allowed = _allowed_database_tables()
    if table_name not in allowed:
        raise HTTPException(404, "Tabella non trovata o non visualizzabile")
    return table_name


def _db_table_columns(table_name: str) -> list[dict]:
    insp = _db_inspector()
    pk_cols = set()
    try:
        pk_cols = set((insp.get_pk_constraint(table_name) or {}).get("constrained_columns") or [])
    except Exception:
        pk_cols = set()
    cols = []
    for col in insp.get_columns(table_name):
        name = col.get("name")
        cols.append({
            "name": name,
            "type": str(col.get("type") or ""),
            "notnull": not bool(col.get("nullable", True)),
            "default": str(col.get("default") or "") if col.get("default") is not None else None,
            "primary_key": name in pk_cols,
            "sensitive": _is_sensitive_db_column(name),
        })
    return cols


def _db_table_summary(table_name: str) -> dict:
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    with engine.connect() as conn:
        count = conn.execute(text(f"SELECT COUNT(*) AS c FROM {qtable}")).scalar()
    columns = _db_table_columns(table_name)
    return {
        "name": table_name,
        "rows": int(count or 0),
        "columns_count": len(columns),
        "sensitive_columns": [c["name"] for c in columns if c["sensitive"]],
    }

# -----------------------------------------------------------------------
# Server / Manutenzione v69
# -----------------------------------------------------------------------

@router.get("/server-maintenance")
def admin_server_maintenance(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    root = _project_root()
    usage = shutil.disk_usage(root)
    backups = _list_backups()
    return {
        "environment": os.getenv("APP_ENV", "locale/produzione"),
        "version": "v72",
        "app": {
            "status": "online",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "root": str(root),
            "base_url": APP_BASE_URL,
        },
        "database": {
            "status": "raggiungibile",
            "type": _database_kind_label(),
            "url_masked": _mask_secret(os.getenv("DATABASE_URL", ""), left=18, right=12),
            "host": getattr(engine.url, "host", None),
            "database": getattr(engine.url, "database", None),
            "pool_size": os.getenv("DB_POOL_SIZE", "5"),
        },
        "disk": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        },
        "settings": {
            "maintenance_mode": _str_to_bool(_setting_value(db, "maintenance_mode", "false")),
            "backup_frequency": _setting_value(db, "backup_frequency", "manuale"),
            "backup_storage_target": _setting_value(db, "backup_storage_target", "locale"),
            "server_console_url": _setting_value(db, "server_console_url", ""),
        },
        "services": _service_key_status(db),
        "backups": backups,
        "last_backup": backups[0] if backups else None,
    }


@router.put("/server-maintenance/settings")
def admin_server_maintenance_settings(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    # Impostazioni generali server: richiedono permesso piattaforma/manutenzione.
    _require_perm(superadmin, "view_server_maintenance")
    if "maintenance_mode" in payload:
        _require_perm(superadmin, "toggle_maintenance")
        _set_setting_value(db, "maintenance_mode", _bool_to_str(payload.get("maintenance_mode")))
        _activity(db, superadmin.get("username"), "maintenance_mode_updated", f"Modalità manutenzione: {bool(payload.get('maintenance_mode'))}", "warning")
    if "backup_frequency" in payload:
        _require_perm(superadmin, "create_backups")
        _set_setting_value(db, "backup_frequency", str(payload.get("backup_frequency") or "manuale")[:80])
    if "backup_storage_target" in payload:
        _require_perm(superadmin, "create_backups")
        _set_setting_value(db, "backup_storage_target", str(payload.get("backup_storage_target") or "locale")[:120])
    if "server_console_url" in payload:
        _require_perm(superadmin, "advanced_server_access")
        _set_setting_value(db, "server_console_url", str(payload.get("server_console_url") or "")[:500])
    db.commit()
    return admin_server_maintenance(db, superadmin)


@router.put("/server-maintenance/keys")
def admin_server_maintenance_keys(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_service_keys")
    allowed = {"google_maps_api_key", "openai_api_key", "stripe_secret_key", "shopify_domain"}
    changed = []
    for key in allowed:
        if key in payload:
            _set_setting_value(db, key, str(payload.get(key) or "").strip())
            changed.append(key)
    _activity(db, superadmin.get("username"), "service_keys_updated", "Aggiornate chiavi servizi: " + ", ".join(changed), "warning")
    db.commit()
    return {"ok": True, "services": _service_key_status(db)}


@router.post("/server-maintenance/test-service")
def admin_server_test_service(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "test_service_connections")
    service = (payload.get("service") or "").strip().lower()
    statuses = {s["key"]: s for s in _service_key_status(db)}
    if service not in statuses:
        raise HTTPException(400, "Servizio non riconosciuto")
    row = statuses[service]
    ok = bool(row.get("configured"))
    _activity(db, superadmin.get("username"), "service_connection_test", f"Test servizio {row.get('name')}: {'ok' if ok else 'non configurato'}")
    return {
        "service": service,
        "ok": ok,
        "message": "Configurazione presente. Il test reale API può essere esteso nella prossima versione." if ok else "Servizio non configurato o chiave mancante.",
    }


@router.post("/server-maintenance/backups")
def admin_create_backup(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "create_backups")
    import subprocess
    result = subprocess.run([sys.executable, "scripts/backup_database.py"], cwd=str(_project_root()), capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(400, result.stderr.strip() or result.stdout.strip() or "Backup PostgreSQL non riuscito")
    backups_now = _list_backups()
    if not backups_now:
        raise HTTPException(400, "Backup completato ma file non trovato nella cartella backup")
    out = _backup_dir() / backups_now[0]["filename"]
    _activity(db, superadmin.get("username"), "database_backup_created", f"Creato backup PostgreSQL {out.name}")
    db.commit()
    return {"ok": True, "backup": {"filename": out.name, "size_bytes": out.stat().st_size, "created_at": datetime.fromtimestamp(out.stat().st_mtime).isoformat()}, "backups": _list_backups()}


@router.get("/server-maintenance/backups/{filename}")
def admin_download_backup(filename: str, superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "download_backups")
    path = _safe_backup_name(filename)
    return FileResponse(str(path), media_type="application/octet-stream", filename=path.name)


@router.post("/server-maintenance/restart-app")
def admin_restart_app(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "restart_application")
    _activity(db, superadmin.get("username"), "restart_requested", "Richiesto riavvio applicazione da Super Admin", "warning")
    db.commit()
    return {"ok": True, "message": "Richiesta registrata. In produzione il comando reale va collegato a systemd con permessi limitati."}


@router.post("/server-maintenance/advanced-access")
def admin_advanced_server_access(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "advanced_server_access")
    host = (payload.get("host") or "").strip()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not host or not username or not password:
        raise HTTPException(400, "Inserisci host, username e password server")
    _activity(db, superadmin.get("username"), "advanced_server_access_attempt", f"Accesso avanzato richiesto per {username}@{host}", "warning")
    db.commit()
    return {
        "ok": True,
        "message": "Accesso validato lato pannello. Per aprire una console reale collega un terminale esterno protetto e imposta l'URL nella sezione Server / Manutenzione. La password non viene salvata.",
    }



# -----------------------------------------------------------------------
# Database Viewer v71
# -----------------------------------------------------------------------

@router.get("/database-viewer/tables")
def admin_database_tables(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_database")
    tables = []
    for name in _allowed_database_tables():
        try:
            tables.append(_db_table_summary(name))
        except Exception:
            tables.append({"name": name, "rows": 0, "columns_count": 0, "sensitive_columns": []})
    _activity(db, superadmin.get("username"), "database_viewer_opened", "Aperto Database Viewer PostgreSQL", "warning")
    db.commit()
    return {"tables": tables, "masking_enabled": True, "database_type": _database_kind_label()}


@router.get("/database-viewer/table/{table_name}")
def admin_database_table(
    table_name: str,
    page: int = 1,
    page_size: int = 50,
    q: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_database")
    page = max(1, int(page or 1))
    page_size = max(10, min(200, int(page_size or 50)))
    q_text = (q or "").strip()
    table_name = _safe_db_table_name(table_name)
    columns = _db_table_columns(table_name)
    column_names = [c["name"] for c in columns]
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    where_sql = ""
    params = {}
    if q_text and column_names:
        searchable = [c for c in column_names if not _is_sensitive_db_column(c)]
        if searchable:
            clauses = []
            for i, col in enumerate(searchable):
                pname = f"q{i}"
                clauses.append(f"CAST({preparer.quote(col)} AS TEXT) ILIKE :{pname}")
                params[pname] = f"%{q_text}%"
            where_sql = " WHERE " + " OR ".join(clauses)
    total_sql = text(f"SELECT COUNT(*) AS c FROM {qtable}{where_sql}")
    params_page = dict(params)
    params_page.update({"limit": page_size, "offset": (page - 1) * page_size})
    rows_sql = text(f"SELECT * FROM {qtable}{where_sql} LIMIT :limit OFFSET :offset")
    clean_rows = []
    with engine.connect() as conn:
        total = conn.execute(total_sql, params).scalar()
        rows = conn.execute(rows_sql, params_page).mappings().all()
        for row in rows:
            item = {}
            for col in column_names:
                item[col] = _mask_db_value(col, row.get(col))
            clean_rows.append(item)
    return {
        "table": table_name,
        "columns": columns,
        "rows": clean_rows,
        "page": page,
        "page_size": page_size,
        "total": int(total or 0),
        "total_pages": max(1, ((int(total or 0) + page_size - 1) // page_size)),
        "query": q_text,
    }

@router.get("/database-viewer/table/{table_name}/export")
def admin_database_export(
    table_name: str,
    q: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "export_database")
    q_text = (q or "").strip()
    table_name = _safe_db_table_name(table_name)
    columns = _db_table_columns(table_name)
    column_names = [c["name"] for c in columns]
    preparer = engine.dialect.identifier_preparer
    qtable = preparer.quote(table_name)
    where_sql = ""
    params = {}
    if q_text and column_names:
        searchable = [c for c in column_names if not _is_sensitive_db_column(c)]
        if searchable:
            clauses = []
            for i, col in enumerate(searchable):
                pname = f"q{i}"
                clauses.append(f"CAST({preparer.quote(col)} AS TEXT) ILIKE :{pname}")
                params[pname] = f"%{q_text}%"
            where_sql = " WHERE " + " OR ".join(clauses)
    rows_sql = text(f"SELECT * FROM {qtable}{where_sql} LIMIT 10000")
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(column_names)
    with engine.connect() as conn:
        rows = conn.execute(rows_sql, params).mappings().all()
        for row in rows:
            writer.writerow([_mask_db_value(col, row.get(col)) for col in column_names])

    _activity(db, superadmin.get("username"), "database_table_exported", f"Export CSV tabella {table_name}", "warning")
    db.commit()
    data = out.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table_name}_export.csv"'},
    )

# -----------------------------------------------------------------------
# Overview / KPI
# -----------------------------------------------------------------------

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


# -----------------------------------------------------------------------
# Utenti
# -----------------------------------------------------------------------

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


# -----------------------------------------------------------------------
# Ticket
# -----------------------------------------------------------------------

@router.get("/tickets")
def admin_tickets(
    status: str = "",
    tipo: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_tickets")
    q = db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    if tipo:
        q = q.filter(SupportTicket.tipo == tipo)
    rows = q.order_by(SupportTicket.created_at.desc()).all()
    return [ticket_to_dict(t, db) for t in rows]


@router.put("/tickets/{ticket_id}")
def admin_update_ticket(ticket_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_tickets")
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")
    valid_statuses = ("aperto", "in_lavorazione", "chiuso")
    new_status = (payload.get("status") or ticket.status or "aperto").strip()
    if new_status not in valid_statuses:
        raise HTTPException(400, "Stato non valido")

    previous_status = ticket.status
    ticket.status = new_status
    ticket.admin_note = payload.get("admin_note", ticket.admin_note)
    ticket.updated_at = datetime.utcnow()

    linked_error = db.get(SystemErrorLog, getattr(ticket, "system_error_id", None)) if getattr(ticket, "system_error_id", None) else None
    if linked_error:
        if new_status == "in_lavorazione":
            linked_error.status = "in_progress"
            if not linked_error.seen_at:
                linked_error.seen_at = datetime.utcnow()
        elif new_status == "chiuso":
            linked_error.status = "resolved"
            linked_error.resolved_at = datetime.utcnow()
            if ticket.admin_note:
                linked_error.admin_note = (linked_error.admin_note or "") + f"\nTicket #{ticket.id} chiuso: {ticket.admin_note}"
                linked_error.admin_note = linked_error.admin_note.strip()[:4000]

    db.commit()
    db.refresh(ticket)

    # Se richiesto, avvisa l'utente quando il ticket viene chiuso.
    if new_status == "chiuso" and previous_status != "chiuso" and getattr(ticket, "notify_on_resolution", True) and not getattr(ticket, "resolved_email_sent", False):
        # Prima di inviare l'avviso di risoluzione, rilegge l'email aggiornata dal Profilo azienda.
        # Questo evita che un ticket usi ancora la vecchia email demo/account se l'azienda
        # ha modificato il campo email dal Profilo azienda.
        linked_user = db.get(User, ticket.user_id) if ticket.user_id else None
        destination_email = ((linked_user.company_email if linked_user else None) or ticket.email or "").strip()
        if destination_email and destination_email != ticket.email:
            ticket.email = destination_email
            db.commit()
            db.refresh(ticket)
        sent = send_ticket_resolved(destination_email, ticket_to_dict(ticket, db)) if destination_email else False
        ticket.resolved_email_sent = bool(sent)
        db.commit()
        db.refresh(ticket)

    return ticket_to_dict(ticket, db)


# -----------------------------------------------------------------------
# Errori sistema
# -----------------------------------------------------------------------

@router.get("/system-errors")
def admin_system_errors(
    status: str = "",
    severity: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_errors")
    limit = max(1, min(limit, 300))
    q = db.query(SystemErrorLog)
    if status:
        q = q.filter(SystemErrorLog.status == status)
    if severity:
        q = q.filter(SystemErrorLog.severity == severity)
    rows = q.order_by(SystemErrorLog.created_at.desc()).limit(limit).all()
    return [error_log_to_dict(r) for r in rows]


@router.get("/system-errors/summary")
def admin_system_errors_summary(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    new_count = db.query(SystemErrorLog).filter(SystemErrorLog.status == "new").count()
    critical_count = db.query(SystemErrorLog).filter(
        SystemErrorLog.status != "resolved",
        SystemErrorLog.severity == "critical",
    ).count()
    high_count = db.query(SystemErrorLog).filter(
        SystemErrorLog.status != "resolved",
        SystemErrorLog.severity == "high",
    ).count()
    last = db.query(SystemErrorLog).order_by(SystemErrorLog.created_at.desc()).first()
    return {
        "new": new_count,
        "critical_open": critical_count,
        "high_open": high_count,
        "last_error": error_log_to_dict(last) if last else None,
    }


@router.get("/system-errors/{error_id}")
def admin_system_error_detail(error_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    row = db.get(SystemErrorLog, error_id)
    if not row:
        raise HTTPException(404, "Errore non trovato")
    if row.status == "new":
        row.status = "seen"
        row.seen_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return error_log_to_dict(row)


@router.put("/system-errors/{error_id}")
def admin_update_system_error(error_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_errors")
    row = db.get(SystemErrorLog, error_id)
    if not row:
        raise HTTPException(404, "Errore non trovato")
    status = payload.get("status")
    if status in ("new", "seen", "in_progress", "resolved", "ignored"):
        row.status = status
        if status in ("seen", "in_progress") and not row.seen_at:
            row.seen_at = datetime.utcnow()
        if status == "resolved":
            row.resolved_at = datetime.utcnow()
    if "admin_note" in payload:
        row.admin_note = (payload.get("admin_note") or "")[:4000]
    if status == "resolved":
        linked_tickets = db.query(SupportTicket).filter(
            SupportTicket.system_error_id == row.id,
            SupportTicket.status != "chiuso",
        ).all()
        for ticket in linked_tickets:
            ticket.status = "chiuso"
            ticket.updated_at = datetime.utcnow()
            if row.admin_note and not ticket.admin_note:
                ticket.admin_note = row.admin_note
            if getattr(ticket, "notify_on_resolution", True) and not getattr(ticket, "resolved_email_sent", False):
                sent = send_ticket_resolved(ticket.email, ticket_to_dict(ticket, db))
                ticket.resolved_email_sent = bool(sent)
    db.commit()
    db.refresh(row)
    return error_log_to_dict(row)



@router.post("/tickets/{ticket_id}/ai-analysis")
def admin_ticket_ai_analysis(ticket_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_tickets")
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")
    if not getattr(ticket, "system_error_id", None):
        raise HTTPException(400, "Analisi AI disponibile solo per ticket collegati a un errore sistema")
    err = db.get(SystemErrorLog, ticket.system_error_id)
    linked_user = db.get(User, ticket.user_id) if ticket.user_id else None
    context = {
        "ticket": ticket_to_dict(ticket, db),
        "error": error_log_to_dict(err) if err else None,
        "company": user_to_dict(linked_user, db) if linked_user else None,
        "sector": (linked_user.company_sector if linked_user else "") or (err.company_sector if err else ""),
    }
    prompt = """Analizza questo ticket GiroFacile collegato a errore tecnico.
Produci una risposta breve in italiano con sezioni: Problema rilevato, Possibile causa, Impatto sull'utente, Come risolvere, Risposta suggerita al cliente.
Non inventare dati, usa solo il contesto fornito.
"""
    result = run_ai_text(
        db, task="admin_error_analysis", user_id=ticket.user_id,
        system_prompt="Sei un assistente tecnico interno per il Super Admin SaaS GiroFacile. Scrivi in modo pratico, breve e operativo.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )
    return result


@router.post("/system-errors/{error_id}/ai-analysis")
def admin_error_ai_analysis(error_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    err = db.get(SystemErrorLog, error_id)
    if not err:
        raise HTTPException(404, "Errore non trovato")
    linked_user = db.get(User, err.user_id) if err.user_id else None
    context = {
        "error": error_log_to_dict(err),
        "company": user_to_dict(linked_user, db) if linked_user else None,
        "sector": (linked_user.company_sector if linked_user else "") or err.company_sector or "",
    }
    prompt = """Analizza questo errore tecnico GiroFacile.
Produci una scheda breve in italiano con: Problema rilevato, Possibile causa, Impatto sull'utente, Come risolvere, Risposta suggerita.
Non inventare dati e non promettere soluzioni già completate.
"""
    return run_ai_text(
        db, task="admin_error_analysis", user_id=err.user_id,
        system_prompt="Sei un assistente tecnico interno per il Super Admin SaaS GiroFacile. Scrivi in modo pratico, breve e operativo.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )

# -----------------------------------------------------------------------
# Revenue
# -----------------------------------------------------------------------

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
