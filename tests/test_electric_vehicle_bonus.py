"""Electric fleet bonus contract and lifecycle against isolated databases only."""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def fleet_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.core.dependencies import current_user
    from app.database import Base, get_db
    from app.models import User
    from app.routers.billing import router as billing_router
    from app.routers.vehicles_drivers import vehicles_router
    from app.services.usage_limits import guard_company_write

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="fleet-owner", password_hash="test", plan="business", plan_status="active")
        other = User(username="fleet-other", password_hash="test", plan="business", plan_status="active")
        db.add_all([owner, other])
        db.commit()
        app = FastAPI()
        app.include_router(vehicles_router)
        app.include_router(billing_router)

        def authenticate(request: Request):
            guard_company_write(request, owner)
            return owner

        app.dependency_overrides[current_user] = authenticate
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db, owner, other
    engine.dispose()


def seed_fleet(ctx, non_electric=0, electric=0, *, owner=None):
    from app.models import Vehicle
    _, db, default_owner, _ = ctx
    owner = owner or default_owner
    rows = [Vehicle(user_id=owner.id, nome=f"Standard {uuid.uuid4().hex}", alimentazione="gasolio")
            for _ in range(non_electric)] + [
        Vehicle(user_id=owner.id, nome=f"Electric {uuid.uuid4().hex}", alimentazione="elettrico")
        for _ in range(electric)]
    db.add_all(rows)
    db.commit()
    return rows


def create_vehicle(ctx, fuel="elettrico"):
    return ctx[0].post("/api/vehicles", json={"nome": "Nuovo mezzo", "alimentazione": fuel})


def usage(ctx):
    response = ctx[0].get("/api/vehicles/usage")
    assert response.status_code == 200, response.text
    return response.json()


def set_plan(ctx, plan):
    ctx[2].plan = plan
    ctx[1].commit()


@pytest.mark.parametrize("plan,standard,bonus", [("starter", 3, 1), ("business", 10, 2), ("pro", 50, 5)])
def test_bonus_at_standard_limit_and_one_extra_is_blocked(fleet_env, plan, standard, bonus):
    # Requested scenarios 1-6 using the approved current standard limits.
    ctx = fleet_env
    set_plan(ctx, plan)
    seed_fleet(ctx, non_electric=standard)
    for _ in range(bonus):
        created = create_vehicle(ctx)
        assert created.status_code == 200, created.text
    current = usage(ctx)
    assert current["standard_limit"] == standard
    assert current["electric_bonus"] == bonus
    assert current["total_limit"] == standard + bonus
    assert current["total_used"] == standard + bonus
    assert current["standard_used"] == standard and current["bonus_used"] == bonus
    assert not current["can_add_electric"] and not current["can_add_non_electric"]
    assert create_vehicle(ctx).status_code == 403
    assert usage(ctx)["total_used"] == standard + bonus


@pytest.mark.parametrize("fuel", ["gasolio", "diesel", "benzina", "gpl", "metano", "ibrido_benzina",
    "ibrido_gasolio", "ibrido_plugin_benzina", "ibrido_plugin_gasolio", "ibrido"])
def test_every_non_electric_fuel_uses_standard_slots(fleet_env, fuel):
    ctx = fleet_env
    seed_fleet(ctx, non_electric=10)
    rejected = create_vehicle(ctx, fuel)
    assert rejected.status_code == 403, rejected.text
    assert "elettric" in rejected.json()["detail"].lower()
    assert "2" in rejected.json()["detail"]
    current = usage(ctx)
    assert current["total_used"] == 10 and current["bonus_remaining"] == 2
    assert current["can_add_electric"] and not current["can_add_non_electric"]


@pytest.mark.parametrize("non_electric,electric,standard_used,bonus_used", [
    (0, 1, 0, 1), (8, 1, 8, 1), (8, 4, 10, 2), (10, 2, 10, 2), (0, 12, 10, 2)])
def test_bonus_first_allocation_supports_mixed_and_fully_electric_fleets(
    fleet_env, non_electric, electric, standard_used, bonus_used
):
    ctx = fleet_env
    seed_fleet(ctx, non_electric, electric)
    current = usage(ctx)
    assert current["non_electric_used"] == non_electric
    assert current["electric_used"] == electric
    assert current["standard_used"] == standard_used
    assert current["bonus_used"] == bonus_used
    assert current["standard_remaining"] == 10 - standard_used
    assert current["bonus_remaining"] == 2 - bonus_used
    assert current["total_remaining"] == 12 - non_electric - electric
    assert not current["over_limit"]


def test_bonus_electrics_do_not_prevent_standard_vehicle_creation(fleet_env):
    ctx = fleet_env
    seed_fleet(ctx, non_electric=9, electric=2)
    assert create_vehicle(ctx, "gasolio").status_code == 200
    assert usage(ctx)["total_used"] == 12


