"""Global login email policy, checked before saving or sending invitations."""
from hashlib import sha256
from fastapi import HTTPException
from sqlalchemy import func, text
from ..models import User, Driver, DriverAccount, Agent, AgentAccount, CompanyCollaborator


def ensure_login_email_available(db, email, role, identity_id=None):
    email = (email or '').strip().lower()
    if not email:
        return
    if db.bind.dialect.name == 'postgresql':
        key = int.from_bytes(sha256(email.encode()).digest()[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    for model, kind, identity_column in (
        (User, 'user', User.id), (Driver, 'driver', Driver.id),
        (DriverAccount, 'driver', DriverAccount.driver_id),
        (Agent, 'agent', Agent.id), (AgentAccount, 'agent', AgentAccount.agent_id),
        (CompanyCollaborator, 'collaborator', CompanyCollaborator.id),
    ):
        query = db.query(model).filter(func.lower(model.email) == email)
        if role == kind and identity_id is not None:
            query = query.filter(identity_column != identity_id)
        if query.first():
            raise HTTPException(409, 'Email già associata a un’identità GiroFacile, anche archiviata. Usa un’altra email o contatta l’assistenza per recuperare l’identità esistente.')
