"""Monitoraggio errori GiroFacile.

Registra solo errori tecnici importanti, li rende visibili al Super Admin
e, se configurato, invia una notifica email immediata.
"""
from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any

from fastapi import Request

from ..core.config import (
    ERROR_NOTIFICATIONS_ENABLED,
    ERROR_NOTIFICATIONS_EMAIL,
    ERROR_NOTIFICATION_MIN_SEVERITY,
)
from ..core.security import verify_token
from ..database import SessionLocal
from ..models import SystemErrorLog, User
from .email import send_system_error_alert

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

IGNORED_PATH_PREFIXES = (
    "/static/",
    "/favicon.ico",
)

EXPECTED_STATUS_CODES = {400, 401, 403, 404, 409, 422}


def should_ignore_http_status(status_code: int) -> bool:
    return status_code in EXPECTED_STATUS_CODES


def _severity_for_exception(exc: Exception, path: str = "") -> str:
    name = exc.__class__.__name__.lower()
    if "operationalerror" in name or "database" in name:
        return "critical"
    if "timeout" in name or "connection" in name:
        return "high"
    if path.startswith("/api/"):
        return "high"
    return "medium"


def _extract_action(request: Request) -> str:
    path = request.url.path
    if path.startswith("/api/customers"):
        return "Clienti"
    if path.startswith("/api/routes"):
        return "Giri / pianificazione"
    if path.startswith("/api/drivers"):
        return "Autisti"
    if path.startswith("/api/vehicles"):
        return "Mezzi"
    if path.startswith("/api/deposits"):
        return "Depositi"
    if path.startswith("/api/reports"):
        return "Report"
    if path.startswith("/api/settings"):
        return "Impostazioni"
    if path.startswith("/api/driver"):
        return "Portale autista"
    if "shopify" in path.lower() or "integration" in path.lower():
        return "Integrazioni"
    return path


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def log_exception(request: Request, exc: Exception, *, severity: str | None = None) -> int | None:
    """Salva un errore tecnico e manda email se la soglia lo consente."""
    path = request.url.path
    if path.startswith(IGNORED_PATH_PREFIXES):
        return None

    severity = severity or _severity_for_exception(exc, path)
    technical_details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    db = SessionLocal()
    try:
        user = None
        token_user_id = verify_token(request.cookies.get("session"))
        if token_user_id:
            user = db.get(User, token_user_id)

        row = SystemErrorLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            company_name=user.company_name if user else None,
            company_sector=(user.company_sector or user.company_activity_type) if user else None,
            user_role="azienda" if user else "pubblico",
            method=request.method,
            path=path,
            action=_extract_action(request),
            error_type=exc.__class__.__name__,
            error_message=str(exc)[:3000],
            technical_details=technical_details[:12000],
            browser=request.headers.get("user-agent", "")[:1500],
            ip_address=_client_ip(request),
            severity=severity,
            status="new",
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        should_send = (
            ERROR_NOTIFICATIONS_ENABLED
            and ERROR_NOTIFICATIONS_EMAIL
            and SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(ERROR_NOTIFICATION_MIN_SEVERITY, 3)
        )
        if should_send:
            payload = {
                "id": row.id,
                "company_name": row.company_name,
                "username": row.username,
                "company_sector": row.company_sector,
                "action": row.action,
                "method": row.method,
                "path": row.path,
                "severity": row.severity,
                "error_type": row.error_type,
                "error_message": row.error_message,
                "technical_details": row.technical_details,
            }
            row.email_sent = bool(send_system_error_alert(ERROR_NOTIFICATIONS_EMAIL, payload))
            db.commit()
        return row.id
    except Exception as monitor_exc:
        print(f"[ERROR_MONITOR] Impossibile registrare errore: {monitor_exc}")
        return None
    finally:
        db.close()


def error_log_to_dict(row: SystemErrorLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "username": row.username or "",
        "company_name": row.company_name or "",
        "company_sector": row.company_sector or "",
        "user_role": row.user_role or "",
        "method": row.method or "",
        "path": row.path or "",
        "action": row.action or "",
        "error_type": row.error_type or "",
        "error_message": row.error_message or "",
        "technical_details": row.technical_details or "",
        "browser": row.browser or "",
        "ip_address": row.ip_address or "",
        "severity": row.severity or "high",
        "status": row.status or "new",
        "email_sent": bool(row.email_sent),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "seen_at": row.seen_at.isoformat() if row.seen_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "admin_note": row.admin_note or "",
    }