def test_electric_to_non_electric_conflict_is_rejected_without_mutation(fleet_env):
    ctx = fleet_env
    electric = seed_fleet(ctx, non_electric=10, electric=1)[-1]
    rejected = ctx[0].put(f"/api/vehicles/{electric.id}", json={"nome": electric.nome, "alimentazione": "benzina"})
    assert rejected.status_code == 403
    assert "standard" in rejected.json()["detail"].lower() or "inclus" in rejected.json()["detail"].lower()
    ctx[1].refresh(electric)
    assert electric.alimentazione == "elettrico"
    assert usage(ctx)["non_electric_used"] == 10


def test_electric_to_non_electric_is_allowed_when_standard_slot_is_free(fleet_env):
    ctx = fleet_env
    electric = seed_fleet(ctx, non_electric=9, electric=2)[-1]
    response = ctx[0].put(f"/api/vehicles/{electric.id}", json={"nome": electric.nome, "alimentazione": "gasolio"})
    assert response.status_code == 200, response.text
    current = usage(ctx)
    assert (current["standard_used"], current["bonus_used"]) == (10, 1)


def test_deletion_releases_bonus_and_preserves_the_vehicle_record(fleet_env):
    from app.models import Vehicle
    ctx = fleet_env
    electric = seed_fleet(ctx, non_electric=10, electric=2)[-1]
    assert ctx[0].delete(f"/api/vehicles/{electric.id}").status_code == 200
    current = usage(ctx)
    assert current["bonus_used"] == 1 and current["bonus_remaining"] == 1
    archived = ctx[1].get(Vehicle, electric.id)
    assert archived is not None and archived.deleted_at is not None and not archived.is_active
    assert create_vehicle(ctx).status_code == 200
    assert usage(ctx)["total_used"] == 12


def test_inactive_live_vehicles_count_but_archived_vehicles_do_not(fleet_env):
    ctx = fleet_env
    rows = seed_fleet(ctx, non_electric=10, electric=2)
    rows[0].is_active = False
    rows[-1].deleted_at = datetime.utcnow()
    rows[-1].is_active = False
    ctx[1].commit()
    current = usage(ctx)
    assert current["non_electric_used"] == 10 and current["electric_used"] == 1
    assert create_vehicle(ctx, "gasolio").status_code == 403
    assert create_vehicle(ctx).status_code == 200



def test_company_usage_and_mutations_are_tenant_scoped(fleet_env):
    ctx = fleet_env
    foreign = seed_fleet(ctx, non_electric=30, electric=10, owner=ctx[3])[-1]
    seed_fleet(ctx, non_electric=1, electric=1)
    assert usage(ctx)["total_used"] == 2
    assert ctx[0].put(f"/api/vehicles/{foreign.id}", json={"nome": "Foreign", "alimentazione": "gasolio"}).status_code == 404
    assert ctx[0].delete(f"/api/vehicles/{foreign.id}").status_code == 404
    assert create_vehicle(ctx).status_code == 200
    ctx[1].refresh(foreign)
    assert foreign.alimentazione == "elettrico" and foreign.deleted_at is None


def test_catalog_drives_api_public_plans_and_custom_bonus(fleet_env, monkeypatch):
    from app.services.plan_catalog import PLAN_LIMITS
    ctx = fleet_env
    catalog = ctx[0].get("/api/billing/plans").json()
    assert [(p["id"], p["limits"]["electric_vehicle_bonus"]) for p in catalog] == [
        ("starter", 1), ("business", 2), ("pro", 5)]
    assert [p["limits"]["max_vehicles"] for p in catalog] == [3, 10, 50]
    script = ctx[0].get("/api/billing/catalog.js").text
    public = json.loads(script.split(" = ", 1)[1].rstrip(";"))
    assert public["business"]["electric_vehicle_bonus"] == 2
    monkeypatch.setitem(PLAN_LIMITS["business"], "electric_vehicle_bonus", 3)
    seed_fleet(ctx, non_electric=10, electric=2)
    assert usage(ctx)["electric_bonus"] == 3
    assert create_vehicle(ctx).status_code == 200
    assert create_vehicle(ctx).status_code == 403


def stripe_subscription(ctx, plan, *, pending=False, cancel=False):
    end = int((datetime.now() + timedelta(days=30)).timestamp())
    result = {
        "id": "sub-fleet", "customer": ctx[2].stripe_customer_id, "livemode": False,
        "status": "active", "collection_method": "charge_automatically", "cancel_at_period_end": cancel,
        "items": {"data": [{"id": "si-fleet", "quantity": 1, "price": {"id": "price-" + plan}, "current_period_end": end}]},
        "latest_invoice": {"status": "open" if pending else "paid"}}
    if pending:
        result["pending_update"] = {"expires_at": end}
    return result


