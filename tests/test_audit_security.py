from datetime import datetime
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
    person.deleted_at = datetime.utcnow()
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
