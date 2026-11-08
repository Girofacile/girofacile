"""Indirizzi per i test in locale: link (inviti, email, QR) su un indirizzo scelto dal portale admin."""
import pytest

from app.core import config, links
from test_agents_feature import env  # noqa: F401


@pytest.fixture(autouse=True)
def clean_override():
    links.set_override("")
    yield
    links.set_override("")


@pytest.fixture
def admin_client(env):  # noqa: F811
    from app.routers import admin
    from app.core.config import SUPERADMIN_USERNAME
    from app.core.security import make_superadmin_token
    client, db, *_ = env
    client.app.include_router(admin.router)
    client.cookies.set("superadmin_session", make_superadmin_token(SUPERADMIN_USERNAME))
    return client, db


def test_normalize_accepts_ip_and_port_only():
    assert links.normalize("192.168.1.20:8000") == "http://192.168.1.20:8000"
    assert links.normalize(" http://100.108.133.45:8000/ ") == "http://100.108.133.45:8000"
    assert links.normalize("") == ""
    for bad in ("http://192.168.1.20:8000/driver", "javascript:alert(1)", "http://a b"):
        with pytest.raises(ValueError):
            links.normalize(bad)


def test_override_changes_links_but_never_in_production(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")
    links.set_override("192.168.1.20:8000")
    assert links.base_url("https://girofacile.it") == "http://192.168.1.20:8000"
    monkeypatch.setattr(config, "APP_ENV", "production")
    assert links.base_url("https://girofacile.it/") == "https://girofacile.it"
    assert links.current_override() == ""


def test_admin_sets_the_address_used_by_driver_links(admin_client, monkeypatch):
    client, db = admin_client
    monkeypatch.setattr(config, "APP_ENV", "development")
    data = client.get("/api/admin/local-addresses").json()
    assert data["enabled"] is True and data["custom"] == ""
    assert {p["name"] for p in data["portals"]} >= {"Gestionale", "App autista", "Portale agenti", "Super Admin"}
    saved = client.put("/api/admin/local-addresses", json={"base_url": "192.168.1.20:8000"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["custom"] == "http://192.168.1.20:8000"
    assert "http://192.168.1.20:8000/driver" in [p["url"] for p in body["portals"]]
    # Il link dell'invito autista (setup e portale) usa l'indirizzo scelto.
    from app.routers import vehicles_drivers  # noqa: F401  (import del modulo: usa links.base_url)
    assert links.base_url(config.APP_BASE_URL) == "http://192.168.1.20:8000"
    assert client.put("/api/admin/local-addresses", json={"base_url": "http://x/driver"}).status_code == 422
    assert client.put("/api/admin/local-addresses", json={"base_url": ""}).json()["custom"] == ""


def test_production_refuses_the_test_address(admin_client, monkeypatch):
    client, _ = admin_client
    monkeypatch.setattr(config, "APP_ENV", "production")
    assert client.get("/api/admin/local-addresses").json()["enabled"] is False
    assert client.put("/api/admin/local-addresses", json={"base_url": "192.168.1.20:8000"}).status_code == 403