def setup_stripe_catalog(ctx, monkeypatch):
    from app.services.plan_catalog import PLAN_PRICES
    ctx[2].stripe_customer_id = "cus-fleet"
    ctx[1].commit()
    for key, info in PLAN_PRICES.items():
        monkeypatch.setitem(info, "stripe_price_id", "price-" + key)


def test_paid_upgrade_updates_bonus_immediately_and_pending_upgrade_does_not(fleet_env, monkeypatch):
    from app.services.billing import sync_subscription
    ctx = fleet_env
    setup_stripe_catalog(ctx, monkeypatch)
    set_plan(ctx, "starter")
    seed_fleet(ctx, non_electric=3, electric=1)
    sync_subscription(ctx[1], ctx[2], stripe_subscription(ctx, "business", pending=True))
    ctx[1].commit()
    assert usage(ctx)["electric_bonus"] == 1
    assert create_vehicle(ctx).status_code == 403
    sync_subscription(ctx[1], ctx[2], stripe_subscription(ctx, "business"))
    ctx[1].commit()
    current = usage(ctx)
    assert current["plan"] == "business" and current["electric_bonus"] == 2
    assert current["total_limit"] == 12
    assert create_vehicle(ctx).status_code == 200


def test_pending_downgrade_keeps_current_bonus_until_effective_plan_changes(fleet_env):
    ctx = fleet_env
    ctx[2].billing_pending_plan = "starter"
    ctx[1].commit()
    seed_fleet(ctx, non_electric=10, electric=1)
    current = usage(ctx)
    assert current["plan"] == "business" and current["electric_bonus"] == 2
    assert create_vehicle(ctx).status_code == 200


def test_downgrade_excess_accepts_bonus_fleet_and_rejects_non_electric_excess(fleet_env):
    from app.services.billing import downgrade_excess
    ctx = fleet_env
    rows = seed_fleet(ctx, non_electric=3, electric=1)
    assert downgrade_excess(ctx[1], ctx[2], "starter") == []
    rows[-1].alimentazione = "gasolio"
    ctx[1].commit()
    excess = downgrade_excess(ctx[1], ctx[2], "starter")
    assert excess and any("mezz" in item.lower() for item in excess)
    rows[-1].alimentazione = "elettrico"
    ctx[1].commit()
    seed_fleet(ctx, electric=1)
    assert downgrade_excess(ctx[1], ctx[2], "starter")


def test_preventive_downgrade_blocks_before_calling_stripe_schedule(fleet_env, monkeypatch):
    from app.services import billing
    ctx = fleet_env
    setup_stripe_catalog(ctx, monkeypatch)
    seed_fleet(ctx, non_electric=4)
    ctx[2].stripe_subscription_id = "sub-fleet"
    ctx[2].billing_source = "stripe_test"
    ctx[1].commit()
    sub = stripe_subscription(ctx, "business")
    fake = SimpleNamespace(Subscription=SimpleNamespace(retrieve=lambda *a, **k: sub))
    monkeypatch.setattr(billing, "stripe_client", lambda *a: fake)
    monkeypatch.setattr(billing, "price_for", lambda *a: "price-starter")
    rejected = ctx[0].post("/api/billing/change-plan", json={"plan": "starter"})
    assert rejected.status_code == 409
    assert ctx[2].plan == "business" and ctx[2].billing_pending_plan is None
    assert usage(ctx)["total_used"] == 4


def test_administrative_downgrade_keeps_data_and_allows_corrections_only(fleet_env):
    from app.models import Vehicle
    ctx = fleet_env
    rows = seed_fleet(ctx, non_electric=4, electric=2)
    set_plan(ctx, "starter")
    current = usage(ctx)
    assert current["over_limit"] and current["over_standard"] and current["over_total"]
    assert current["standard_remaining"] == 0 and current["total_remaining"] == 0
    assert not current["can_add_electric"] and not current["can_add_non_electric"]
    assert current["message"]
    assert create_vehicle(ctx).status_code == 403
    assert create_vehicle(ctx, "benzina").status_code == 403
    assert ctx[0].put(f"/api/vehicles/{rows[0].id}", json={"nome": "Rinominato", "alimentazione": "gasolio"}).status_code == 200
    assert ctx[0].put(f"/api/vehicles/{rows[0].id}", json={"nome": "Rinominato", "alimentazione": "elettrico"}).status_code == 200
    assert not usage(ctx)["over_standard"] and usage(ctx)["over_total"]
    assert ctx[0].put(f"/api/vehicles/{rows[0].id}", json={"nome": "Rinominato", "alimentazione": "gasolio"}).status_code == 403
    assert ctx[1].query(Vehicle).filter(Vehicle.user_id == ctx[2].id).count() == 6
    for item in rows[-2:]:
        assert ctx[0].delete(f"/api/vehicles/{item.id}").status_code == 200
    current = usage(ctx)
    assert current["total_used"] == 4 and not current["over_limit"]
    assert len(ctx[0].get("/api/vehicles").json()) == 4
    assert ctx[1].query(Vehicle).filter(Vehicle.user_id == ctx[2].id).count() == 6


