"""Controllo della configurazione obbligatoria in produzione.

In produzione il server non deve avviarsi con segreti mancanti, deboli o
lasciati ai valori di sviluppo: una chiave nota permette di falsificare link
firmati (tracciamento, fermate occasionali, ricevute targa) e una password
superadmin di default espone l'intera piattaforma.
"""
from __future__ import annotations

import os

DEFAULT_SECRETS = {"dev-secret-change-me", "change-me", "changeme", "secret"}
WEAK_ADMIN_PASSWORDS = {
    "admin", "admin123", "admin2026", "administrator", "password",
    "password123", "girofacile", "girofacile123", "12345678", "changeme",
}
MIN_SECRET_LENGTH = 32
MIN_ADMIN_PASSWORD_LENGTH = 12
PRODUCTION_ENVS = {"production", "prod"}


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

    return problems


def require_production_config(env: dict | None = None) -> None:
    """Blocca l'avvio in produzione se la configurazione non è sicura."""
    if not is_production(env):
        return
    problems = production_config_problems(env)
    if problems:
        raise RuntimeError(
            "Avvio in produzione bloccato, configurazione non sicura: " + "; ".join(problems)
        )
