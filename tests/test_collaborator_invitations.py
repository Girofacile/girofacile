"""Collaborator self-service invitation regressions; all delivery uses a fake mailbox."""
import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from test_company_collaborators import company


STRONG_PASSWORD = "Silver&Falcon93Maple!"
NEW_COLLABORATOR = {
    "full_name": "Noemi Sarti",
    "email": "cedarworker@example.test",
    "permissions": ["customers.read"],
}


@pytest.fixture
def mailbox(company, monkeypatch):
    messages = []

    def deliver(to_email, full_name, company_name, setup_url):
        messages.append({
            "to_email": to_email, "full_name": full_name,
            "company_name": company_name, "setup_url": setup_url,
        })
        return True

    monkeypatch.setattr("app.services.email.send_collaborator_invitation", deliver)
    return messages


def _token(mailbox, index=-1):
    url = urlsplit(mailbox[index]["setup_url"])
    assert url.path == "/collaborator/setup"
    assert not url.query, "Bearer tokens must stay out of query strings and access logs"
    return parse_qs(url.fragment)["token"][0]


def _create(company, mailbox, **changes):
    client, db, owner, _, _, _, _, login_owner, _ = company
    login_owner()
    result = client.post("/api/collaborators", json=dict(NEW_COLLABORATOR, **changes))
    assert result.status_code == 200, result.text
    from app.models import CompanyCollaborator
    actor = db.get(CompanyCollaborator, result.json()["id"])
    return result, actor, _token(mailbox)


def _accept(client, token, password=STRONG_PASSWORD, **changes):
    return client.post("/api/collaborator-invitations/accept", json={
        "token": token, "password": password, "confirm_password": password, **changes,
    })


def test_creation_emails_single_use_hashed_link_without_an_owner_password(company, mailbox):
    from app.models import CollaboratorInvitation
    from app.core.security import verify_password
    client, db, owner, *_ = company
    result, actor, token = _create(company, mailbox)
    assert len(mailbox) == 1
    assert mailbox[0]["to_email"] == actor.email
    assert mailbox[0]["full_name"] == actor.full_name
    assert mailbox[0]["company_name"] == owner.company_name
    public = result.json()
    assert public["password_setup_required"] is True
    assert public["invitation_status"] == "pending"
    assert public["invitation_sent"] is True
    assert actor.is_active is True and actor.last_login is None
    assert not verify_password(STRONG_PASSWORD, actor.password_hash)
    invitation = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one()
    assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token != invitation.token_hash and len(token) >= 32
    assert invitation.email == actor.email
    assert datetime.utcnow() + timedelta(days=6, hours=23) < invitation.expires_at
    assert invitation.expires_at <= datetime.utcnow() + timedelta(days=7, minutes=1)
    assert invitation.sent_at is not None and invitation.used_at is None
    listing = client.get("/api/collaborators")
    assert listing.status_code == 200
    for response in (result.text, listing.text):
        assert token not in response and actor.password_hash not in response
        assert "setup_url" not in response and "token_hash" not in response


def test_owner_cannot_choose_or_replace_collaborator_password(company, mailbox):
    client, _, _, _, existing, _, _, login_owner, _ = company
    login_owner()
    payload = dict(NEW_COLLABORATOR, password=STRONG_PASSWORD)
    assert client.post("/api/collaborators", json=payload).status_code == 422
    before = existing.password_hash
    payload.update(full_name=existing.full_name, email=existing.email)
    assert client.put(f"/api/collaborators/{existing.id}", json=payload).status_code == 422
    assert existing.password_hash == before
    assert mailbox == []


