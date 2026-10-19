"""Limiti su login, registrazione e reset password; fiducia negli header proxy."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from app.core import http_security as hs


def _request(path, client="203.0.113.7", headers=None, method="POST", identifier="person@example.test"):
    async def body():
        return {"email": identifier}
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path),
                           client=SimpleNamespace(host=client), headers=headers or {}, json=body)


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


def test_own_success_never_clears_another_accounts_failures():
    target = lambda: _request("/api/login", identifier="target@example.test")
    own = lambda: _request("/api/login", identifier="own@example.test")
    for _ in range(3):
        assert _call(target(), status=401).status_code == 401
        assert _call(own(), status=200).status_code == 200
    assert _call(target(), status=401).status_code == 429
    assert _call(own(), status=200).status_code == 200


def test_identifier_normalization_cannot_get_a_fresh_bucket():
    for identifier in ("Target@Example.Test", " target@example.test ", "TARGET@example.test"):
        assert _call(_request("/api/login", identifier=identifier), status=401).status_code == 401
    assert _call(_request("/api/login", identifier="target@example.test"), status=401).status_code == 429


def test_success_does_not_clear_ip_spray_budget():
    for index in range(30):
        assert _call(_request("/api/login", identifier=f"account{index}@example.test"), status=200).status_code == 200
    assert _call(_request("/api/login", identifier="next@example.test"), status=200).status_code == 429


def test_malformed_identifiers_remain_ip_limited():
    for _ in range(3):
        assert _call(_request("/api/login", identifier=None), status=422).status_code == 422
    assert _call(_request("/api/login", identifier=None), status=422).status_code == 429


def test_inspecting_identity_preserves_endpoint_body():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.middleware("http")(hs.login_rate_limit_middleware)

    @app.post("/api/login")
    def login(payload: dict):
        return payload

    payload = {"email": "body@example.test", "password": "synthetic-password"}
    with TestClient(app) as client:
        response = client.post("/api/login", json=payload)
    assert response.status_code == 200
    assert response.json() == payload


@pytest.mark.parametrize('path', ['/api/driver/login', '/api/agent/login'])
def test_email_only_endpoints_ignore_extra_username_for_rate_key(path):
    def request(index):
        req = _request(path)
        async def body():
            return {'email': 'target@example.test', 'username': f'ignored-{index}'}
        req.json = body
        return req
    assert [_call(request(i), status=401).status_code for i in range(4)] == [401, 401, 401, 429]
