"""Un solo modo di leggere l'ambiente (produzione o sviluppo) e le impostazioni sì/no.

Prima ogni modulo riconosceva la produzione a modo suo («prod» valeva in alcuni e non in
altri) e un refuso come COOKIE_SECURE=tru veniva letto come «spento». Qui:
- «production» e «prod» sono la stessa cosa ovunque;
- un valore sì/no non riconosciuto non spegne mai nulla: vale il predefinito sicuro e
  all'avvio il server si rifiuta di partire finché non viene corretto.
"""
from __future__ import annotations

import os

PRODUCTION_ENVS = {"production", "prod"}
KNOWN_ENVS = PRODUCTION_ENVS | {"development", "dev", "local", "test", "testing", "staging"}
TRUE_VALUES = {"1", "true", "yes", "si", "sì", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
# Impostazioni sì/no lette dall'ambiente: un valore diverso da quelli ammessi blocca l'avvio.
BOOL_SETTINGS = (
    "COOKIE_SECURE", "TRUST_PROXY_HEADERS", "LOGIN_RATE_LIMIT_ENABLED", "OBJECT_STORAGE_ENABLED",
    "ALLOW_SQLITE_LEGACY", "GOOGLE_GEOCODING_ENABLED", "GOOGLE_ROUTES_ENABLED", "AI_ENABLED",
    "ERROR_NOTIFICATIONS_ENABLED", "DATABASE_ECHO",
)


def _env(env):
    return os.environ if env is None else env


def raw_app_env(env: dict | None = None) -> str:
    return (_env(env).get("APP_ENV") or "development").strip().lower()


def app_env(env: dict | None = None) -> str:
    """Nome normalizzato: «prod» diventa «production»."""
    value = raw_app_env(env)
    return "production" if value in PRODUCTION_ENVS else value


def is_production(env: dict | None = None) -> bool:
    return raw_app_env(env) in PRODUCTION_ENVS


def parse_bool(value, default: bool) -> tuple[bool, bool]:
    """Restituisce (valore, valido). Vuoto o assente: il predefinito, valido."""
    text = (value or "").strip().lower()
    if not text:
        return default, True
    if text in TRUE_VALUES:
        return True, True
    if text in FALSE_VALUES:
        return False, True
    return default, False


def env_bool(name: str, default: bool = False, env: dict | None = None) -> bool:
    return parse_bool(_env(env).get(name), default)[0]


def invalid_settings(env: dict | None = None) -> list[str]:
    """Valori che il server non accetta in nessun ambiente."""
    env = _env(env)
    problems = []
    if raw_app_env(env) not in KNOWN_ENVS:
        problems.append(f"APP_ENV non riconosciuto: usa production oppure development (trovato «{raw_app_env(env)}»)")
    samesite = (env.get("COOKIE_SAMESITE") or "lax").strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        problems.append(f"COOKIE_SAMESITE non valido: usa lax, strict oppure none (trovato «{env.get('COOKIE_SAMESITE')}»)")
    for name in BOOL_SETTINGS:
        if not parse_bool(env.get(name), False)[1]:
            problems.append(f"{name} non valido: usa true oppure false (trovato «{env.get(name)}»)")
    return problems