def test_info_does_not_consume_invitation_and_acceptance_enables_only_that_identity(company, mailbox):
    from app.core.security import verify_password
    from app.models import CollaboratorInvitation
    client, db, owner, _, _, _, _, _, _ = company
    _, actor, token = _create(company, mailbox)
    old_owner_hash = owner.password_hash
    permissions = actor.permissions_json
    client.cookies.clear()
    for _ in range(2):
        info = client.post("/api/collaborator-invitations/info", json={"token": token})
        assert info.status_code == 200, info.text
        assert info.json()["email"] == actor.email
        assert info.json()["full_name"] == actor.full_name
        assert info.json()["company_name"] == owner.company_name
        assert actor.full_name in info.json()["password_context"]
        assert actor.email in info.json()["password_context"]
        assert owner.company_name in info.json()["password_context"]
        assert token not in info.text and actor.password_hash not in info.text
    result = _accept(client, token)
    assert result.status_code == 200, result.text
    assert result.json()["ok"] is True
    assert "session" not in client.cookies, "Choosing a password must not authenticate the owner or collaborator"
    db.refresh(actor)
    assert actor.password_setup_required is False and actor.is_active is True
    assert verify_password(STRONG_PASSWORD, actor.password_hash)
    assert owner.password_hash == old_owner_hash
    assert actor.permissions_json == permissions
    assert db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one().used_at is not None
    assert client.get("/api/me").json()["authenticated"] is False
    result = client.post("/api/login", json={"username": actor.email, "password": STRONG_PASSWORD})
    assert result.status_code == 200, result.text
    assert result.json()["is_collaborator"] is True
    assert result.json()["is_admin"] is False
    assert client.get("/api/customers").status_code == 200
    assert client.get("/api/collaborators").status_code == 403
    assert client.get("/api/billing/overview").status_code == 403
    assert client.put("/api/settings", json={}).status_code == 403


@pytest.mark.parametrize("password", [
    "password1", "Noemi&Parade92!", "Cedarworker&Parade92!",
    "Demo&Parade92!", " Silver&Falcon93Maple!",
])
def test_acceptance_enforces_same_password_policy_including_company_context(company, mailbox, password):
    from app.models import CollaboratorInvitation
    client, db, *_ = company
    _, actor, token = _create(company, mailbox)
    initial_hash = actor.password_hash
    result = _accept(client, token, password)
    assert result.status_code == 422, result.text
    db.refresh(actor)
    assert actor.password_setup_required is True and actor.password_hash == initial_hash
    assert db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one().used_at is None
    assert _accept(client, token).status_code == 200


def test_confirmation_mismatch_does_not_consume_invitation(company, mailbox):
    client, *_ = company
    _, _, token = _create(company, mailbox)
    assert _accept(client, token, confirm_password="Orbit!River47Cedar#").status_code == 422
    assert _accept(client, token).status_code == 200


def test_pending_identity_cannot_login_use_a_session_or_reset_its_password(company, mailbox):
    from app.models import PasswordResetToken
    from app.core.security import make_account_token
    from app.services.sessions import credential
    from app.routers.auth import _create_reset_token, _find_reset_accounts
    client, db, *_ = company
    _, actor, token = _create(company, mailbox)
    assert client.post("/api/login", json={"username": actor.email, "password": STRONG_PASSWORD}).status_code in (401, 403)
    client.cookies.clear()
    client.cookies.set("session", make_account_token("collaborator", actor.id, credential(actor)))
    assert client.get("/api/me").json()["authenticated"] is False
    assert client.get("/api/collaborator/account").status_code == 401
    assert _find_reset_accounts(actor.email, db) == []
    before = db.query(PasswordResetToken).count()
    result = client.post("/api/password-reset/request", json={"email": actor.email})
    assert result.status_code == 200
    assert db.query(PasswordResetToken).count() == before
    # A pre-existing or manually inserted reset token cannot bypass setup.
    reset = _create_reset_token(db, "collaborator", actor.id, actor.email)
    db.commit()
    assert client.post("/api/password-reset/confirm", json={
        "token": reset.token, "password": STRONG_PASSWORD,
    }).status_code == 404
    db.refresh(actor)
    assert actor.password_setup_required is True
    assert _accept(client, token).status_code == 200


