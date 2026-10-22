"""Controllo della configurazione obbligatoria in produzione.

In produzione il server non deve avviarsi con segreti mancanti, deboli o
lasciati ai valori di sviluppo: una chiave nota permette di falsificare link
firmati (tracciamento, fermate occasionali, ricevute targa) e una password
superadmin di default espone l'intera piattaforma.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_SECRETS = {"dev-secret-change-me", "change-me", "changeme", "secret"}
WEAK_ADMIN_PASSWORDS = {
    "admin", "admin123", "admin2026", "administrator", "password",
    "password123", "girofacile", "girofacile123", "12345678", "changeme",
}
MIN_SECRET_LENGTH = 32
MIN_ADMIN_PASSWORD_LENGTH = 12
PRODUCTION_ENVS = {"production", "prod"}
LOCAL_URLS = ("http://localhost", "http://127.0.0.1")
S3_SETTINGS = tuple("OBJECT_STORAGE_" + name for name in ("ENDPOINT", "REGION", "BUCKET", "ACCESS_KEY", "SECRET_KEY"))


def is_production(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    return (env.get("APP_ENV") or "development").strip().lower() in PRODUCTION_ENVS


def production_config_problems(env: dict | None = None) -> list[str]:
    """Elenca i problemi di configurazione; lista vuota se tutto è in regola.

    Legge le variabili d'ambiente reali e non i fallback di ``config.py``,
    così un valore assente viene riconosciuto come assente.
    """
    env = os.environ if env is None else env
    problems: list[str] = []

    secret = (env.get("APP_SECRET") or "").strip()
    if not secret:
        problems.append("APP_SECRET non impostato")
    elif secret.lower() in DEFAULT_SECRETS:
        problems.append("APP_SECRET usa un valore di sviluppo")
    elif len(secret) < MIN_SECRET_LENGTH:
        problems.append(f"APP_SECRET troppo corto (minimo {MIN_SECRET_LENGTH} caratteri)")

    admin_password = (env.get("SUPERADMIN_PASSWORD") or env.get("APP_PASSWORD") or "").strip()
    if not admin_password:
        problems.append("SUPERADMIN_PASSWORD non impostata")
    elif admin_password.lower() in WEAK_ADMIN_PASSWORDS:
        problems.append("SUPERADMIN_PASSWORD usa un valore di default o comune")
    elif len(admin_password) < MIN_ADMIN_PASSWORD_LENGTH:
        problems.append(f"SUPERADMIN_PASSWORD troppo corta (minimo {MIN_ADMIN_PASSWORD_LENGTH} caratteri)")

    if (env.get("COOKIE_SECURE") or "").strip().lower() in {"0", "false", "no", "off"}:
        problems.append("COOKIE_SECURE disattivato")

    database_url = (env.get("DATABASE_URL") or "").strip().lower()
    if database_url.startswith("sqlite") or _is_true(env.get("ALLOW_SQLITE_LEGACY")):
        problems.append("SQLite non è ammesso in produzione")

    base_url = (env.get("APP_BASE_URL") or "").strip().lower()
    if base_url.startswith("http://") and not base_url.startswith(LOCAL_URLS):
        problems.append("APP_BASE_URL deve usare https")

    if _is_true(env.get("OBJECT_STORAGE_ENABLED")):
        backend = (env.get("OBJECT_STORAGE_BACKEND") or "s3").strip().lower()
        if backend != "s3":
            problems.append("archivio prove di consegna locale non ammesso in produzione (usa OBJECT_STORAGE_BACKEND=s3)")
        else:
            missing = [name for name in S3_SETTINGS if not (env.get(name) or "").strip()]
            if missing:
                problems.append("archivio prove di consegna incompleto: manca " + ", ".join(missing))

    return problems


def production_config_warnings(env: dict | None = None) -> list[str]:
    """Impostazioni assenti che non impediscono l'avvio ma disattivano funzioni."""
    env = os.environ if env is None else env
    warnings: list[str] = []
    if not (env.get("DATABASE_URL") or "").strip():
        warnings.append("DATABASE_URL non impostato: viene usato il database locale di sviluppo")
    if not all((env.get(name) or "").strip() for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")):
        warnings.append("email SMTP non configurata: inviti e recupero password non partono")
    if not (env.get("ERROR_NOTIFICATIONS_EMAIL") or "").strip():
        warnings.append("ERROR_NOTIFICATIONS_EMAIL non impostata: nessun avviso sugli errori")
    if not _is_true(env.get("OBJECT_STORAGE_ENABLED")):
        warnings.append("archivio prove di consegna disattivato: firme e foto non vengono salvate come file")
    if not (env.get("PASSWORD_PEPPER") or "").strip():
        warnings.append("PASSWORD_PEPPER non impostato")
    if not (env.get("ORDER_CONNECTOR_KEY") or "").strip():
        warnings.append("ORDER_CONNECTOR_KEY non impostata: i negozi online non si possono collegare")
    return warnings


def _is_true(value) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "si", "sì", "on"}


def require_production_config(env: dict | None = None) -> None:
    """Blocca l'avvio in produzione se la configurazione non è sicura."""
    if not is_production(env):
        return
    problems = production_config_problems(env)
    if problems:
        raise RuntimeError(
            "Avvio in produzione bloccato, configurazione non sicura: " + "; ".join(problems)
        )
    for warning in production_config_warnings(env):
        logger.warning("Configurazione produzione: %s", warning)
