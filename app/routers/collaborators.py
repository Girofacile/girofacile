"""Owner-managed company collaborators and separate self-service identity."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CompanyCollaborator, User, PasswordResetToken
from ..core.dependencies import current_user
from ..core.security import hash_password, verify_password, validate_password_strength
from ..core.http_security import COOKIE_DOMAIN
from ..services.company_permissions import CATALOG, DEPENDENCIES, normalize_permissions, permissions_for
from ..services.identity import ensure_login_email_available
from ..services.sessions import read_session
from ..services.plans import user_plan_info

router = APIRouter(tags=["company-collaborators"])


class CollaboratorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=3, max_length=200)
    permissions: list[str]
    is_active: StrictBool = True
    password: str | None = Field(default=None, max_length=256)


def public_account(actor):
    return {"id": actor.id, "full_name": actor.full_name, "email": actor.email,
            "permissions": sorted(permissions_for(actor)), "is_active": actor.is_active,
            "created_at": actor.created_at, "last_login": actor.last_login}


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
    return {"permissions": CATALOG, "dependencies": {key: sorted(value) for key, value in DEPENDENCIES.items()}}


@router.get("/api/collaborators")
def listing(owner: User = Depends(current_user), db: Session = Depends(get_db)):
    return [public_account(item) for item in db.query(CompanyCollaborator).filter_by(user_id=owner.id)
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
    # A company username can itself be an email and takes priority at login.
    if db.query(User).filter(func.lower(User.username) == email).first():
        raise HTTPException(409, "Email già utilizzata per un accesso GiroFacile")
    if actor is None and not data.password:
        raise HTTPException(422, "Imposta una password iniziale")
    password_hash = None
    if data.password:
        try:
            validate_password_strength(data.password, context_values=(name, email, owner.company_name))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        password_hash = hash_password(data.password)
    if actor is None:
        actor = CompanyCollaborator(user_id=owner.id, password_hash=password_hash)
        db.add(actor)
    revoke = actor.id and (actor.email != email or (actor.is_active and not data.is_active))
    if revoke:
        actor.session_version += 1
    actor.full_name, actor.email = name, email
    actor.permissions_json = json.dumps(grants)
    actor.is_active = data.is_active
    if password_hash:
        actor.password_hash = password_hash
    if actor.id and (password_hash or revoke):
        db.query(PasswordResetToken).filter_by(account_type="collaborator", account_id=actor.id, used_at=None).update({"used_at": datetime.utcnow()})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email già utilizzata")
    db.refresh(actor)
    return public_account(actor)


@router.post("/api/collaborators")
def create(data: CollaboratorIn, owner: User = Depends(current_user), db: Session = Depends(get_db)):
    return save(data, owner, db)


@router.put("/api/collaborators/{collaborator_id}")
def update(collaborator_id: int, data: CollaboratorIn, owner: User = Depends(current_user), db: Session = Depends(get_db)):
    actor = db.query(CompanyCollaborator).filter_by(id=collaborator_id, user_id=owner.id).first()
    if not actor:
        raise HTTPException(404, "Collaboratore non trovato")
    return save(data, owner, db, actor)


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
    db.query(PasswordResetToken).filter_by(account_type="collaborator", account_id=actor.id, used_at=None).update({"used_at": datetime.utcnow()})
    db.commit()
    response.delete_cookie("session", path="/", domain=COOKIE_DOMAIN)
    return {"ok": True, "reauthenticate": True, "message": "Password aggiornata. Accedi di nuovo."}