@pytest.mark.parametrize("status", ["expired", "cancelled", "incomplete", "unpaid"])
def test_inactive_subscription_cannot_use_bonus_but_can_read_fleet(fleet_env, status):
    ctx = fleet_env
    seed_fleet(ctx, non_electric=1, electric=1)
    ctx[2].plan_status = status
    ctx[1].commit()
    current = usage(ctx)
    assert not current["plan_active"]
    assert not current["can_add_electric"] and not current["can_add_non_electric"]
    assert create_vehicle(ctx).status_code == 403
    assert len(ctx[0].get("/api/vehicles").json()) == 2


def test_scheduled_cancellation_keeps_bonus_until_access_expires(fleet_env, monkeypatch):
    from app.services.billing import sync_subscription
    ctx = fleet_env
    setup_stripe_catalog(ctx, monkeypatch)
    sync_subscription(ctx[1], ctx[2], stripe_subscription(ctx, "business", cancel=True))
    ctx[1].commit()
    assert ctx[2].billing_cancel_at_period_end
    seed_fleet(ctx, non_electric=10, electric=1)
    assert usage(ctx)["plan_active"]
    assert create_vehicle(ctx).status_code == 200
    ctx[2].plan_expires_at = datetime.utcnow() - timedelta(seconds=1)
    ctx[1].commit()
    assert not usage(ctx)["plan_active"]
    assert create_vehicle(ctx).status_code == 403
    assert usage(ctx)["total_used"] == 12



def test_electric_normalization_and_plugin_hybrids_do_not_get_bonus(fleet_env):
    ctx = fleet_env
    seed_fleet(ctx, non_electric=10)
    result = create_vehicle(ctx, "  ELETTRICO  ")
    assert result.status_code == 200, result.text
    assert result.json()["alimentazione"] == "elettrico"
    assert usage(ctx)["electric_used"] == 1
    assert create_vehicle(ctx, "ibrido_plugin_benzina").status_code == 403


def test_legacy_unknown_fuel_cannot_be_used_to_claim_bonus(fleet_env):
    from app.models import Vehicle
    ctx = fleet_env
    seed_fleet(ctx, non_electric=9)
    unknown = Vehicle(user_id=ctx[2].id, nome="Legacy", alimentazione="unknown")
    ctx[1].add(unknown)
    ctx[1].commit()
    assert usage(ctx)["non_electric_used"] == 10
    assert create_vehicle(ctx, "gasolio").status_code == 403
    assert create_vehicle(ctx).status_code == 200


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="TEST_POSTGRES_URL not configured")
def test_postgres_concurrent_creations_cannot_take_the_same_last_bonus_slot():
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.database import Base
    from app.models import User, Vehicle
    from app.services.plans import check_vehicle_limit, vehicle_usage

    engine = create_engine(os.environ["TEST_POSTGRES_URL"])
    schema = "fleet_bonus_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA " + schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        with Session(isolated) as db:
            owner = User(username="quota-owner", password_hash="test", plan="starter", plan_status="active")
            db.add(owner)
            db.flush()
            owner_id = owner.id
            db.add_all([Vehicle(user_id=owner_id, nome=f"Diesel {i}", alimentazione="gasolio") for i in range(3)])
            db.commit()
        barrier = Barrier(2)

        def create(index):
            with Session(isolated) as db:
                db.execute(text("SET LOCAL lock_timeout = '10s'"))
                owner = db.get(User, owner_id)
                barrier.wait(timeout=10)
                try:
                    check_vehicle_limit(owner, db, alimentazione="elettrico")
                    db.add(Vehicle(user_id=owner_id, nome=f"Bonus {index}", alimentazione="elettrico"))
                    db.commit()
                    return 200
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(create, [0, 1])) == [200, 403]
        with Session(isolated) as db:
            current = vehicle_usage(db.get(User, owner_id), db)
            assert current["total_used"] == 4 and current["bonus_used"] == 1
            assert not current["over_limit"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        engine.dispose()

@pytest.mark.parametrize("raw,expected", [
    ("Hybrid Electric", "ibrido_benzina"),
    ("plug-in hybrid petrol", "ibrido_plugin_benzina"),
    ("plug-in hybrid diesel", "ibrido_plugin_diesel"),
    ("Electric", "elettrico"),
])
def test_plate_lookup_keeps_hybrids_out_of_the_electric_bonus(raw, expected):
    from app.services.vehicle_lookup import _fuel_to_internal
    assert _fuel_to_internal(raw) == expected
