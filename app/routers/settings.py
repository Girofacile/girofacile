from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(user: User = Depends(current_user)):
    return {
        "delivery_signature_enabled": bool(getattr(user, "delivery_signature_enabled", False)),
    }


@router.put("")
def update_settings(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.delivery_signature_enabled = bool(payload.get("delivery_signature_enabled", False))
    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "delivery_signature_enabled": bool(user.delivery_signature_enabled),
    }
