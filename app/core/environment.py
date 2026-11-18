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
    problems += billing_problems(env)
    return problems


def billing_problems(env: dict) -> list[str]:
    """Pagamenti: una modalità sconosciuta o una chiave dell'altra modalità bloccano l'avvio."""
    mode = (env.get("BILLING_MODE") or "disabled").strip().lower()
    if mode not in {"disabled", "test", "live"}:
        return [f"BILLING_MODE non valido: usa disabled, test oppure live (trovato «{env.get('BILLING_MODE')}»)"]
    if mode == "disabled":
        return []
    problems = []
    key = (env.get("STRIPE_SECRET_KEY") or "").strip()
    expected = ("sk_live_", "rk_live_") if mode == "live" else ("sk_test_", "rk_test_")
    if not key.startswith(expected):
        problems.append(f"BILLING_MODE={mode} richiede una STRIPE_SECRET_KEY che inizia con {expected[0]} o {expected[1]}")
    if not (env.get("STRIPE_WEBHOOK_SECRET") or "").strip():
        problems.append(f"BILLING_MODE={mode} richiede STRIPE_WEBHOOK_SECRET")
    if mode == "live":
        missing = [name for name in ("STRIPE_PRICE_STARTER", "STRIPE_PRICE_BUSINESS", "STRIPE_PRICE_PRO")
                   if not (env.get(name) or "").strip()]
        if missing:
            problems.append("BILLING_MODE=live richiede i prezzi Stripe reali: manca " + ", ".join(missing))
    return problems
