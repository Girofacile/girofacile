"""Giri in bozza: planning left before scheduling, private to each company operator."""
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..core.dependencies import current_user
from ..schemas import DeliveryIn
from ..schemas.order_planning import MAX_SELECTION, PlanningConfiguration
from ..services import planning_drafts as service
from .orders import actor_key

router = APIRouter(prefix='/api/planning-drafts', tags=['planning-drafts'])


class DraftCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: Literal['orders', 'customers']
    selection_version: int = Field(default=0, ge=0)
    configuration: PlanningConfiguration | None = None
    stops: list[DeliveryIn] | None = Field(default=None, max_length=MAX_SELECTION)


class DraftResume(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selection_version: int = Field(default=0, ge=0)


@router.get('')
def list_drafts(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.list_drafts(db, user.id, actor_key(request, user))


@router.post('', status_code=201)
def create_draft(data: DraftCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        row = service.create(db, user.id, actor_key(request, user), data)
        db.commit()
        return service.summary(row)
    except Exception:
        db.rollback(); raise


@router.post('/{draft_id}/resume')
def resume_draft(draft_id: int, data: DraftResume, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        result = service.resume(db, user.id, actor_key(request, user), draft_id, data)
        db.commit()
        return result
    except Exception:
        db.rollback(); raise


@router.delete('/{draft_id}')
def delete_draft(draft_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        service.delete(db, user.id, actor_key(request, user), draft_id)
        db.commit()
        return {'ok': True}
    except Exception:
        db.rollback(); raise
