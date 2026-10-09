"""Security boundaries for collaborator invitations, without SMTP or production DB."""
from collections import defaultdict, deque
from html import escape
from pathlib import Path
import threading
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    # Imports may construct the application engine; these tests never open it.
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    monkeypatch.setenv("OBJECT_STORAGE_ENABLED", "false")


@pytest.mark.parametrize("transport_result", [True, False])
def test_invitation_email_escapes_content_and_preserves_transport_result(
    monkeypatch, transport_result
):
    from app.services import email

    sent = []

    def capture(to_email, subject, html_body):
        sent.append((to_email, subject, html_body))
        return transport_result

    def unexpected_smtp(*args, **kwargs):
        pytest.fail("Invitation unit tests must not contact SMTP")

    monkeypatch.setattr(email, "_send", capture)
    monkeypatch.setattr(email.smtplib, "SMTP", unexpected_smtp)
    name = 'Ada <script>alert("name")</script>'
    company = 'Acme <img src=x onerror="company">\r\nBcc: injected@example.test'
    recipient = "worker&tag@example.test"
    setup_url = 'https://invites.example.test/collaborator/setup#token=synthetic&extra="unsafe"'

    result = email.send_collaborator_invitation(recipient, name, company, setup_url)

    assert result is transport_result
    assert len(sent) == 1
    address, subject, body = sent[0]
    assert address == recipient
    assert "\r" not in subject and "\n" not in subject
    for value in (name, company, recipient, setup_url):
        assert escape(value, quote=True) in body
    assert "<script>" not in body
    assert '<img src=x onerror="company">' not in body
    assert f'href="{setup_url}"' not in body
    assert "Password temporanea:" not in body
    assert "temporary_password" not in body
    assert "GiroFacile" in body


def test_invitation_page_is_private_and_does_not_touch_database(monkeypatch):
    from app.main import app as real_app
    from app import database

    def unexpected_database(*args, **kwargs):
        pytest.fail("The invitation HTML page must not access any database")

    monkeypatch.setattr(database.engine, "connect", unexpected_database)
    monkeypatch.setattr(database, "SessionLocal", unexpected_database)
    endpoint = next(
        route.endpoint for route in real_app.routes
        if getattr(route, "path", None) == "/collaborator/setup"
    )
    app = FastAPI()
    app.add_api_route("/collaborator/setup", endpoint, methods=["GET"])
    with TestClient(app) as client:
        response = client.get(
            "/collaborator/setup?token=must-not-reflect-a-secret",
            headers={"Referer": "https://untrusted.example.test/"},
        )

    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("pragma") == "no-cache"
    assert "must-not-reflect-a-secret" not in response.text
    assert response.headers.get("set-cookie") is None
    assert 'id="invitePassword"' in response.text
    assert Path("static/collaborator/setup.html").is_file()


@pytest.fixture
def invitation_limiter(monkeypatch):
    from app.core import http_security

    monkeypatch.setattr(http_security, "LOGIN_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(http_security, "LOGIN_RATE_LIMIT_ATTEMPTS", 2)
    monkeypatch.setattr(http_security, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(http_security, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(http_security, "_attempts", defaultdict(deque))
    monkeypatch.setattr(http_security, "_attempts_lock", threading.Lock())
    assert "/api/collaborator-invitations/accept" in http_security.LOGIN_PATHS

    app = FastAPI()
    app.middleware("http")(http_security.login_rate_limit_middleware)

    @app.post("/api/collaborator-invitations/accept")
    def accept(data: dict):
        return JSONResponse(
            status_code=200 if data.get("accepted") else 400,
            content={"ok": bool(data.get("accepted"))},
        )

    @app.post("/api/collaborator-invitations/info")
    def info():
        return {"ok": True}

    @app.post("/api/login")
    def login():
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})

    with TestClient(app) as client:
        yield client


def test_invalid_invitation_acceptance_is_rate_limited_but_info_is_not(invitation_limiter):
    client = invitation_limiter
    for _ in range(6):
        assert client.post("/api/collaborator-invitations/info", json={}).status_code == 200
    for _ in range(2):
        assert client.post(
            "/api/collaborator-invitations/accept", json={"accepted": False}
        ).status_code == 400
    limited = client.post(
        "/api/collaborator-invitations/accept", json={"accepted": False}
    )
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    assert client.post("/api/collaborator-invitations/info", json={}).status_code == 200
    # Counters are endpoint-specific; adding invites does not weaken login limits.
    assert client.post("/api/login", json={}).status_code == 401
    assert client.post("/api/login", json={}).status_code == 401
    assert client.post("/api/login", json={}).status_code == 429


def test_successful_invitation_acceptance_clears_its_rate_counter(invitation_limiter):
    client = invitation_limiter
    assert client.post(
        "/api/collaborator-invitations/accept", json={"accepted": False}
    ).status_code == 400
    assert client.post(
        "/api/collaborator-invitations/accept", json={"accepted": True}
    ).status_code == 200
    for _ in range(2):
        assert client.post(
            "/api/collaborator-invitations/accept", json={"accepted": False}
        ).status_code == 400
    assert client.post(
        "/api/collaborator-invitations/accept", json={"accepted": False}
    ).status_code == 429


@pytest.mark.parametrize("environment,base_url", [
    ("development", "http://localhost:8000"),
    ("development", "http://localhost:8000/girofacile"),
    ("development", "https://invites.example.test"),
    ("production", "https://invites.example.test"),
    ("prod", "https://invites.example.test"),
])
def test_setup_url_uses_configured_public_origin_and_fragment(
    monkeypatch, environment, base_url
):
    from app.services import collaborator_invitations as invitations

    monkeypatch.setattr(invitations, "APP_ENV", environment)
    monkeypatch.setattr(invitations, "APP_BASE_URL", base_url)
    token = "synthetic-token-for-tests"
    result = invitations._setup_url(token)
    parsed = urlsplit(result)
    assert result.startswith(base_url.rstrip("/") + "/collaborator/setup#")
    assert parsed.query == ""
    assert parsed.fragment == "token=" + token
    assert token not in parsed.path
    assert token not in parsed.netloc


@pytest.mark.parametrize("environment,base_url", [
    ("production", "http://invites.example.test"),
    ("prod", "http://invites.example.test"),
    ("development", "javascript:alert(1)"),
    ("development", "ftp://invites.example.test"),
    ("development", "https:///missing-host"),
    ("development", "https://user:password@invites.example.test"),
    ("development", "https://invites.example.test?token=leak"),
    ("development", "https://invites.example.test#fragment"),
    ("development", "https://[broken-ipv6"),
    ("development", "https://invites.example.test:invalid-port"),
    ("development", "https://invites.example.test:99999"),
    ("development", ""),
])
def test_invalid_setup_configuration_fails_safely(monkeypatch, environment, base_url):
    from app.services import collaborator_invitations as invitations

    monkeypatch.setattr(invitations, "APP_ENV", environment)
    monkeypatch.setattr(invitations, "APP_BASE_URL", base_url)
    with pytest.raises(HTTPException) as error:
        invitations._setup_url("synthetic-token-for-tests")
    assert error.value.status_code == 503
    assert "synthetic-token-for-tests" not in str(error.value.detail)
    assert "user:password" not in str(error.value.detail)
