import asyncio

import pytest

from app.core.production_check import (
    production_config_problems, production_config_warnings, require_production_config,
)

STRONG = {
    "APP_ENV": "production",
    "APP_SECRET": "k" * 48,
    "SUPERADMIN_PASSWORD": "Una-Password-Robusta-2026!",
}


def test_strong_production_config_is_accepted():
    assert production_config_problems(STRONG) == []
    require_production_config(STRONG)


@pytest.mark.parametrize("changes, expected", [
    ({"APP_SECRET": ""}, "APP_SECRET non impostato"),
    ({"APP_SECRET": "dev-secret-change-me"}, "valore di sviluppo"),
    ({"APP_SECRET": "corto"}, "troppo corto"),
    ({"SUPERADMIN_PASSWORD": ""}, "SUPERADMIN_PASSWORD non impostata"),
    ({"SUPERADMIN_PASSWORD": "admin123"}, "default o comune"),
    ({"SUPERADMIN_PASSWORD": "Breve1!"}, "troppo corta"),
    ({"COOKIE_SECURE": "false"}, "COOKIE_SECURE"),
    ({"DATABASE_URL": "sqlite:///girofacile.db"}, "SQLite"),
    ({"ALLOW_SQLITE_LEGACY": "true"}, "SQLite"),
    ({"APP_BASE_URL": "http://app.esempio.it"}, "https"),
    ({"OBJECT_STORAGE_ENABLED": "true", "OBJECT_STORAGE_BACKEND": "local"}, "locale non ammesso"),
    ({"OBJECT_STORAGE_ENABLED": "true", "OBJECT_STORAGE_BUCKET": "pod"}, "OBJECT_STORAGE_ENDPOINT"),
])
def test_weak_production_config_blocks_startup(changes, expected):
    env = {**STRONG, **changes}
    with pytest.raises(RuntimeError, match=expected):
        require_production_config(env)


def test_app_password_fallback_is_checked_when_superadmin_missing():
    env = {"APP_ENV": "prod", "APP_SECRET": "k" * 48, "APP_PASSWORD": "admin123"}
    with pytest.raises(RuntimeError, match="default o comune"):
        require_production_config(env)


def test_development_keeps_local_defaults():
    require_production_config({"APP_ENV": "development"})
    require_production_config({})


def test_lifespan_refuses_production_with_default_secret(monkeypatch):
    from app import main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("APP_SECRET", raising=False)
    monkeypatch.setenv("SUPERADMIN_PASSWORD", "Una-Password-Robusta-2026!")

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(RuntimeError, match="APP_SECRET"):
        asyncio.run(start())


def test_complete_s3_storage_and_https_are_accepted():
    env = {**STRONG, "APP_BASE_URL": "https://app.esempio.it", "OBJECT_STORAGE_ENABLED": "true",
           **{"OBJECT_STORAGE_" + k: "x" for k in ("ENDPOINT", "REGION", "BUCKET", "ACCESS_KEY", "SECRET_KEY")}}
    assert production_config_problems(env) == []


def test_missing_optional_services_only_warn(caplog):
    warnings = production_config_warnings(STRONG)
    assert any("SMTP" in w for w in warnings)
    assert any("ERROR_NOTIFICATIONS_EMAIL" in w for w in warnings)
    with caplog.at_level("WARNING"):
        require_production_config(STRONG)
    assert "SMTP" in caplog.text


def test_health_reports_database_state(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main

    class Broken:
        def connect(self):
            raise RuntimeError("database down")

    client = TestClient(main.app)
    monkeypatch.setattr(main, "engine", Broken())
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
