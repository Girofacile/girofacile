"""Regression checks for the composed administration router."""
import inspect
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")

import pytest
from fastapi import HTTPException

from app.core.dependencies import require_superadmin
from app.routers.admin import router


def test_admin_routes_are_registered_once_and_require_authentication():
    assert len(router.routes) == 38
    identities = [(route.path, tuple(sorted(route.methods))) for route in router.routes]
    assert len(set(identities)) == 38
    for route in router.routes:
        assert route.path.startswith("/api/admin/")
        assert route.tags == ["admin"]
        assert require_superadmin in [dep.call for dep in route.dependant.dependencies]


@pytest.mark.parametrize("route", router.routes, ids=lambda route: route.name)
def test_collaborator_without_permissions_is_denied_before_accessing_data(route):
    kwargs = {"superadmin": {"role": "collaborator", "permissions": {}}, "db": None}
    signature = inspect.signature(route.endpoint)
    if "db" not in signature.parameters:
        kwargs.pop("db")
    for name, parameter in signature.parameters.items():
        if name not in kwargs and parameter.default is inspect.Parameter.empty:
            kwargs[name] = {} if name == "payload" else "unused"
    with pytest.raises(HTTPException) as exc:
        route.endpoint(**kwargs)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Permesso collaboratore non abilitato"