def test_tampered_expired_used_and_unknown_links_have_uniform_error(company, mailbox):
    from app.models import CollaboratorInvitation
    client, db, *_ = company
    _, actor, token = _create(company, mailbox)
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    info_bad = client.post("/api/collaborator-invitations/info", json={"token": bad})
    accept_bad = _accept(client, bad)
    assert info_bad.status_code == accept_bad.status_code == 400
    assert info_bad.json()["detail"] == accept_bad.json()["detail"]
    assert _accept(client, "x" * len(token)).json()["detail"] == accept_bad.json()["detail"]
    row = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/collaborator-invitations/info", json={"token": token}).json()["detail"] == accept_bad.json()["detail"]
    assert _accept(client, token).status_code == 400
    db.refresh(actor)
    assert actor.password_setup_required is True
    row.expires_at = datetime.utcnow() + timedelta(hours=1)
    db.commit()
    assert _accept(client, token).status_code == 200
    accepted_hash = actor.password_hash
    assert client.post("/api/collaborator-invitations/info", json={"token": token}).status_code == 400
    assert _accept(client, token, "Orbit!River47Cedar#").status_code == 400
    db.refresh(actor)
    assert actor.password_hash == accepted_hash


def test_resend_revokes_old_link_and_preserves_permissions(company, mailbox):
    from app.models import CollaboratorInvitation
    client, db, _, _, _, _, _, login_owner, _ = company
    _, actor, old_token = _create(company, mailbox)
    initial_permissions = actor.permissions_json
    login_owner()
    result = client.post(f"/api/collaborators/{actor.id}/invite")
    assert result.status_code == 200, result.text
    assert result.json()["invitation_sent"] is True
    new_token = _token(mailbox)
    assert new_token != old_token and len(mailbox) == 2
    assert actor.permissions_json == initial_permissions
    assert db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id, used_at=None).count() == 1
    assert _accept(client, old_token).status_code == 400
    assert _accept(client, new_token).status_code == 200
    assert client.post(f"/api/collaborators/{actor.id}/invite").status_code == 409
    assert len(mailbox) == 2


def test_pending_email_change_sends_to_new_address_and_revokes_old_invitation(company, mailbox):
    client, db, _, _, _, _, _, login_owner, _ = company
    _, actor, old_token = _create(company, mailbox)
    login_owner()
    result = client.put(f"/api/collaborators/{actor.id}", json={
        **NEW_COLLABORATOR, "email": "newcedarworker@example.test",
    })
    assert result.status_code == 200, result.text
    assert result.json()["invitation_sent"] is True
    assert len(mailbox) == 2 and mailbox[-1]["to_email"] == "newcedarworker@example.test"
    db.refresh(actor)
    assert actor.email == "newcedarworker@example.test"
    assert actor.password_setup_required is True
    assert _accept(client, old_token).status_code == 400
    assert _accept(client, _token(mailbox)).status_code == 200


def test_disabling_pending_account_revokes_link_and_reenable_requires_new_invitation(company, mailbox):
    client, db, _, _, _, _, _, login_owner, _ = company
    _, actor, token = _create(company, mailbox)
    login_owner()
    data = dict(NEW_COLLABORATOR, is_active=False)
    result = client.put(f"/api/collaborators/{actor.id}", json=data)
    assert result.status_code == 200, result.text
    assert result.json()["invitation_status"] == "disabled"
    assert _accept(client, token).status_code == 400
    assert client.post(f"/api/collaborators/{actor.id}/invite").status_code == 403
    data["is_active"] = True
    result = client.put(f"/api/collaborators/{actor.id}", json=data)
    assert result.status_code == 200, result.text
    assert _accept(client, token).status_code == 400
    assert actor.password_setup_required is True
    assert result.json()["invitation_sent"] is True
    assert len(mailbox) == 2
    assert _token(mailbox) != token
    assert _accept(client, _token(mailbox)).status_code == 200
    db.refresh(actor)
    assert actor.is_active is True and actor.password_setup_required is False


