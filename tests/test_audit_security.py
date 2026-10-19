from datetime import datetime
from app.core.clock import utc_now
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from test_agents_feature import env


@pytest.mark.parametrize('collaborator', [False, True])
def test_admin_relogin_in_same_second_has_new_session(env, monkeypatch, collaborator):
    import app.core.security as security
    from app.services.sessions import logout_sessions, revoked
    _, db, *_ = env
    monkeypatch.setattr(security.time, 'time', lambda: 1000)
    issue = (lambda: security.make_superadmin_collaborator_token(1)) if collaborator else (lambda: security.make_superadmin_token('admin'))
    old, new = issue(), issue()
    assert old != new
    assert security.verify_superadmin_token(old) == security.verify_superadmin_token(new)
    req = Request({'type': 'http', 'headers': [(b'cookie', f'superadmin_session={old}'.encode())]})
    logout_sessions(req, Response(), db, ('superadmin_session',))
    assert revoked(old, db) and not revoked(new, db)


@pytest.mark.parametrize('role', ['user', 'agent', 'driver'])
def test_session_expiry_password_binding_and_logout(env, monkeypatch, role):
    from app.core.security import make_account_token
    from app.services.sessions import read_session, logout_sessions
    from app.models import Driver, DriverAccount
    _, db, owner, _, _, _, _, agent, *_ = env
    driver = Driver(user_id=owner.id, nome='Audit')
    db.add(driver); db.flush()
    da = DriverAccount(driver_id=driver.id, email='audit@example.test', password_hash='old')
    db.add(da); db.commit()
    account = {'user': owner, 'agent': agent, 'driver': da}[role]
    import app.core.security as security
    monkeypatch.setattr(security.time, 'time', lambda: 1000)
    raw = make_account_token(role, account.id, account.password_hash)
    assert read_session(raw, role, db).id == account.id
    account.password_hash = 'changed'; db.commit()
    assert read_session(raw, role, db) is None
    raw = make_account_token(role, account.id, account.password_hash)
    monkeypatch.setattr(security.time, 'time', lambda: 1000 + 31*86400)
    assert read_session(raw, role, db) is None
    monkeypatch.setattr(security.time, 'time', lambda: 1000)
    name = 'session' if role == 'user' else role + '_session'
    req = Request({'type': 'http', 'headers': [(b'cookie', f'{name}={raw}'.encode())]})
    logout_sessions(req, Response(), db, (name,))
    assert read_session(raw, role, db) is None


@pytest.mark.parametrize('role', ['driver', 'agent'])
def test_reset_never_reactivates_archived_identity(env, role):
    from app.models import Driver, DriverAccount
    from app.routers.auth import _find_reset_accounts, _create_reset_token, confirm_password_reset
    _, db, owner, _, seller, _, _, agent, *_ = env
    driver = Driver(user_id=owner.id, nome='Audit')
    db.add(driver); db.flush()
    da = DriverAccount(driver_id=driver.id, email='audit@example.test', password_hash='old')
    db.add(da); db.commit()
    person, account = (driver, da) if role == 'driver' else (seller, agent)
    token = _create_reset_token(db, role, account.id, account.email)
    person.deleted_at = utc_now()
    person.is_active = False
    account.is_active = False
    db.commit()
    assert (role, account) not in _find_reset_accounts(account.email, db)
    with pytest.raises(HTTPException):
        confirm_password_reset({'token': token.token, 'password': 'Audit-password-2026'}, db)
    assert not account.is_active


def test_setting_secret_values_masked_but_ordinary_values_preserved():
    from app.routers.admin_database import _mask_db_value
    row = {'key': 'openai_api_key', 'value': 'synthetic-secret'}
    assert _mask_db_value('value', row['value'], 'saas_platform_settings', row) != row['value']
    row = {'key': 'trial_days', 'value': '14'}
    assert _mask_db_value('value', row['value'], 'saas_platform_settings', row) == '14'


def test_platform_permission_does_not_grant_service_keys(env):
    from app.routers.admin_profile import admin_platform_settings, admin_update_platform_settings
    _, db, *_ = env
    collaborator = {'role': 'collaborator', 'permissions': {'manage_platform': True}}
    result = admin_platform_settings(db, collaborator)
    assert 'openai_api_key' not in result and 'stripe_secret_key' not in result
    with pytest.raises(HTTPException) as error:
        admin_update_platform_settings({'openai_api_key': 'fake'}, db, collaborator)
    assert error.value.status_code == 403


