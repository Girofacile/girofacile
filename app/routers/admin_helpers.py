"""Admin helpers: extracted from the SaaS administration router."""
from datetime import datetime
import json
import os
import secrets
import string
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from ..core.config import SUPERADMIN_USERNAME, ERROR_NOTIFICATIONS_EMAIL
from ..core.dependencies import is_admin_user
from ..database import engine, database_kind
from ..services.backups import backup_directory, backup_files, resolve_backup
from ..models import Customer, Driver, RoutePlan, SupportTicket, User, Vehicle, SaaSPlatformSetting, SuperAdminProfile, SuperAdminActivityLog, SuperAdminCollaborator
from ..services.plans import get_user_plan_status
from ..services.platform_settings import google_maps_api_key, openai_api_key


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
    return backup_directory()


def _list_backups() -> list[dict]:
    return [{"filename": p.name, "size_bytes": p.stat().st_size,
             "created_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat()}
            for p in backup_files()[:20]]


def _safe_backup_name(filename: str) -> Path:
    try:
        return resolve_backup(filename)
    except ValueError:
        raise HTTPException(404, "Backup non trovato")


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
