"""Reset links stay bound to one current identity and credential generation."""
import pytest
from fastapi import HTTPException
from test_agents_feature import env


@pytest.fixture
def reset_accounts(env, monkeypatch):
    from app.core.security import hash_password
    from app.models import CompanyCollaborator, Driver, DriverAccount
    from app.services import email
    _, db, owner, other, _, _, _, agent, *_ = env
    monkeypatch.setattr(email, "send_password_reset", lambda *args, **kwargs: True)
    monkeypatch.setattr(email, "send_password_changed_notice", lambda *args, **kwargs: True)
    old_hash = hash_password("Orbit!River47Cedar#")
    owner.email, owner.password_hash = "owner@example.test", old_hash
    other.email, other.password_hash = "other@example.test", old_hash
    agent.password_hash = old_hash
    driver = Driver(user_id=owner.id, nome="Audit")
    db.add(driver)
    db.flush()
    driver_account = DriverAccount(driver_id=driver.id, email="driver@example.test",
                                   password_hash=old_hash, is_active=True)
    collaborator = CompanyCollaborator(user_id=owner.id, full_name="Audit Operator",
        email="collaborator@example.test", password_hash=old_hash,
        permissions_json="[]", is_active=True)
    db.add_all([driver_account, collaborator])
    db.commit()
    return db, {"user": owner, "driver": driver_account, "agent": agent,
                "collaborator": collaborator}, other


@pytest.mark.parametrize("role", ["user", "driver", "agent", "collaborator"])
def test_successful_reset_consumes_sibling_links_and_revokes_old_sessions(reset_accounts, role):
    from app.core.security import make_account_token, verify_password
    from app.routers.auth import _create_reset_token, confirm_password_reset, get_password_reset_info
    from app.services.sessions import credential, read_session
    db, accounts, other = reset_accounts
    account = accounts[role]
    old_session = make_account_token(role, account.id, credential(account))
    first = _create_reset_token(db, role, account.id, account.email)
    second = _create_reset_token(db, role, account.id, account.email)
    unrelated = _create_reset_token(db, "user", other.id, other.email)
    db.commit()
    assert first is not None and second is not None and unrelated is not None
    assert get_password_reset_info(first.token, db)["ok"]
    assert get_password_reset_info(second.token, db)["ok"]
    assert confirm_password_reset({"token": second.token, "password": "Silver&Falcon93Maple!"}, db)["ok"]
    for item in (first, second, unrelated):
        db.refresh(item)
    assert first.used_at is not None and second.used_at is not None
    assert unrelated.used_at is None
    assert verify_password("Silver&Falcon93Maple!", account.password_hash)
    assert read_session(old_session, role, db) is None
    with pytest.raises(HTTPException):
        get_password_reset_info(first.token, db)
    with pytest.raises(HTTPException):
        confirm_password_reset({"token": first.token, "password": "Copper!Tiger82Birch&"}, db)
    assert verify_password("Silver&Falcon93Maple!", account.password_hash)


@pytest.mark.parametrize("role", ["user", "driver", "agent", "collaborator"])
def test_old_recipient_cannot_read_or_consume_reset_after_email_change(reset_accounts, role):
    from app.routers.auth import _create_reset_token, confirm_password_reset, get_password_reset_info
    db, accounts, _ = reset_accounts
    account = accounts[role]
    reset = _create_reset_token(db, role, account.id, account.email)
    db.commit()
    old_hash = account.password_hash
    account.email = role + "-changed@example.test"
    db.commit()
    with pytest.raises(HTTPException):
        get_password_reset_info(reset.token, db)
    with pytest.raises(HTTPException):
        confirm_password_reset({"token": reset.token, "password": "Silver&Falcon93Maple!"}, db)
    assert account.password_hash == old_hash


def test_owner_email_edit_consumes_all_outstanding_owner_reset_links(reset_accounts):
    from app.routers.auth import _create_reset_token, get_password_reset_info, update_account_profile
    db, accounts, _ = reset_accounts
    owner = accounts["user"]
    resets = [_create_reset_token(db, "user", owner.id, owner.email) for _ in range(2)]
    db.commit()
    assert update_account_profile({"username": owner.username, "email": "owner-changed@example.test"}, owner, db)["ok"]
    for reset in resets:
        db.refresh(reset)
        assert reset.used_at is not None
        with pytest.raises(HTTPException):
            get_password_reset_info(reset.token, db)
