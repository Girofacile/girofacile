"""Credential-bound, expiring sessions and persistent logout revocation."""
from datetime import datetime, timedelta
from hashlib import sha256

from ..core.security import read_account_token, verify_superadmin_token
from ..models import User, Driver, DriverAccount, Agent, AgentAccount, RevokedSession, CompanyCollaborator


def active_identity(account, db):
    if isinstance(account, CompanyCollaborator):
        return bool(account.is_active and not account.password_setup_required and db.get(User, account.user_id))
    if isinstance(account, User):
        return True
    if not account or not account.is_active:
        return False
    if isinstance(account, DriverAccount):
        person = db.get(Driver, account.driver_id)
    else:
        person = db.get(Agent, account.agent_id)
    return bool(person and person.is_active and person.deleted_at is None)


def revoked(raw, db):
    return bool(raw and db.get(RevokedSession, sha256(raw.encode()).hexdigest()))


def credential(account):
    if isinstance(account, CompanyCollaborator):
        return f"{account.password_hash}:{account.session_version}"
    return account.password_hash


def read_session(raw, role, db):
    data = read_account_token(raw, role)
    if not data or revoked(raw, db):
        return None
    model = {'user': User, 'driver': DriverAccount, 'agent': AgentAccount, 'collaborator': CompanyCollaborator}[role]
    account = db.get(model, data['id'])
    if not account or not active_identity(account, db):
        return None
    return account if read_account_token(raw, role, credential(account)) else None


def logout_sessions(request, response, db, names=('session', 'driver_session', 'agent_session')):
    from ..core.http_security import COOKIE_DOMAIN
    for name in names:
        raw = request.cookies.get(name)
        role = {'session': 'user', 'driver_session': 'driver', 'agent_session': 'agent'}.get(name)
        valid = read_account_token(raw, role) if role else verify_superadmin_token(raw)
        if name == 'session' and not valid:
            valid = read_account_token(raw, 'collaborator')
        if raw and len(raw) < 4096 and valid:
            digest = sha256(raw.encode()).hexdigest()
            if not db.get(RevokedSession, digest):
                db.add(RevokedSession(token_hash=digest, expires_at=datetime.utcnow() + timedelta(days=31)))
        response.delete_cookie(name, path='/', domain=COOKIE_DOMAIN)
    db.query(RevokedSession).filter(RevokedSession.expires_at < datetime.utcnow()).delete()
    db.commit()
