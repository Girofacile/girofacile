from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, SuperAdminCollaborator
from .config import APP_USER, SUPERADMIN_USERNAME
from .security import verify_token, verify_superadmin_token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = verify_token(request.cookies.get("session"))
    if not user_id:
        raise HTTPException(status_code=401, detail="Non autenticato")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Sessione non valida")
    return user


def is_admin_user(user: User | None) -> bool:
    if not user:
        return False
    return (user.username or "").strip().lower() == (APP_USER or "admin").strip().lower()


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Accesso riservato all'amministratore")
    return user


def owned(query, model, user: User):
    """Filtra query per user_id dell'utente corrente.

    Se il modello supporta il soft delete, esclude automaticamente i record
    archiviati. Questo evita che dati eliminati logicamente compaiano nelle
    liste operative, mantenendo però lo storico collegato a giri/report.
    """
    query = query.filter(model.user_id == user.id)
    deleted_at = getattr(model, "deleted_at", None)
    if deleted_at is not None:
        query = query.filter(deleted_at.is_(None))
    return query


# -----------------------------------------------------------------------
# Super Admin SaaS
# -----------------------------------------------------------------------
def current_superadmin(request: Request, db: Session = Depends(get_db)) -> dict:
    username = verify_superadmin_token(request.cookies.get("superadmin_session"))
    if not username:
        raise HTTPException(status_code=401, detail="Accesso Super Admin richiesto")
    if str(username).startswith("collab:"):
        try:
            collaborator_id = int(str(username).split(":", 1)[1])
        except Exception:
            raise HTTPException(status_code=401, detail="Sessione collaboratore non valida")
        collaborator = db.get(SuperAdminCollaborator, collaborator_id)
        if not collaborator or not collaborator.is_active:
            raise HTTPException(status_code=401, detail="Collaboratore non attivo")
        import json
        try:
            permissions = json.loads(collaborator.permissions_json or "{}")
        except Exception:
            permissions = {}
        return {
            "username": collaborator.email,
            "display_name": collaborator.full_name,
            "role": "collaborator",
            "collaborator_id": collaborator.id,
            "permissions": permissions,
        }
    if username.strip().lower() != (SUPERADMIN_USERNAME or "admin").strip().lower():
        raise HTTPException(status_code=401, detail="Sessione Super Admin non valida")
    return {"username": username, "role": "superadmin", "permissions": {"all": True}}


def require_superadmin(superadmin: dict = Depends(current_superadmin)) -> dict:
    return superadmin
