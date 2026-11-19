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


def test_complimentary_access_has_no_payment_and_no_expiry(admin_fleet):
    """Account scelti dall'amministratore: piano attivo senza abbonamento né scadenza."""
    from datetime import timedelta
    from app.core.clock import utc_now
    from app.services.plans import get_user_plan_status
    client, db, user, *_ = admin_fleet
    user.plan, user.plan_status, user.plan_expires_at = "starter", "expired", utc_now() - timedelta(days=1)
    db.commit()
    response = client.put(f"/api/admin/users/{user.id}/plan", json={"plan": "pro", "plan_status": "expired", "complimentary": True})
    assert response.status_code == 200, response.text
    db.refresh(user)
    assert (user.plan, user.plan_status, user.plan_expires_at, user.billing_source) == ("pro", "active", None, "complimentary")
    assert get_user_plan_status(user) == "active"
    detail = client.get(f"/api/admin/users/{user.id}").json()
    assert detail["billing_source"] == "complimentary" and detail["plan_status"] == "active"


def test_refunded_stripe_account_can_receive_free_access(admin_fleet):
    """Abbonamento rimborsato o non pagato: non blocca più l'assegnazione e Stripe viene scollegato."""
    client, db, user, *_ = admin_fleet
    user.plan, user.plan_status, user.billing_source = "starter", "incomplete", "stripe_live"
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_cancel_at_period_end = "cus_live", "sub_live", True
    db.commit()
    response = client.put(f"/api/admin/users/{user.id}/plan", json={"plan": "business", "complimentary": True})
    assert response.status_code == 200, response.text
    db.refresh(user)
    assert user.stripe_customer_id is None and user.stripe_subscription_id is None
    assert not user.billing_cancel_at_period_end
    assert (user.plan, user.plan_status, user.billing_source) == ("business", "active", "complimentary")


def test_still_paying_stripe_subscription_is_not_overwritten(admin_fleet):
    client, db, user, *_ = admin_fleet
    user.plan, user.plan_status, user.billing_source = "business", "active", "stripe_live"
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_cancel_at_period_end = "cus_live", "sub_live", False
    db.commit()
    response = client.put(f"/api/admin/users/{user.id}/plan", json={"plan": "pro", "complimentary": True})
    assert response.status_code == 409 and "annullalo prima su Stripe" in response.json()["detail"]
    db.refresh(user)
    assert (user.plan, user.billing_source, user.stripe_subscription_id) == ("business", "stripe_live", "sub_live")
