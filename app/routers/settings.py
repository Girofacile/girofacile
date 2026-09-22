from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..models import User
from ..services.agents_feature import agents_enabled
from ..services.plans import require_feature
from pydantic import BaseModel, StrictBool

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    delivery_signature_enabled: StrictBool | None = None
    agents_enabled: StrictBool | None = None


@router.get("")
def get_settings(user: User = Depends(current_user)):
    return {
        "delivery_signature_enabled": bool(getattr(user, "delivery_signature_enabled", False)),
        "agents_enabled": agents_enabled(user),
    }


@router.put("")
def update_settings(payload: SettingsUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.agents_enabled is True:
        require_feature(user, "has_agents")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "delivery_signature_enabled": bool(user.delivery_signature_enabled),
        "agents_enabled": agents_enabled(user),
    }
