"""Limiti su login, registrazione e reset password; fiducia negli header proxy."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from app.core import http_security as hs


def _request(path, client="203.0.113.7", headers=None, method="POST"):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path),
                           client=SimpleNamespace(host=client), headers=headers or {})


def _call(request, status=200):
    async def call_next(_req):
        return JSONResponse({"ok": True}, status_code=status)
    return asyncio.run(hs.login_rate_limit_middleware(request, call_next))


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    hs._attempts.clear()
    monkeypatch.setattr(hs, "LOGIN_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(hs, "LOGIN_RATE_LIMIT_ATTEMPTS", 3)
    yield
    hs._attempts.clear()


@pytest.mark.parametrize("path", sorted(hs.SENSITIVE_PATHS))
def test_sensitive_endpoints_are_limited_even_on_success(path):
    codes = [_call(_request(path)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_successful_login_still_resets_counter():
    for _ in range(2):
        _call(_request("/api/login"), status=401)
    assert _call(_request("/api/login")).status_code == 200
    codes = [_call(_request("/api/login"), status=401).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]


def test_forwarded_header_ignored_from_public_client(monkeypatch):
    monkeypatch.setattr(hs, "TRUST_PROXY_HEADERS", True)
    spoofed = _request("/api/login", client="8.8.8.8", headers={"x-forwarded-for": "1.2.3.4"})
    assert hs._client_ip(spoofed) == "8.8.8.8"


def test_forwarded_header_used_behind_internal_proxy(monkeypatch):
    monkeypatch.setattr(hs, "TRUST_PROXY_HEADERS", True)
    proxied = _request("/api/login", client="172.18.0.1", headers={"x-forwarded-for": "198.51.100.9, 10.0.0.2"})
    assert hs._client_ip(proxied) == "198.51.100.9"


def test_tracked_keys_are_bounded(monkeypatch):
    monkeypatch.setattr(hs, "MAX_TRACKED_KEYS", 50)
    for i in range(200):
        _call(_request("/api/signup", client=f"198.51.100.{i % 250}"))
    assert len(hs._attempts) <= 50


def test_compose_binds_internal_services_locally():
    from pathlib import Path
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert '"127.0.0.1:5000:5000"' in content
    assert '"${APP_BIND_ADDRESS:-127.0.0.1}:8000:8000"' in content