@pytest.mark.parametrize("failure", ["false", "exception"])
def test_email_failure_is_visible_preserves_pending_account_and_retry_recovers(company, mailbox, monkeypatch, failure):
    client, db, _, _, _, _, _, login_owner, _ = company

    def fail(*args, **kwargs):
        if failure == "exception":
            raise RuntimeError("Synthetic SMTP outage; never use a real server")
        return False

    monkeypatch.setattr("app.services.email.send_collaborator_invitation", fail)
    login_owner()
    result = client.post("/api/collaborators", json=NEW_COLLABORATOR)
    assert result.status_code == 200, result.text
    public = result.json()
    assert public["invitation_sent"] is False and public["invitation_status"] == "failed"
    assert public["message"]
    from app.models import CompanyCollaborator
    actor = db.get(CompanyCollaborator, public["id"])
    assert actor is not None and actor.password_setup_required is True
    pending = next(item for item in client.get("/api/collaborators").json() if item["id"] == actor.id)
    assert pending["invitation_status"] == "failed"
    assert client.post("/api/collaborators", json=NEW_COLLABORATOR).status_code == 409
    assert db.query(CompanyCollaborator).filter_by(email=NEW_COLLABORATOR["email"]).count() == 1

    def recover(to_email, full_name, company_name, setup_url):
        mailbox.append(dict(to_email=to_email, full_name=full_name,
                            company_name=company_name, setup_url=setup_url))
        return True

    monkeypatch.setattr("app.services.email.send_collaborator_invitation", recover)
    retried = client.post(f"/api/collaborators/{actor.id}/invite")
    assert retried.status_code == 200, retried.text
    assert retried.json()["invitation_sent"] is True
    assert retried.json()["invitation_status"] == "pending"
    assert _accept(client, _token(mailbox)).status_code == 200


def test_invitation_actions_are_owner_only_and_tenant_scoped(company, mailbox):
    from app.models import CompanyCollaborator
    client, db, _, other, _, _, _, login_owner, login_actor = company
    _, actor, token = _create(company, mailbox)
    foreign = CompanyCollaborator(user_id=other.id, full_name="Foreign Invited",
                                  email="foreign-invited@example.test", password_hash="!",
                                  password_setup_required=True)
    db.add(foreign)
    db.commit()
    login_owner()
    assert client.post(f"/api/collaborators/{foreign.id}/invite").status_code == 404
    assert client.put(f"/api/collaborators/{foreign.id}", json=NEW_COLLABORATOR).status_code == 404
    login_actor()
    assert client.post(f"/api/collaborators/{actor.id}/invite").status_code == 403
    client.cookies.clear()
    assert client.post(f"/api/collaborators/{actor.id}/invite").status_code == 401
    assert len(mailbox) == 1
    assert _accept(client, token).status_code == 200
    db.refresh(foreign)
    assert foreign.password_setup_required is True and foreign.password_hash == "!"


def test_existing_accounts_stay_initialized_and_cannot_be_reinvited(company, mailbox):
    client, _, _, _, actor, _, _, login_owner, _ = company
    assert actor.password_setup_required is False
    assert client.post("/api/login", json={"username": actor.email, "password": "Orbit!River47Cedar#"}).status_code == 200
    login_owner()
    assert client.post(f"/api/collaborators/{actor.id}/invite").status_code == 409
    public = next(item for item in client.get("/api/collaborators").json() if item["id"] == actor.id)
    assert public["password_setup_required"] is False
    assert public["invitation_status"] == "not_required"
    assert mailbox == []


def test_editing_permissions_does_not_resend_or_extend_pending_invitation(company, mailbox):
    from app.models import CollaboratorInvitation
    client, db, _, _, _, _, _, login_owner, _ = company
    _, actor, token = _create(company, mailbox)
    row = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one()
    expires = row.expires_at
    login_owner()
    result = client.put(f"/api/collaborators/{actor.id}", json={
        **NEW_COLLABORATOR, "permissions": ["customers.read", "customers.create"],
    })
    assert result.status_code == 200, result.text
    assert len(mailbox) == 1 and row.expires_at == expires
    assert "customers.create" in json.loads(actor.permissions_json)
    assert _accept(client, token).status_code == 200


def test_expired_invitation_is_reported_and_can_be_renewed(company, mailbox):
    from app.models import CollaboratorInvitation
    client, db, _, _, _, _, _, login_owner, _ = company
    _, actor, token = _create(company, mailbox)
    row = db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    login_owner()
    public = next(item for item in client.get("/api/collaborators").json() if item["id"] == actor.id)
    assert public["invitation_status"] == "expired"
    assert _accept(client, token).status_code == 400
    result = client.post(f"/api/collaborators/{actor.id}/invite")
    assert result.status_code == 200 and result.json()["invitation_sent"] is True
    assert _accept(client, _token(mailbox)).status_code == 200


