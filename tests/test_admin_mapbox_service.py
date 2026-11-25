"""Pannello Server: Mapbox compare tra i servizi collegati e il «Test» verifica davvero il token."""
import pytest
from test_agents_feature import env  # noqa: F401


@pytest.fixture
def panel(env):  # noqa: F811
    from app.core.dependencies import require_superadmin
    from app.routers.admin_server import router
    client = env[0]
    client.app.include_router(router)
    client.app.dependency_overrides[require_superadmin] = lambda: {"username": "owner", "role": "superadmin", "permissions": {"all": True}}
    return env


class _Response:
    def __init__(self, code):
        self.code = code
        self.headers = {"content-type": "application/json; charset=utf-8"}

    def json(self):
        return {"code": self.code}


@pytest.mark.parametrize("code,ok,text", [("TokenValid", True, "valido"), ("TokenInvalid", False, "rifiuta"), ("TokenExpired", False, "scaduto")])
def test_mapbox_listed_and_token_checked(panel, monkeypatch, code, ok, text):
    import requests
    from app.services import platform_settings
    from app.routers import admin_helpers
    client = panel[0]
    monkeypatch.setattr(platform_settings, "mapbox_access_token", lambda db=None: "pk.SEGRETO123456")
    monkeypatch.setattr(admin_helpers, "mapbox_access_token", lambda db=None: "pk.SEGRETO123456")
    calls = []
    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None: calls.append(url) or _Response(code))
    services = {s["key"]: s for s in client.get("/api/admin/server-maintenance").json()["services"]}
    assert services["mapbox"]["configured"] is True and "SEGRETO123456" not in services["mapbox"]["masked"]
    result = client.post("/api/admin/server-maintenance/test-service", json={"service": "mapbox"}).json()
    assert result["ok"] is ok and text in result["message"] and "SEGRETO" not in result["message"]
    assert calls == ["https://api.mapbox.com/tokens/v2"]