@pytest.mark.parametrize("enabled", [True, False])
def test_platform_settings_requires_maintenance_permission_before_any_write(env, enabled):
    from app.models import SaaSPlatformSetting
    from app.routers.admin_profile import admin_update_platform_settings
    _, db, *_ = env
    restricted = {"role": "collaborator", "permissions": {"manage_platform": True}}
    with pytest.raises(HTTPException) as error:
        admin_update_platform_settings({"platform_name": "Must not persist", "maintenance_mode": enabled}, db, restricted)
    assert error.value.status_code == 403
    assert db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key.in_(["platform_name", "maintenance_mode"])).count() == 0
    permitted = {"role": "collaborator", "permissions": {"manage_platform": True, "toggle_maintenance": True}}
    result = admin_update_platform_settings({"maintenance_mode": enabled}, db, permitted)
    assert result["maintenance_mode"] == ("true" if enabled else "false")


def test_superadmin_reinvite_invalidates_existing_cookie(env, monkeypatch):
    from app.core.dependencies import current_superadmin
    from app.core.security import make_superadmin_collaborator_token
    from app.models import SuperAdminCollaborator
    from app.routers import admin_profile, auth
    from app.services.sessions import read_superadmin_session
    _, db, *_ = env
    actor = SuperAdminCollaborator(full_name="Audit Operator", email="sa-audit@example.test",
                                  password_hash="old-hash", permissions_json='{"view_revenue":true}')
    db.add(actor)
    db.commit()
    old = make_superadmin_collaborator_token(actor.id, actor.password_hash)
    request = Request({"type": "http", "headers": [(b"cookie", f"superadmin_session={old}".encode())]})
    assert current_superadmin(request, db)["collaborator_id"] == actor.id
    assert auth.superadmin_me(request, db)["authenticated"] is True
    monkeypatch.setattr(admin_profile, "send_superadmin_collaborator_invitation", lambda *args: True)
    admin_profile.admin_resend_collaborator(actor.id, db, {"role": "superadmin", "permissions": {"all": True}})
    assert read_superadmin_session(old, db) is None
    assert auth.superadmin_me(request, db)["authenticated"] is False
    with pytest.raises(HTTPException) as error:
        current_superadmin(request, db)
    assert error.value.status_code == 401
    fresh = make_superadmin_collaborator_token(actor.id, actor.password_hash)
    assert read_superadmin_session(fresh, db) == f"collab:{actor.id}"


def test_superadmin_owner_password_rotation_and_legacy_cookie_fail_closed(env, monkeypatch):
    import base64
    import app.core.security as security
    from app.core import config
    from app.services.sessions import read_superadmin_session
    _, db, *_ = env
    username = config.SUPERADMIN_USERNAME
    monkeypatch.setattr(config, "SUPERADMIN_PASSWORD", "synthetic-before")
    old = security.make_superadmin_token(username, config.SUPERADMIN_PASSWORD)
    assert read_superadmin_session(old, db) == username
    monkeypatch.setattr(config, "SUPERADMIN_PASSWORD", "synthetic-after")
    assert read_superadmin_session(old, db) is None
    fresh = security.make_superadmin_token(username, config.SUPERADMIN_PASSWORD)
    assert read_superadmin_session(fresh, db) == username
    legacy_body = base64.urlsafe_b64encode(f"superadmin:{username}:{int(security.time.time())}:old-nonce".encode()).decode()
    legacy = f"{legacy_body}.{security._sign(legacy_body)}"
    assert security.verify_superadmin_token(legacy) == username
    assert read_superadmin_session(legacy, db) is None


def test_superadmin_login_issues_only_the_credential_it_verified(env, monkeypatch):
    from app.core.security import hash_password
    from app.models import SuperAdminCollaborator
    from app.routers import auth
    _, db, *_ = env
    before = hash_password("Orbit!River47Cedar#")
    account = SuperAdminCollaborator(full_name="Audit Login", email="sa-login@example.test",
                                     password_hash=before, permissions_json="{}")
    db.add(account)
    db.commit()
    captured = []
    monkeypatch.setattr(auth, "make_superadmin_collaborator_token",
                        lambda identity, credential: captured.append(credential) or "test-cookie")
    commit = db.commit
    def rotate_after_login_commit():
        commit()
        account.password_hash = hash_password("Silver&Falcon93Maple!")
        commit()
    monkeypatch.setattr(db, "commit", rotate_after_login_commit)
    auth.superadmin_login({"email": account.email, "password": "Orbit!River47Cedar#"}, Response(), db)
    assert captured == [before]
    assert account.password_hash != before
