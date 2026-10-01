"""Check admin registration and access boundaries across the split routers."""
from collections import Counter

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_admin_sections_match_compatibility_router_without_duplicates(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from app.main import app
    from app.routers import admin

    compatibility = FastAPI()
    compatibility.include_router(admin.router)
    actual = [route for route in app.routes if route.path.startswith("/api/admin/")]
    # Authentication endpoints remain in auth.py; compare the section routes.
    expected = {(route.path, method) for route in admin.router.routes for method in route.methods}
    counts = Counter((route.path, method) for route in actual for method in route.methods)
    assert all(counts[key] == 1 for key in expected)
    schema = app.openapi()
    for path, definition in compatibility.openapi()["paths"].items():
        assert schema["paths"][path] == definition


def test_every_admin_section_requires_authentication_and_collaborator_permissions(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from app.core.dependencies import require_superadmin
    from app.database import get_db
    from app.routers import admin

    app = FastAPI()
    app.include_router(admin.router)
    # Denied requests must not reach any database or external-service operation.
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        for route in admin.router.routes:
            path = route.path
            for parameter in route.param_convertors:
                value = "users" if parameter == "table_name" else "backup.dump" if parameter == "filename" else "1"
                path = path.replace("{" + parameter + "}", value)
            for method in route.methods:
                response = client.request(method, path, json={})
                assert response.status_code == 401, (method, path, response.text)

        app.dependency_overrides[require_superadmin] = lambda: {
            "username": "restricted", "role": "collaborator", "permissions": {},
        }
        for route in admin.router.routes:
            path = route.path
            for parameter in route.param_convertors:
                value = "users" if parameter == "table_name" else "backup.dump" if parameter == "filename" else "1"
                path = path.replace("{" + parameter + "}", value)
            for method in route.methods:
                response = client.request(method, path, json={})
                assert response.status_code == 403, (method, path, response.text)
