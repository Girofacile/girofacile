"""Admin diagnostics exercise real authentication and only mock the OSRM HTTP call."""
import json
import requests
import pytest
from app.services import platform_settings as settings, routing_health as health
from app.models import DistanceCache, RoutePlan, ApiUsageLog
from test_agents_feature import env


class Response:
    status_code = 200

    def json(self):
        return {"code": "Ok", "waypoints": [{"location": [14.25, 40.85]}]}


@pytest.fixture
def diagnostic(env, monkeypatch):
    from app.routers import admin
    from app.core.config import SUPERADMIN_USERNAME
    from app.core.security import make_superadmin_token
    client, db, *_ = env
    client.app.include_router(admin.router)
    client.cookies.set("superadmin_session", make_superadmin_token(SUPERADMIN_USERNAME))
    monkeypatch.setenv("OSRM_URL", "http://osrm:5000")
    monkeypatch.setenv("TRAFFIC_PROVIDER", "mapbox")
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "sensitive-mapbox-token")
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        assert url == "http://osrm:5000/nearest/v1/driving/0,0"
        return Response()

    monkeypatch.setattr(health.requests, "get", get)
    return client, db, calls


def test_health_is_read_only_and_never_calls_mapbox(diagnostic):
    client, db, calls = diagnostic
    before = {m: db.query(m).count() for m in (DistanceCache, RoutePlan, ApiUsageLog)}
    result = client.get('/api/admin/routing-health')
    assert result.status_code == 200
    body = result.json()
    assert body["osrm"]["status"] == "ok" and body["osrm"]["reachable"]
    assert body["osrm"]["response_ms"] >= 0
    assert body["traffic"] == {"provider": "mapbox", "configured": True}
    assert len(calls) == 1
    assert calls[0][1] == {"params": {"number": 1}, "timeout": (2, 3), "allow_redirects": False}
    assert {m: db.query(m).count() for m in before} == before
    assert not db.new and not db.dirty and not db.deleted
    assert 'sensitive-mapbox-token' not in result.text and 'http://' not in result.text


def test_normal_company_session_is_not_superadmin(diagnostic):
    client, _, calls = diagnostic
    client.cookies.clear()
    # env overrides current_user to a company owner: still insufficient.
    assert client.get('/api/admin/routing-health').status_code == 401
    assert not calls


@pytest.mark.parametrize("permissions", [{}, {"view_server_maintenance": True}, {"test_service_connections": True}])
def test_collaborator_without_both_permissions_is_denied(diagnostic, permissions):
    from app.core.dependencies import current_superadmin
    client, _, calls = diagnostic
    client.app.dependency_overrides[current_superadmin] = lambda: {"role": "collaborator", "permissions": permissions}
    assert client.get('/api/admin/routing-health').status_code == 403
    assert not calls


@pytest.mark.parametrize("failure", [requests.Timeout, requests.ConnectionError])
def test_unreachable_has_no_exception_or_secret_details(diagnostic, monkeypatch, failure):
    client, _, _ = diagnostic
    def fail(*args, **kwargs):
        raise failure('http://username:password@host/?token=sensitive-mapbox-token')
    monkeypatch.setattr(health.requests, 'get', fail)
    response = client.get('/api/admin/routing-health')
    assert response.json()['osrm']['status'] == 'unreachable'
    assert response.json()['osrm']['reachable'] is False
    for secret in ('username', 'password', 'token=', 'sensitive-mapbox-token'):
        assert secret not in response.text


@pytest.mark.parametrize("status,payload", [(503, {}), (302, {}), (200, {"code": "NoSegment"}),
    (200, {"code": "Ok", "waypoints": []}), (200, []), (200, {"code": "Ok", "waypoints": ["bad"]})])
def test_invalid_http_or_osrm_payload(diagnostic, monkeypatch, status, payload):
    class BadResponse:
        status_code = status
        def json(self): return payload
    monkeypatch.setattr(health.requests, 'get', lambda *a, **k: BadResponse())
    body = diagnostic[0].get('/api/admin/routing-health').json()['osrm']
    assert body['status'] == 'invalid_response' and body['reachable']


@pytest.mark.parametrize("url", ['http://user:secret@host:5000', 'not-an-url', 'https://[broken'])
def test_invalid_config_does_not_leak_or_make_requests(diagnostic, monkeypatch, url):
    monkeypatch.setenv('OSRM_URL', url)
    client, _, calls = diagnostic
    result = client.get('/api/admin/routing-health')
    assert result.json()['osrm']['status'] == 'invalid_configuration'
    assert not result.json()['osrm']['configured'] and not calls
    assert 'secret' not in result.text and url not in result.text


@pytest.mark.parametrize('url', ['http://localhost:5000', 'http://osrm:5000'])
def test_url_from_environment_and_database_precedence(env, monkeypatch, url):
    _, db, *_ = env
    monkeypatch.setenv('OSRM_URL', url)
    assert settings.osrm_url(db) == url
    settings.set_platform_setting(db, 'osrm_url', 'http://localhost:5000')
    db.commit()
    assert settings.osrm_url(db) == 'http://localhost:5000'


def test_docker_diagnoses_saved_localhost_without_rewriting_it(diagnostic, monkeypatch):
    client, db, _ = diagnostic
    settings.set_platform_setting(db, 'osrm_url', 'http://localhost:5000')
    db.commit()
    monkeypatch.setenv('GIROFACILE_RUNTIME', 'docker-compose')
    calls = []
    monkeypatch.setattr(health.requests, 'get', lambda url, **kw: calls.append(url) or Response())
    body = client.get('/api/admin/routing-health').json()['osrm']
    assert body['configuration_source'] == 'database'
    assert body['warning'] == 'docker_loopback_configuration'
    assert calls == ['http://localhost:5000/nearest/v1/driving/0,0']
    assert settings.osrm_url(db) == 'http://localhost:5000'


@pytest.mark.parametrize('provider,token,expected', [('none', '', False), ('mapbox', '', False), ('mapbox', 'secret', True), ('secret-provider', 'secret', False)])
def test_traffic_status_only_checks_configuration(diagnostic, monkeypatch, provider, token, expected):
    monkeypatch.setenv('TRAFFIC_PROVIDER', provider)
    monkeypatch.setenv('MAPBOX_ACCESS_TOKEN', token)
    result = diagnostic[0].get('/api/admin/routing-health')
    assert result.json()['traffic']['configured'] is expected
    assert len(diagnostic[2]) == 1
    assert 'secret' not in result.text


def test_native_default_stays_localhost(monkeypatch):
    monkeypatch.delenv('OSRM_URL', raising=False)
    assert settings.osrm_url(None) == 'http://localhost:5000'
