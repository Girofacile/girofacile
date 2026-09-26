"""Admin profile: extracted from the SaaS administration router."""
from datetime import datetime
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.config import APP_BASE_URL, ERROR_NOTIFICATIONS_EMAIL, GOOGLE_MAPS_API_KEY
from ..core.dependencies import require_superadmin
from ..database import get_db
from ..models import SuperAdminActivityLog, SuperAdminCollaborator
from ..services.email import send_superadmin_collaborator_invitation
from ..core.security import hash_password

from .admin_helpers import (
    COLLABORATOR_PERMISSIONS,
    _activity,
    _bool_to_str,
    _collaborator_permissions,
    _get_or_create_superadmin_profile,
    _permissions_to_json,
    _profile_to_dict,
    _require_perm,
    _set_setting_value,
    _setting_value,
    _temporary_password,
    collaborator_to_dict,
)

router = APIRouter()


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
