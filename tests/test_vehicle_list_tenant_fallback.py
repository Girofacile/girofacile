"""Il fallback legacy del registro mezzi non deve mai ignorare il filtro aziendale."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.routers import vehicles_drivers


def _session(ddl, rows):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(ddl))
        for row in rows:
            conn.execute(text(row))
    return sessionmaker(bind=engine)()


@pytest.fixture
def broken_orm(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("ORM non disponibile")
    monkeypatch.setattr(vehicles_drivers, "owned", fail)
    monkeypatch.setattr(vehicles_drivers, "vehicle_to_dict", lambda item, _db: {"nome": item.nome, "user_id": getattr(item, "user_id", None)})


def test_fallback_without_tenant_column_refuses(broken_orm):
    db = _session("CREATE TABLE vehicles (id INTEGER PRIMARY KEY, nome TEXT)",
                  ["INSERT INTO vehicles (nome) VALUES ('Mezzo altra azienda')"])
    with pytest.raises(HTTPException) as exc:
        vehicles_drivers.list_vehicles(db=db, user=SimpleNamespace(id=1))
    assert exc.value.status_code == 503


def test_fallback_filters_by_company(broken_orm):
    db = _session("CREATE TABLE vehicles (id INTEGER PRIMARY KEY, nome TEXT, user_id INTEGER, deleted_at TEXT)",
                  ["INSERT INTO vehicles (nome, user_id) VALUES ('Mio', 1)",
                   "INSERT INTO vehicles (nome, user_id) VALUES ('Altrui', 2)",
                   "INSERT INTO vehicles (nome, user_id, deleted_at) VALUES ('Archiviato', 1, '2026-01-01')"])
    result = vehicles_drivers.list_vehicles(db=db, user=SimpleNamespace(id=1))
    assert [v["nome"] for v in result] == ["Mio"]
