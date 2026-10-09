"""Owner-managed company collaborators and separate self-service identity."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CollaboratorInvitation, CompanyCollaborator, User, PasswordResetToken
from ..core.dependencies import current_user
from ..core.security import hash_password, verify_password, validate_password_strength
from ..core.http_security import COOKIE_DOMAIN
from ..services.company_permissions import CATALOG, DEPENDENCIES, normalize_permissions, permissions_for, permission_presets
from ..services.identity import ensure_login_email_available
from ..services.sessions import read_session
from ..services.plans import user_plan_info
from ..services.collaborator_invitations import (PRIVATE_HEADERS, confirm_invitation, invitation_fields,
    invitation_info, issue_invitation, latest_invitation, revoke_invitations)

router = APIRouter(tags=["company-collaborators"])


class CollaboratorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=200)
    permissions: list[str]
    is_active: StrictBool = True


def public_account(actor, invitation=None):
    return {"id": actor.id, "full_name": actor.full_name, "email": actor.email,
            "permissions": sorted(permissions_for(actor)), "is_active": actor.is_active,
            "created_at": actor.created_at, "last_login": actor.last_login,
            **invitation_fields(actor, invitation)}


def collaborator_session(actor, owner):
    return {"ok": True, "authenticated": True, "role": "admin", "is_admin": False,
            "is_collaborator": True, "collaborator_id": actor.id,
            "username": actor.full_name, "email": actor.email,
            "company_name": owner.company_name, "company_logo_url": owner.company_logo_url,
            "company_sector": owner.company_sector, "workspace_operational": True,
            "onboarding_completed": True, "onboarding_dismissed": True,
            "permissions": sorted(permissions_for(actor)), "redirect_url": "/dashboard",
            **user_plan_info(owner)}


def actor_account(request: Request, db: Session = Depends(get_db)):
    actor = read_session(request.cookies.get("session"), "collaborator", db)
    if not actor:
        raise HTTPException(401, "Sessione collaboratore non valida")
    return actor


@router.get("/api/collaborators/permissions")
def catalog(owner: User = Depends(current_user)):
    return {"permissions": CATALOG, "dependencies": {key: sorted(value) for key, value in DEPENDENCIES.items()},
            "presets": permission_presets()}


@router.get("/api/collaborators")
def listing(owner: User = Depends(current_user), db: Session = Depends(get_db)):
    latest = (db.query(CollaboratorInvitation.collaborator_id, func.max(CollaboratorInvitation.id).label("latest_id"))
              .join(CompanyCollaborator, CompanyCollaborator.id == CollaboratorInvitation.collaborator_id)
              .filter(CompanyCollaborator.user_id == owner.id)
              .group_by(CollaboratorInvitation.collaborator_id).subquery())
    invitations = {item.collaborator_id: item for item in
                   db.query(CollaboratorInvitation).join(latest, CollaboratorInvitation.id == latest.c.latest_id).all()}
    return [public_account(item, invitations.get(item.id)) for item in db.query(CompanyCollaborator).filter_by(user_id=owner.id)
            .order_by(CompanyCollaborator.full_name, CompanyCollaborator.id).all()]

def save(data, owner, db, actor=None):
    email = data.email.strip().lower()
    if email.count("@") != 1 or any(char.isspace() for char in email) or not all(email.split("@")):
        raise HTTPException(422, "Inserisci un indirizzo email valido")
    name = data.full_name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Inserisci il nome del collaboratore")
    grants = normalize_permissions(data.permissions)
    ensure_login_email_available(db, email, "collaborator", actor.id if actor else None)
    if db.query(User).filter(func.lower(User.username) == email).first():
        raise HTTPException(409, "Email già utilizzata per un accesso GiroFacile")
    created = actor is None
    email_changed = not created and actor.email != email
    reactivated = not created and not actor.is_active and data.is_active
    revoke = not created and (email_changed or (actor.is_active and not data.is_active))
    if created:
        # This marker cannot be verified as a password. Only the invite recipient
        # can initialize credentials; legacy accounts keep their existing hashes.
        actor = CompanyCollaborator(user_id=owner.id, password_hash="!pending-invite", password_setup_required=True)
        db.add(actor)
    if revoke:
        actor.session_version += 1
        revoke_invitations(db, actor)
        db.query(PasswordResetToken).filter_by(account_type="collaborator", account_id=actor.id, used_at=None).update(
            {"used_at": datetime.utcnow()}, synchronize_session=False)
    if email_changed:
        # A changed login address must be verified by its recipient.
        actor.password_setup_required = True
    actor.full_name, actor.email = name, email
    actor.permissions_json = json.dumps(grants)
    actor.is_active = data.is_active
    send = actor.is_active and actor.password_setup_required and (created or email_changed or reactivated)
    delivery = {}
    try:
        db.flush()
        if send:
            delivery = issue_invitation(db, actor, owner)
        else:
            db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email già utilizzata")
    db.refresh(actor)
    return {**public_account(actor, latest_invitation(db, actor)), **delivery}

@router.post("/api/collaborators")
def create(data: CollaboratorIn, owner: User = Depends(current_user), db: Session = Depends(get_db)):
    return save(data, owner, db)


@router.put("/api/collaborators/{collaborator_id}")
def update(collaborator_id: int, data: CollaboratorIn, owner: User = Depends(current_user), db: Session = Depends(get_db)):
    actor = db.query(CompanyCollaborator).filter_by(id=collaborator_id, user_id=owner.id).with_for_update().populate_existing().first()
    if not actor:
        raise HTTPException(404, "Collaboratore non trovato")
    return save(data, owner, db, actor)


@router.post("/api/collaborators/{collaborator_id}/invite")
def invite(collaborator_id: int, owner: User = Depends(current_user), db: Session = Depends(get_db)):
    actor = db.query(CompanyCollaborator).filter_by(id=collaborator_id, user_id=owner.id).with_for_update().populate_existing().first()
    if not actor:
        raise HTTPException(404, "Collaboratore non trovato")
    delivery = issue_invitation(db, actor, owner)
    return {**public_account(actor, latest_invitation(db, actor)), **delivery}


class InvitationTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: StrictStr = Field(min_length=32, max_length=128)


class InvitationAcceptIn(InvitationTokenIn):
    password: StrictStr = Field(min_length=1, max_length=256)
    confirm_password: StrictStr = Field(min_length=1, max_length=256)


@router.post("/api/collaborator-invitations/info")
def invitation_details(data: InvitationTokenIn, response: Response, db: Session = Depends(get_db)):
    response.headers.update(PRIVATE_HEADERS)
    return invitation_info(db, data.token)


@router.post("/api/collaborator-invitations/accept")
def accept_invitation(data: InvitationAcceptIn, response: Response, db: Session = Depends(get_db)):
    response.headers.update(PRIVATE_HEADERS)
    return confirm_invitation(db, data.token, data.password, data.confirm_password)


@router.get("/api/collaborator/account")
def account(actor=Depends(actor_account)):
    return {"username": actor.full_name, "email": actor.email, "role": "Collaboratore"}


@router.get("/api/collaborator/context")
def context(actor=Depends(actor_account), db: Session = Depends(get_db)):
    owner = db.get(User, actor.user_id)
    return {key: bool(getattr(owner, key, False)) for key in
            ("has_time_windows", "needs_photo_proof", "has_ztl", "needs_tail_lift", "has_refrigerated_goods")}


@router.put("/api/collaborator/account")
def update_account(payload: dict, actor=Depends(actor_account), db: Session = Depends(get_db)):
    if set(payload) - {"username", "email"} or any(not isinstance(value, str) for value in payload.values()):
        raise HTTPException(422, "Campi non consentiti")
    if payload.get("email", actor.email).strip().lower() != actor.email:
        raise HTTPException(403, "Il cambio dell’email di accesso è riservato al titolare")
    name = str(payload.get("username", actor.full_name)).strip()
    if not 2 <= len(name) <= 160:
        raise HTTPException(422, "Nome non valido")
    actor.full_name = name
    db.commit()
    return {"ok": True, "account": account(actor)}


@router.post("/api/collaborator/password")
def password(payload: dict, response: Response, actor=Depends(actor_account), db: Session = Depends(get_db)):
    if any(not isinstance(payload.get(key), str) or len(payload[key]) > 256 for key in ('current_password', 'new_password', 'confirm_password')):
        raise HTTPException(422, "Campi password non validi")
    old, new = payload.get("current_password", ""), payload.get("new_password", "")
    if not verify_password(old, actor.password_hash):
        raise HTTPException(400, "La password attuale non è corretta")
    if new != payload.get("confirm_password") or verify_password(new, actor.password_hash):
        raise HTTPException(400, "Controlla la nuova password e la conferma")
    try:
        validate_password_strength(new, context_values=(actor.full_name, actor.email))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    actor.password_hash = hash_password(new)
    revoke_invitations(db, actor)
    db.query(PasswordResetToken).filter_by(account_type="collaborator", account_id=actor.id, used_at=None).update({"used_at": datetime.utcnow()})
    db.commit()
    response.delete_cookie("session", path="/", domain=COOKIE_DOMAIN)
    return {"ok": True, "reauthenticate": True, "message": "Password aggiornata. Accedi di nuovo."}
