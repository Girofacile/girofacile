"""Private, resumable selections for each company operator."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..core.dependencies import current_user
from ..schemas.order_planning import SelectionChange, SelectionSnapshot
from ..services import order_planning as service
from .orders import actor_key

router = APIRouter(prefix='/api/order-planning', tags=['order-planning'])


@router.get('/selection')
def get_selection(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.selection_response(db, service.selection(db, user.id, actor_key(request,user)))


@router.put('/selection')
def change_selection(data: SelectionChange, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        row = service.change_selection(db,user.id,actor_key(request,user),data)
        db.commit()
        return service.selection_response(db,row)
    except Exception:
        db.rollback(); raise


@router.put('/snapshot')
def save_snapshot(data: SelectionSnapshot, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        row = service.snapshot(db,user.id,actor_key(request,user),data)
        db.commit()
        return service.selection_response(db,row)
    except Exception:
        db.rollback(); raise


@router.post('/preview')
def prepare_preview(data: SelectionSnapshot, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        row, warnings = service.preview(db,user,actor_key(request,user),data)
        db.commit()
        return service.selection_response(db,row) | {'warnings':warnings}
    except Exception:
        db.rollback(); raise
