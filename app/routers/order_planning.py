"""Private, resumable selections for each company operator."""
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..core.dependencies import current_user
from ..schemas.order_planning import SelectionChange, SelectionSnapshot, SelectionVerify, SelectionAddressResolution
from ..services import order_planning as service
from .orders import actor_key

router = APIRouter(prefix='/api/order-planning', tags=['order-planning'])


@router.get('/selection')
def get_selection(request: Request, include_stops: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = service.selection(db, user.id, actor_key(request,user))
    result = service.selection_response(db, row)
    if include_stops and row and not result['routes']:
        result['stops'] = service.selection_stops(db, row)
    return result


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


@router.post('/verify-selected')
def verify_selected(data:SelectionVerify,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from ..services import selected_order_addresses
    try:return selected_order_addresses.verify_selected(db,user.id,actor_key(request,user),data)
    except Exception:db.rollback();raise


@router.post('/resolve-address')
def resolve_address(data:SelectionAddressResolution,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from ..services import selected_order_addresses
    from ..services.company_permissions import permissions_for
    collaborator=getattr(request.state,'company_collaborator',None)
    if data.action!='exclude' and collaborator is not None and 'orders.update' not in permissions_for(collaborator):
        raise HTTPException(403,'Il tuo account non può correggere gli indirizzi degli ordini. Puoi escluderli dalla selezione.')
    try:return selected_order_addresses.resolve(db,user.id,actor_key(request,user),data)
    except Exception:db.rollback();raise
