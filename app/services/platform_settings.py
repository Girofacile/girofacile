"""Lettura centralizzata impostazioni SaaS salvate nel database.

Queste funzioni garantiscono che ciò che viene modificato dal profilo
Super Admin venga realmente usato dai servizi operativi. Il file .env resta
solo come fallback quando una chiave/impostazione non è ancora salvata nel DB.
"""
from __future__ import annotations

import os
from sqlalchemy.orm import Session

from ..models import SaaSPlatformSetting


def get_platform_setting(db: Session | None, key: str, default: str = "") -> str:
    if db is not None:
        try:
            row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == key).first()
            if row and row.value is not None and str(row.value).strip() != "":
                return str(row.value).strip()
        except Exception:
            pass
    return default


def set_platform_setting(db: Session, key: str, value: str | None):
    row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == key).first()
    if not row:
        row = SaaSPlatformSetting(key=key, value=value or "")
        db.add(row)
    else:
        row.value = value or ""
    return row


def setting_bool(db: Session | None, key: str, default: bool = False) -> bool:
    raw = get_platform_setting(db, key, "true" if default else "false")
    return str(raw).strip().lower() in ("1", "true", "yes", "si", "sì", "on")


def google_maps_api_key(db: Session | None = None) -> str:
    return get_platform_setting(db, "google_maps_api_key", os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()


def google_geocoding_enabled(db: Session | None = None) -> bool:
    # Default da .env, ma se la chiave è salvata nel pannello Super Admin il servizio resta attivo.
    env_default = os.getenv("GOOGLE_GEOCODING_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si", "sì", "on")
    return setting_bool(db, "google_geocoding_enabled", env_default) or bool(google_maps_api_key(db))


def google_routes_enabled(db: Session | None = None) -> bool:
    env_default = os.getenv("GOOGLE_ROUTES_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si", "sì", "on")
    return setting_bool(db, "google_routes_enabled", env_default) or bool(google_maps_api_key(db))


def openai_api_key(db: Session | None = None) -> str:
    return get_platform_setting(db, "openai_api_key", os.getenv("OPENAI_API_KEY", "")).strip()


def openai_model(db: Session | None = None) -> str:
    return get_platform_setting(db, "openai_model", os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"


def ai_enabled(db: Session | None = None) -> bool:
    return setting_bool(db, "ai_enabled", os.getenv("AI_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si", "sì", "on"))

# Routing di base e traffico: le impostazioni DB prevalgono sulle variabili env.
def routing_setting(db: Session | None, key: str, default: str = "") -> str:
    return get_platform_setting(db, key, os.getenv(key.upper(), default))


def osrm_url(db: Session | None = None) -> str:
    from urllib.parse import urlparse
    url = routing_setting(db, "osrm_url", "http://localhost:5000").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("OSRM_URL deve essere un URL HTTP(S) senza credenziali")
    public = parsed.hostname.lower() in ("router.project-osrm.org", "routing.openstreetmap.de")
    production = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production")).lower() in ("production", "prod")
    allow_public = routing_setting(db, "osrm_allow_public_fallback", "false").lower() in ("1", "true", "yes", "on")
    if public and (production or not allow_public):
        raise ValueError("In produzione OSRM richiede un'istanza propria; il server pubblico è solo per sviluppo esplicito")
    return url


def traffic_provider_name(db: Session | None = None) -> str:
    return routing_setting(db, "traffic_provider", "none").lower()


def mapbox_access_token(db: Session | None = None) -> str:
    return routing_setting(db, "mapbox_access_token")


def routing_number(db: Session | None, key: str, default: float, minimum: float = 0) -> float:
    import math
    try:
        value = float(routing_setting(db, key, str(default)))
        return max(minimum, value) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default
