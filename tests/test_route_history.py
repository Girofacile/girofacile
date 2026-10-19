"""History filters precede bounded pages and keep company isolation."""
from datetime import date, datetime, time, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def history(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from app.database import Base, get_db
    from app.models import Delivery, Driver, RoutePlan, User, Vehicle
    from app.routers.routes import router
    from app.core.dependencies import current_user
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner, other = User(username="history-owner", password_hash="test"), User(username="history-other", password_hash="test")
        db.add_all([owner, other])
        db.flush()
        drivers = [Driver(user_id=owner.id, nome=f"Autista {i}") for i in range(12)]
        vehicles = [Vehicle(user_id=owner.id, nome=f"Mezzo {i}", targa=f"TEST{i:03}") for i in range(12)]
        db.add_all(drivers + vehicles)
        db.flush()
        for i in range(230):
            row = RoutePlan(user_id=owner.id, nome=f"Archivio {i:03}",
                data_giro=date(2025, 1, 1)+timedelta(days=i), orario_partenza=time(8),
                status="annullato" if i % 2 else "completato",
                driver_id=drivers[i % 12].id, vehicle_id=vehicles[i % 12].id,
                created_at=datetime(2025, 1, 1)+timedelta(seconds=i))
            db.add(row)
            db.flush()
            db.add_all([Delivery(route_plan_id=row.id, cliente_nome=f"Cliente {n}", indirizzo="Via Test")
                        for n in range(i % 3)])
        db.add_all([RoutePlan(user_id=owner.id, nome=f"Aperto {i}", data_giro=date(2026, 10, 18),
            orario_partenza=time(8), status="programmato", created_at=datetime(2026, 10, 18)) for i in range(250)])
        db.add(RoutePlan(user_id=other.id, nome="Archivio altrui", data_giro=date(2025, 1, 1),
            orario_partenza=time(8), status="completato", created_at=datetime(2026, 10, 19)))
        db.commit()
        owner_id, other_id = owner.id, other.id
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[current_user] = lambda: db.get(User, owner_id)
        with TestClient(app) as client:
            yield client, db, engine, owner_id, other_id
    engine.dispose()


def test_all_old_closed_routes_are_reachable_with_array_compatibility(history):
    client, *_ = history
    response = client.get("/api/routes")
    assert response.status_code == 200
    assert isinstance(response.json(), list) and len(response.json()) == 100
    assert response.headers["x-total-count"] == "230"
    rows, page = [], 1
    while page:
        response = client.get("/api/routes", params={"page": page, "page_size": 100, "with_meta": True})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["total"] == 230 and len(data["items"]) <= 100
        rows.extend(data["items"])
        page = data["next_page"]
    assert len(rows) == len({r["id"] for r in rows}) == 230
    assert rows[-1]["nome"] == "Archivio 000"
    assert all(r["status"] in ("completato", "annullato") for r in rows)
    assert all(r["nome"] != "Archivio altrui" for r in rows)


def test_filters_precede_pagination_and_preserve_tenant_scope(history):
    client, db, _, _, other_id = history
    from app.models import User
    result = client.get("/api/routes", params={"q": "Archivio 000", "with_meta": True}).json()
    assert result["total"] == 1 and result["items"][0]["nome"] == "Archivio 000"
    result = client.get("/api/routes", params={"date_from": "2025-01-01", "date_to": "2025-01-01", "with_meta": True}).json()
    assert result["total"] == 1
    result = client.get("/api/routes", params={"q": "TEST000", "status": "completato", "with_meta": True}).json()
    assert result["total"] == 20
    row = result["items"][0]
    assert all(r["vehicle_id"] == row["vehicle_id"] for r in result["items"])
    result = client.get("/api/routes", params={"driver_id": row["driver_id"], "vehicle_id": row["vehicle_id"],
        "status": "completato", "with_meta": True}).json()
    assert result["total"] == 20
    assert client.get("/api/routes?q=%25&with_meta=true").json()["total"] == 0
    from app.core.dependencies import current_user
    client.app.dependency_overrides[current_user] = lambda: db.get(User, other_id)
    result = client.get("/api/routes?with_meta=true").json()
    assert result["total"] == 1 and result["items"][0]["nome"] == "Archivio altrui"


def test_page_queries_do_not_grow_with_route_or_stop_count(history):
    client, db, engine, owner_id, _ = history
    from app.models import User
    from app.core.dependencies import current_user
    owner = db.get(User, owner_id)
    owner.id
    db.expunge(owner)
    db.expire_all()
    client.app.dependency_overrides[current_user] = lambda: owner
    selects = []
    def track(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)
    event.listen(engine, "before_cursor_execute", track)
    try:
        response = client.get("/api/routes?page_size=100&with_meta=true")
        assert response.status_code == 200, response.text
        rows = response.json()["items"]
        assert len(rows) == 100 and len(selects) <= 3, selects
        for row in rows:
            assert row["consegne_count"] == int(row["nome"].rsplit(" ", 1)[1]) % 3
            assert row["driver_name"].startswith("Autista ") and "TEST" in row["vehicle_name"]
    finally:
        event.remove(engine, "before_cursor_execute", track)


@pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "status=programmato",
    "date_from=2026-10-20&date_to=2026-10-01", "driver_id=0", "vehicle_id=0"])
def test_invalid_history_parameters_are_rejected(history, query):
    assert history[0].get("/api/routes?"+query).status_code == 422