def test_unaccepted_disabled_creation_does_not_send_mail(company, mailbox):
    client, db, _, _, _, _, _, login_owner, _ = company
    login_owner()
    result = client.post("/api/collaborators", json=dict(NEW_COLLABORATOR, is_active=False))
    assert result.status_code == 200, result.text
    assert result.json()["password_setup_required"] is True
    assert result.json()["invitation_status"] == "disabled"
    assert mailbox == []


def test_email_change_of_initialized_account_requires_new_address_to_set_password(company, mailbox):
    from app.core.security import verify_password
    from app.models import PasswordResetToken
    from app.routers.auth import _create_reset_token
    client, db, owner, _, actor, _, _, login_owner, login_actor = company
    login_actor()
    previous_session = client.cookies.get("session")
    previous_hash = actor.password_hash
    previous_owner_hash = owner.password_hash
    reset = _create_reset_token(db, "collaborator", actor.id, actor.email)
    db.commit()
    login_owner()
    result = client.put(f"/api/collaborators/{actor.id}", json={
        "full_name": actor.full_name, "email": "differentoperator@example.test",
        "permissions": [],
    })
    assert result.status_code == 200, result.text
    assert result.json()["password_setup_required"] is True
    assert result.json()["invitation_sent"] is True
    assert mailbox[-1]["to_email"] == "differentoperator@example.test"
    db.refresh(actor)
    assert actor.password_hash == previous_hash and owner.password_hash == previous_owner_hash
    assert reset.used_at is not None
    client.cookies.clear()
    client.cookies.set("session", previous_session)
    assert client.get("/api/me").json()["authenticated"] is False
    client.cookies.clear()
    assert client.post("/api/login", json={
        "username": actor.email, "password": "Orbit!River47Cedar#",
    }).status_code in (401, 403)
    assert client.post("/api/password-reset/confirm", json={
        "token": reset.token, "password": STRONG_PASSWORD,
    }).status_code in (400, 404)
    assert _accept(client, _token(mailbox)).status_code == 200
    db.refresh(actor)
    assert not verify_password("Orbit!River47Cedar#", actor.password_hash)
    assert verify_password(STRONG_PASSWORD, actor.password_hash)
    assert client.post("/api/login", json={
        "username": actor.email, "password": STRONG_PASSWORD,
    }).status_code == 200


def test_invitation_payload_validation_does_not_send_or_create_accounts(company, mailbox):
    from app.models import CompanyCollaborator
    client, db, *_ = company
    _, actor, token = _create(company, mailbox)
    before = db.query(CompanyCollaborator).count()
    for payload in ({"token": token, "email": "injected@example.test"},
                    {"token": 42}, {"token": token, "permissions": ["all"]}):
        assert client.post("/api/collaborator-invitations/info", json=payload).status_code == 422
    for payload in ({"token": token, "password": STRONG_PASSWORD, "confirm_password": STRONG_PASSWORD, "is_admin": True},
                    {"token": token, "password": 42, "confirm_password": 42}):
        assert client.post("/api/collaborator-invitations/accept", json=payload).status_code == 422
    assert db.query(CompanyCollaborator).count() == before and len(mailbox) == 1
    assert actor.password_setup_required is True
    assert _accept(client, token).status_code == 200


def test_database_default_keeps_raw_legacy_accounts_initialized(company):
    """A SQL insert without the new flag must remain usable on the SQLite compatibility DB."""
    from sqlalchemy import text
    from app.core.security import hash_password
    from app.models import CompanyCollaborator
    client, db, owner, *_ = company
    db.execute(text("""
        INSERT INTO company_collaborators (
          user_id, full_name, email, password_hash, permissions_json,
          session_version, is_active, created_at
        ) VALUES (
          :owner_id, 'Raw Legacy', 'raw-legacy@example.test', :password_hash, '[]',
          0, 1, CURRENT_TIMESTAMP
        )
    """), {"owner_id": owner.id, "password_hash": hash_password(STRONG_PASSWORD)})
    db.commit()
    legacy = db.query(CompanyCollaborator).filter_by(email="raw-legacy@example.test").one()
    assert legacy.password_setup_required is False
    result = client.post("/api/login", json={
        "username": legacy.email, "password": STRONG_PASSWORD,
    })
    assert result.status_code == 200, result.text
    assert result.json()["is_collaborator"] is True
