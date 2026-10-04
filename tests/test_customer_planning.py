"""Only verified registry customers may enter new plans; history stays intact."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import Customer, Delivery, RoutePlan
from app.services.customer_planning import customer_is_plannable, PLANNING_ADDRESS_ERROR
from test_agents_feature import env
from test_routing_architecture import routing_env, payload, saved_route


INVALID = [
    ("da_verificare", 45, 9), ("non_trovato", 45, 9),
    ("", 45, 9), ("legacy", 45, 9),
    ("verificato", None, 9), ("verificato", 45, None),
    ("verificato", 91, 9), ("verificato", 45, 181),
]


@pytest.mark.parametrize("state,lat,lon", INVALID + [
    (None, 45, 9),
    ("verificato", float("nan"), 9), ("verificato", 45, float("inf"))])
def test_invalid_coordinates_or_state_are_ineligible(state, lat, lon):
    assert not customer_is_plannable(SimpleNamespace(stato_geocodifica=state, lat=lat, lon=lon))


def test_selector_filters_before_pagination_and_preserves_registry(routing_env):
    client, db, owner, other, valid, *_ = routing_env
    for i, (state, lat, lon) in enumerate(INVALID):
        row = Customer(user_id=owner.id, nome=f"A invalid {i}", indirizzo="Address",
                       stato_geocodifica=state, lat=lat, lon=lon)
        db.add(row)
    db.add(Customer(user_id=other.id, nome="Foreign", indirizzo="Address",
                    stato_geocodifica="verificato", lat=45, lon=9))
    db.commit()
    assert len(client.get("/api/customers").json()) == len(INVALID) + 1
    assert [r["id"] for r in client.get("/api/customers?planning_only=true&limit=1").json()] == [valid.id]
    assert client.get("/api/customers?planning_only=true&offset=1").json() == []
    assert client.get("/api/customers?planning_only=true&q=invalid").json() == []


@pytest.mark.parametrize("endpoint", ["optimize", "recalculate-manual"])
@pytest.mark.parametrize("state,lat,lon", INVALID)
def test_api_rejects_forged_verification_before_optimizer(routing_env, endpoint, state, lat, lon):
    client, db, _, _, customer, *_, calls = routing_env
    customer.stato_geocodifica, customer.lat, customer.lon = state, lat, lon
    db.commit()
    data = payload(routing_env)
    data["consegne"][0].update(stato_geocodifica="verificato", lat=45, lon=9)
    response = client.post("/api/routes/" + endpoint, json=data)
    assert response.status_code == 400, response.text
    assert response.json()["detail"] == PLANNING_ADDRESS_ERROR
    assert calls == []
    assert db.query(RoutePlan).count() == db.query(Delivery).count() == 0


@pytest.mark.parametrize("endpoint", ["optimize", "recalculate-manual"])
def test_foreign_customer_is_rejected_without_revealing_verification(routing_env, endpoint):
    client, db, _, other, customer, *_ = routing_env
    customer.user_id = other.id
    db.commit()
    response = client.post("/api/routes/" + endpoint, json=payload(routing_env))
    assert response.status_code == 400
    assert "azienda" in response.json()["detail"]
    assert db.query(RoutePlan).count() == 0


def test_verification_immediately_enables_picker_and_valid_plan(routing_env, monkeypatch):
    from app.routers import customers
    client, db, _, _, customer, *_ = routing_env
    customer.stato_geocodifica, customer.lat, customer.lon = "da_verificare", None, None
    db.commit()
    assert client.get("/api/customers?planning_only=true").json() == []
    monkeypatch.setattr(customers, "geocode_customer", lambda *a, **kw: {
        "status": "verificato", "lat": 0, "lon": 0, "formatted": "Verified address"})
    assert client.post(f"/api/customers/{customer.id}/verify-address").status_code == 200
    assert [r["id"] for r in client.get("/api/customers?planning_only=true").json()] == [customer.id]
    assert saved_route(routing_env)["id"]


def test_history_readable_and_edit_rejected_without_deleting_deliveries(routing_env):
    client, db, _, _, customer, *_ = routing_env
    route = saved_route(routing_env, two=True)
    before = client.get(f"/api/routes/{route['id']}").json()
    delivery_ids = [d.id for d in db.query(Delivery).order_by(Delivery.id)]
    customer.stato_geocodifica, customer.lat, customer.lon = "non_trovato", None, None
    db.commit()
    assert client.get(f"/api/routes/{route['id']}").json() == before
    assert client.get("/api/routes").status_code == 200
    data = payload(routing_env, two=True)
    data["route_id"] = route["id"]
    assert client.post("/api/routes/recalculate-manual", json=data).status_code == 400
    assert [d.id for d in db.query(Delivery).order_by(Delivery.id)] == delivery_ids


def test_persistence_barrier_reloads_customer_even_when_identity_is_cached(routing_env):
    from sqlalchemy import update
    from app.routers.routes import save_route_result
    from app.schemas import RoutePlanIn
    client, db, _, _, customer, _, vehicle, _ = routing_env
    # Simulate a verification change after the optimizer's initial validation.
    db.execute(update(Customer).where(Customer.id == customer.id).values(
        stato_geocodifica="da_verificare"), execution_options={"synchronize_session": False})
    assert customer.stato_geocodifica == "verificato"
    data = payload(routing_env)
    with pytest.raises(HTTPException) as exc:
        save_route_result(db, routing_env[2], RoutePlanIn(**data), {"ordered": data["consegne"]}, vehicle)
    assert exc.value.detail == PLANNING_ADDRESS_ERROR
    assert db.query(RoutePlan).count() == db.query(Delivery).count() == 0
