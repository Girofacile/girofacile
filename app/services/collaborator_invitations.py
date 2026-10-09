"""Purpose-specific, single-use collaborator invitations; SMTP runs outside locks."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException
from ..core.config import APP_BASE_URL, APP_ENV
from ..core.security import hash_password, validate_password_strength
from ..models import CollaboratorInvitation, CompanyCollaborator, PasswordResetToken, User

INVITATION_TTL = timedelta(days=7)
PRIVATE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
INVALID_INVITATION = "Invito non valido o scaduto. Richiedi un nuovo invito al titolare."


def _invalid():
    return HTTPException(400, INVALID_INVITATION, headers=PRIVATE_HEADERS)


def _digest(token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        raise _invalid()
    return hashlib.sha256(token.encode()).hexdigest()


def _setup_url(token):
    base = APP_BASE_URL.rstrip("/")
    try:
        parsed = urlsplit(base)
        hostname = parsed.hostname
        parsed.port  # Validate malformed or out-of-range configured ports.
    except ValueError:
        raise HTTPException(503, "Configura un URL pubblico valido per gli inviti.")
    if (parsed.scheme not in {"http", "https"} or not hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (APP_ENV in {"production", "prod"} and parsed.scheme != "https")):
        raise HTTPException(503, "Configura un URL pubblico valido per gli inviti.")
    return f"{base}/collaborator/setup#token={token}"


def latest_invitation(db, actor):
    return db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id).order_by(CollaboratorInvitation.id.desc()).populate_existing().first()


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def invitation_fields(actor, invitation=None):
    if not actor.is_active:
        status = "disabled"
    elif not actor.password_setup_required:
        status = "accepted" if invitation else "not_required"
    elif not invitation:
        status = "pending"
    elif not invitation.sent_at and invitation.used_at:
        status = "failed"
    elif invitation.used_at or invitation.expires_at <= datetime.utcnow():
        status = "expired"
    else:
        status = "pending"
    return {
        "password_setup_required": bool(actor.password_setup_required),
        "invitation_status": status,
        "invitation_sent_at": _utc(invitation.sent_at) if invitation else None,
        "invitation_expires_at": _utc(invitation.expires_at) if invitation else None,
    }


def revoke_invitations(db, actor):
    db.query(CollaboratorInvitation).filter_by(collaborator_id=actor.id, used_at=None).update(
        {"used_at": datetime.utcnow()}, synchronize_session=False)


def issue_invitation(db, actor, owner):
    """Commit the digest first, send mail, then acknowledge this attempt only."""
    actor = db.query(CompanyCollaborator).filter_by(id=actor.id, user_id=owner.id).with_for_update().populate_existing().first()
    if not actor:
        raise HTTPException(404, "Collaboratore non trovato")
    if not actor.is_active:
        raise HTTPException(403, "Riattiva il collaboratore prima di inviare un invito")
    if not actor.password_setup_required:
        raise HTTPException(409, "Il collaboratore ha già impostato la password. Può usare Password dimenticata.")
    now = datetime.utcnow()
    previous = latest_invitation(db, actor)
    if (previous and not previous.used_at and not previous.sent_at
            and now - previous.created_at < timedelta(seconds=30)):
        raise HTTPException(409, "Un invio è già in corso. Riprova tra pochi secondi.")
    token = secrets.token_urlsafe(48)
    setup_url = _setup_url(token)
    revoke_invitations(db, actor)
    invitation = CollaboratorInvitation(
        collaborator_id=actor.id, email=actor.email,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        created_at=now, expires_at=now + INVITATION_TTL,
    )
    db.add(invitation)
    db.flush()
    invitation_id = invitation.id
    to_email, full_name = actor.email, actor.full_name
    company_name = owner.company_name or owner.username
    # A delivered email must never point to an uncommitted token. Release the
    # actor lock before the SMTP timeout; later status writes target only this ID.
    db.commit()
    try:
        from .email import send_collaborator_invitation
        sent = bool(send_collaborator_invitation(
            to_email, full_name, company_name, setup_url))
    except Exception:
        # The email helper logs delivery failures without recording bearer URLs.
        sent = False
    query = db.query(CollaboratorInvitation).filter_by(id=invitation_id)
    if sent:
        query.filter_by(used_at=None).update({"sent_at": datetime.utcnow()}, synchronize_session=False)
    else:
        query.filter_by(used_at=None).update({"used_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
    db.refresh(actor)
    current = latest_invitation(db, actor)
    current_attempt = bool(current and current.id == invitation_id
                           and actor.is_active and actor.email == to_email)
    if sent and current_attempt and not actor.password_setup_required:
        return {"invitation_sent": True, "message": "Il collaboratore ha già attivato il proprio accesso."}
    valid_sent = bool(sent and current_attempt and current and not current.used_at)
    if not current_attempt:
        message = "L'invito è stato sostituito o revocato. Controlla lo stato del collaboratore."
    elif valid_sent:
        message = "Invito inviato via email. Il collaboratore sceglierà la propria password."
    else:
        message = "Collaboratore salvato, ma l'email non è stata inviata. Riprova con Invia invito."
    return {"invitation_sent": valid_sent, "message": message}


def _find_invitation(db, token, lock=False):
    digest = _digest(token)
    invitation = db.query(CollaboratorInvitation).filter_by(token_hash=digest).first()
    if not invitation:
        raise _invalid()
    query = db.query(CompanyCollaborator).filter_by(id=invitation.collaborator_id)
    actor = (query.with_for_update().populate_existing().first() if lock else query.first())
    if lock:
        # Every mutation takes the actor lock before token locks, including
        # acceptance, resend, email changes and disabling.
        invitation = db.query(CollaboratorInvitation).filter_by(id=invitation.id).with_for_update().populate_existing().first()
    if (not actor or not actor.is_active or not actor.password_setup_required
            or not db.get(User, actor.user_id) or not invitation or invitation.used_at
            or invitation.expires_at <= datetime.utcnow()
            or invitation.email.lower() != actor.email.lower()):
        raise _invalid()
    return actor, invitation


def invitation_info(db, token):
    actor, invitation = _find_invitation(db, token)
    owner = db.get(User, actor.user_id)
    return {"ok": True, "email": actor.email, "full_name": actor.full_name,
            "company_name": owner.company_name or owner.username,
            "password_context": [actor.full_name, actor.email, owner.company_name or ""],
            "expires_at": _utc(invitation.expires_at)}


def confirm_invitation(db, token, password, confirm_password):
    actor, invitation = _find_invitation(db, token, lock=True)
    if password != confirm_password:
        raise HTTPException(422, "La password e la conferma non coincidono", headers=PRIVATE_HEADERS)
    owner = db.get(User, actor.user_id)
    try:
        validate_password_strength(password, context_values=(actor.full_name, actor.email, owner.company_name))
    except ValueError as exc:
        raise HTTPException(422, str(exc), headers=PRIVATE_HEADERS)
    actor.password_hash = hash_password(password)
    actor.password_setup_required = False
    actor.session_version += 1
    invitation.used_at = datetime.utcnow()
    revoke_invitations(db, actor)
    db.query(PasswordResetToken).filter_by(
        account_type="collaborator", account_id=actor.id, used_at=None).update(
            {"used_at": datetime.utcnow()}, synchronize_session=False)
    db.commit()
    return {"ok": True, "message": "Password impostata. Ora puoi accedere con la tua email.",
            "redirect_url": "/dashboard"}
