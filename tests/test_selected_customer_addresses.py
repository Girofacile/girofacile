"""Selected customers use the same lazy verification/correction workflow as orders."""
from app.models import Customer
from test_routing_architecture import routing_env
from test_agents_feature import env


def new_customer(db, owner, name="Da verificare"):
    customer = Customer(user_id=owner.id, nome=name, indirizzo="Via Test 1",
                        comune="Napoli", provincia="NA", stato_geocodifica="da_verificare")
    db.add(customer)
    db.commit()
    return customer


def test_selection_verifies_only_unverified_and_preserves_customer_data(routing_env, monkeypatch):
    from app.routers import customers
    client, db, owner, _, verified, *_ = routing_env
    pending = new_customer(db, owner)
    pending.note = "Note cliente salvate"
    pending.tempo_scarico_min = 25
    db.commit()
    calls = []
    def fake_geocode(address, city, province, **kwargs):
        calls.append((address, city, province))
        return {"status": "verificato", "lat": 40.84, "lon": 14.25,
                "formatted": "Via Test 1, Napoli", "source": "google", "confidence": 0.98}
    monkeypatch.setattr(customers, "geocode_address", fake_geocode)
    response = client.post("/api/customers/verify-selected",
                           json={"customer_ids": [verified.id, pending.id]})
    assert response.status_code == 200, response.text
    assert response.json() == {"issues": [], "aborted": False}
    assert calls == [("Via Test 1", "Napoli", "NA")]
    db.refresh(pending)
    assert pending.stato_geocodifica == "verificato"
    assert pending.note == "Note cliente salvate"
    assert pending.tempo_scarico_min == 25
    assert pending.lat == 40.84
    assert client.post("/api/customers/verify-selected", json={"customer_ids": [pending.id]}).json()["issues"] == []
    assert len(calls) == 1


def test_ambiguous_address_can_be_corrected_or_position_confirmed(routing_env, monkeypatch):
    from app.routers import customers
    client, db, owner, *_ = routing_env
    pending = new_customer(db, owner)
    monkeypatch.setattr(customers, "geocode_address", lambda *a, **kw: {
        "status": "da_verificare", "lat": 40.85, "lon": 14.26,
        "formatted": "Via simile", "source": "google", "confidence": 0.5,
    })
    response = client.post("/api/customers/verify-selected", json={"customer_ids": [pending.id]})
    assert response.status_code == 200, response.text
    issue = response.json()["issues"][0]
    assert issue["candidate"] == {"lat": 40.85, "lon": 14.26}
    payload = {"customer_id": pending.id, "original_address": "Via Test 1",
               "original_comune": "Napoli", "address": "Via Corretta 23",
               "comune": "Napoli", "provincia": "NA"}
    corrected = client.post("/api/customers/resolve-selected-address",
                            json=payload | {"action": "correct"})
    assert corrected.status_code == 200, corrected.text
    db.refresh(pending)
    assert pending.lat is None and pending.stato_geocodifica == "da_verificare"
    manual = client.post("/api/customers/resolve-selected-address",
                         json=payload | {"action": "manual", "original_address": "Via Corretta 23",
                                         "lat": 40.82, "lon": 14.22})
    assert manual.status_code == 200, manual.text
    db.refresh(pending)
    assert pending.stato_geocodifica == "verificato"
    assert pending.fonte_geocodifica == "manuale"
    assert pending.indirizzo == "Via Corretta 23"
    assert client.get("/api/customers?planning_only=true").status_code == 200


def test_selected_customer_verification_is_tenant_scoped(routing_env, monkeypatch):
    from app.routers import customers
    client, db, owner, other, *_ = routing_env
    owned = new_customer(db, owner, "Mio")
    foreign = new_customer(db, other, "Altro")
    calls = []
    monkeypatch.setattr(customers, "geocode_address", lambda *a, **kw: calls.append(True))
    response = client.post("/api/customers/verify-selected",
                           json={"customer_ids": [owned.id, foreign.id]})
    assert response.status_code == 404
    assert calls == []
    response = client.post("/api/customers/resolve-selected-address", json={
        "customer_id": foreign.id, "action": "manual", "original_address": "Via Test 1",
        "original_comune": "Napoli", "address": "Via Test 1", "comune": "Napoli",
        "lat": 40.0, "lon": 14.0,
    })
    assert response.status_code == 404


def test_invalid_manual_position_and_stale_address_do_not_mutate(routing_env):
    client, db, owner, *_ = routing_env
    customer = new_customer(db, owner)
    payload = {"customer_id": customer.id, "action": "manual", "original_address": "Via Test 1",
               "original_comune": "Napoli", "address": "Via Corretta 2", "comune": "Napoli",
               "lat": 92.0, "lon": 14.0}
    assert client.post("/api/customers/resolve-selected-address", json=payload).status_code == 422
    payload.update(lat=40.8, original_address="Indirizzo superato")
    assert client.post("/api/customers/resolve-selected-address", json=payload).status_code == 409
    db.refresh(customer)
    assert customer.indirizzo == "Via Test 1"
    assert customer.stato_geocodifica == "da_verificare"


def test_provider_failure_aborts_remaining_selected_customer_checks(routing_env, monkeypatch):
    from app.routers import customers
    from app.services.geocoding import GeocodingUnavailable
    client, db, owner, *_ = routing_env
    a = new_customer(db, owner, "Primo")
    b = new_customer(db, owner, "Secondo")
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(True)
        raise GeocodingUnavailable("Servizio temporaneamente non disponibile")
    monkeypatch.setattr(customers, "geocode_address", unavailable)
    response = client.post("/api/customers/verify-selected",
                           json={"customer_ids": [a.id, b.id]})
    assert response.status_code == 200
    assert response.json()["aborted"] is True
    assert len(response.json()["issues"]) == 2
    assert len(calls) == 1
