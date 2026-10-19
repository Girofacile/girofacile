"""Impostazioni HTTP di sicurezza condivise da tutta l'applicazione."""
from __future__ import annotations

import ipaddress
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict, deque

from fastapi import Request
from fastapi.responses import JSONResponse


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sì", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}
COOKIE_SECURE = env_bool("COOKIE_SECURE", IS_PRODUCTION)
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    COOKIE_SAMESITE = "lax"
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "").strip() or None
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)

LOGIN_RATE_LIMIT_ENABLED = env_bool("LOGIN_RATE_LIMIT_ENABLED", True)
LOGIN_RATE_LIMIT_ATTEMPTS = max(1, int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5")))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = max(60, int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")))

LOGIN_PATHS = {
    "/api/login",
    "/api/admin/login",
    "/api/driver/login",
    "/api/agent/login",
    "/api/collaborator-invitations/accept",
}

# Endpoint sensibili diversi dal login: registrazione e recupero/cambio password.
# A differenza dei login, una risposta positiva non azzera il contatore (la
# richiesta di reset risponde sempre 200 per non rivelare quali email esistono).
SENSITIVE_PATHS = {
    "/api/signup",
    "/api/password-reset/request",
    "/api/support/password-reset-request",
    "/api/password-reset/confirm",
    "/api/account-password/change",
}
RATE_LIMITED_PATHS = LOGIN_PATHS | SENSITIVE_PATHS
MAX_TRACKED_KEYS = 10000

_attempts: "OrderedDict[str, deque[float]]" = OrderedDict()
_attempts_lock = threading.Lock()


def cookie_options(max_age: int) -> dict:
    """Opzioni uniformi per tutti i cookie di autenticazione."""
    options = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "max_age": max_age,
        "path": "/",
    }
    if COOKIE_DOMAIN:
        options["domain"] = COOKIE_DOMAIN
    return options


def _is_internal_address(host: str | None) -> bool:
    try:
        address = ipaddress.ip_address((host or "").strip())
    except ValueError:
        return False
    return address.is_loopback or address.is_private


def _client_ip(request: Request) -> str:
    direct = request.client.host if request.client else None
    # Gli header del proxy sono attendibili solo se la connessione arriva da un
    # proxy interno (loopback o rete privata). Un client esposto direttamente
    # non può così falsificare l'IP per aggirare i limiti.
    if TRUST_PROXY_HEADERS and _is_internal_address(direct):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip
    return direct or "unknown"


async def _login_identifier(request):
    """Hash normalized login identity without retaining personal data."""
    if request.url.path not in LOGIN_PATHS - {"/api/collaborator-invitations/accept"}:
        return None
    try:
        payload = await request.json()
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    value = (payload.get("email") if request.url.path in {"/api/driver/login", "/api/agent/login"}
             else payload.get("username") or payload.get("email"))
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        return None
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


async def login_rate_limit_middleware(request: Request, call_next):
    """In-memory guard; multi-process deployments also need a shared limiter."""
    if (
        not LOGIN_RATE_LIMIT_ENABLED
        or request.method.upper() != "POST"
        or request.url.path not in RATE_LIMITED_PATHS
    ):
        return await call_next(request)

    now = time.monotonic()
    ip_key = f"ip:{_client_ip(request)}:{request.url.path}"
    identifier = await _login_identifier(request)
    credential_login = request.url.path in LOGIN_PATHS - {"/api/collaborator-invitations/accept"}
    if identifier:
        identity_key = f"account:{ip_key}:{identifier}"
        rules = ((identity_key, LOGIN_RATE_LIMIT_ATTEMPTS),
                 (ip_key, LOGIN_RATE_LIMIT_ATTEMPTS * 10))
        clear_key = identity_key
    else:
        rules = ((ip_key, LOGIN_RATE_LIMIT_ATTEMPTS),)
        clear_key = ip_key if request.url.path in LOGIN_PATHS and not credential_login else None
    retry_after = 0
    with _attempts_lock:
        buckets = []
        for key, maximum in rules:
            bucket = _attempts.get(key)
            if bucket is None:
                bucket = _attempts[key] = deque()
            _attempts.move_to_end(key)
            threshold = now - LOGIN_RATE_LIMIT_WINDOW_SECONDS
            while bucket and bucket[0] <= threshold:
                bucket.popleft()
            if len(bucket) >= maximum:
                retry_after = max(retry_after, 1, int(LOGIN_RATE_LIMIT_WINDOW_SECONDS - (now - bucket[0])))
            buckets.append(bucket)
        if not retry_after:
            for bucket in buckets:
                bucket.append(now)
        while len(_attempts) > MAX_TRACKED_KEYS:
            _attempts.popitem(last=False)

    if retry_after:
        return JSONResponse(
            status_code=429,
            content={"detail": "Troppi tentativi. Riprova più tardi."},
            headers={"Retry-After": str(retry_after)},
        )
    response = await call_next(request)
    if clear_key and 200 <= response.status_code < 300:
        with _attempts_lock:
            _attempts.pop(clear_key, None)
    return response
