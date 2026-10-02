"""Administrative entitlement changes preserve fleets and recheck Stripe after locking."""
import pytest
from test_agents_feature import env


@pytest.fixture
def admin_fleet(env):
    from app.core.dependencies import require_superadmin
    from app.routers.admin_users import router
    from app.routers.vehicles_drivers import vehicles_router
    client = env[0]
    client.app.include_router(router)
    client.app.include_router(vehicles_router)
    client.app.dependency_overrides[require_superadmin] = lambda: {
        "username": "test-admin", "role": "superadmin", "permissions": {"all": True}}
    return env


def test_administrative_downgrade_reports_conflict_and_keeps_all_vehicles(admin_fleet):
    from app.models import Vehicle
    from app.services.plan_catalog import PLAN_LIMITS
    client, db, user, *_ = admin_fleet
    target = PLAN_LIMITS["starter"]
    fleet = [Vehicle(user_id=user.id, nome=f"Diesel {i}", alimentazione="gasolio")
             for i in range(target["max_vehicles"] + 1)]
    db.add_all(fleet)
    db.commit()
    before_ids = [item.id for item in fleet]
    response = client.put(f"/api/admin/users/{user.id}/plan", json={"plan": "starter", "reason": "Test"})
    assert response.status_code == 200
    body = response.json()
    assert body["vehicle_usage"]["over_limit"]
    assert body["warning"] and "I dati sono conservati" in body["warning"]
    assert db.query(Vehicle).filter(Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None)).count() == len(before_ids)
    assert client.post("/api/vehicles", json={"nome": "Extra EV", "alimentazione": "elettrico"}).status_code == 403
    assert all(db.get(Vehicle, item_id).deleted_at is None for item_id in before_ids)
    # A corrective conversion reduces the non-electric count; it does not lose records.
    converted = client.put(f"/api/vehicles/{before_ids[0]}", json={"nome": "Convertito", "alimentazione": "elettrico"})
    assert converted.status_code == 200
    assert not client.get("/api/vehicles/usage").json()["over_limit"]


def test_admin_plan_assignment_checks_current_stripe_link_after_lock(admin_fleet, monkeypatch):
    from app.routers import admin_users
    client, db, user, *_ = admin_fleet
    original_plan = user.plan

    def linked_while_waiting(owner, session):
        owner.stripe_subscription_id = "sub_linked_during_lock"
        return owner

    monkeypatch.setattr(admin_users, "lock_vehicle_owner", linked_while_waiting)
    response = client.put(f"/api/admin/users/{user.id}/plan", json={"plan": "pro"})
    assert response.status_code == 409
    assert "Stripe" in response.json()["detail"]
    assert user.plan == original_plan
