"""ERP assistance requests use real support tickets on an isolated database."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def erp_support(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from app.core.dependencies import require_superadmin
    from app.core.security import make_account_token, make_token
    from app.database import Base, get_db
    from app.models import CompanyCollaborator, User
    from app.routers import admin_support, support
    from app.services.sessions import credential

    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="erp-owner", email="login@example.test", company_email="office@example.test",
                     company_name="Azienda esempio", company_phone="021234567", password_hash="test",
                     plan="starter", plan_status="active")
        other = User(username="erp-other", email="other@example.test", password_hash="test", plan_status="active")
        db.add_all([owner, other]); db.flush()
        actor = CompanyCollaborator(user_id=owner.id, full_name="Collaboratore", email="actor@example.test",
                                    password_hash="test", permissions_json="[]")
        db.add(actor); db.commit()
        app = FastAPI()
        app.include_router(support.router)
        app.include_router(admin_support.router)
        app.dependency_overrides[get_db] = lambda: db
        # Admin list reads are local to this test and never send a notification.
        app.dependency_overrides[require_superadmin] = lambda: {"permissions": {"all": True}}
        with TestClient(app) as client:
            def login(user=owner):
                client.cookies.set("session", make_token(user.id, user.password_hash))

            def login_actor(grants):
                actor.permissions_json = json.dumps(grants); db.commit()
                client.cookies.set("session", make_account_token("collaborator", actor.id, credential(actor)))

            login()
            yield client, db, owner, other, login, login_actor
    engine.dispose()


def test_erp_request_is_company_ticket_visible_to_admin_and_history(erp_support):
    from app.models import SupportTicket
    client, db, owner, other, login, _ = erp_support
    response = client.post("/api/support/erp-connection", json={
        "software": "  Gestionale esempio  ", "version": "  2026.1  ",
        "message": "  Vorrei ricevere automaticamente gli ordini delle consegne.  ",
        "phone": "  061234567  ", "notify_on_resolution": False,
    })
    assert response.status_code == 200, response.text
    ticket = response.json()["ticket"]
    assert response.json()["ok"] is True
    assert ticket["tipo"] == "collegamento_gestionale"
    assert ticket["email"] == owner.company_email
    assert ticket["oggetto"] == "Collegamento gestionale — Gestionale esempio"
    assert ticket["status"] == "aperto" and ticket["notify_on_resolution"] is False
    assert "Versione: 2026.1" in ticket["messaggio"]
    assert "Azienda: Azienda esempio" in ticket["messaggio"]
    assert "Telefono per il ricontatto: 061234567" in ticket["messaggio"]
    assert "Vorrei ricevere automaticamente gli ordini delle consegne." in ticket["messaggio"]
    stored = db.query(SupportTicket).one()
    assert stored.user_id == owner.id and stored.system_error_id is None
    assert client.get("/api/support/tickets").json()[0]["id"] == ticket["id"]
    admin_ticket = client.get("/api/admin/tickets?tipo=collegamento_gestionale").json()[0]
    assert admin_ticket["id"] == ticket["id"] and admin_ticket["company_name"] == owner.company_name
    login(other)
    assert client.get("/api/support/tickets").json() == []


def test_erp_request_uses_profile_contact_and_is_available_on_starter(erp_support):
    client, _, owner, _, _, _ = erp_support
    response = client.post("/api/support/erp-connection", json={"software": "ERP", "message": "Vorrei informazioni."})
    assert response.status_code == 200, response.text
    ticket = response.json()["ticket"]
    assert ticket["email"] == owner.company_email
    assert f"Telefono per il ricontatto: {owner.company_phone}" in ticket["messaggio"]


@pytest.mark.parametrize("invalid", [
    {"software": " "}, {"software": "x" * 161}, {"message": "\n "},
    {"message": "x" * 3001}, {"version": "x" * 161}, {"phone": "x" * 101},
    {"user_id": 123}, {"email": "forged@example.test"},
])
def test_erp_request_rejects_invalid_and_spoofed_data_atomically(erp_support, invalid):
    from app.models import SupportTicket
    client, db, *_ = erp_support
    response = client.post("/api/support/erp-connection", json={"software": "ERP", "message": "Collegamento ordini", **invalid})
    assert response.status_code == 422, response.text
    assert db.query(SupportTicket).count() == 0


def test_erp_request_requires_login_and_support_write_permission(erp_support):
    from app.models import SupportTicket
    client, db, owner, _, _, login_actor = erp_support
    payload = {"software": "ERP", "message": "Collegamento ordini"}
    client.cookies.clear()
    assert client.post("/api/support/erp-connection", json=payload).status_code == 401
    login_actor(["orders.integrations", "support.read"])
    assert client.post("/api/support/erp-connection", json=payload).status_code == 403
    assert db.query(SupportTicket).count() == 0
    login_actor(["support.write", "support.read"])
    response = client.post("/api/support/erp-connection", json=payload)
    assert response.status_code == 200, response.text
    assert db.query(SupportTicket).one().user_id == owner.id
    assert response.json()["ticket"]["email"] == owner.company_email


def test_missing_contact_does_not_create_or_activate_connection(erp_support):
    from app.models import SupportTicket
    client, db, owner, *_ = erp_support
    owner.company_email = None; owner.email = None; db.commit()
    response = client.post("/api/support/erp-connection", json={"software": "ERP", "message": "Collegamento ordini"})
    assert response.status_code == 400 and "email" in response.json()["detail"]
    assert db.query(SupportTicket).count() == 0
