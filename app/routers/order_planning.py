"""Private, resumable selections for each company operator."""
from datetime import date
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..core.dependencies import current_user
from ..schemas.order_planning import SelectionChange, SelectionSnapshot, SelectionVerify, SelectionAddressResolution, AppendOrders
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


@router.get('/available')
def available_orders(data_giro: date, deposit_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..models import Deposit
    from .routes import _require_owned_entity
    deposit = _require_owned_entity(db, Deposit, user, deposit_id, 'Deposito') if deposit_id else None
    depot = {'lat': deposit.lat, 'lon': deposit.lon} if deposit and deposit.lat is not None and deposit.lon is not None else None
    return {'orders': service.available(db, user.id, data_giro, depot)}


@router.post('/stops')
def append_orders(data: AppendOrders, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        result, row = service.append_stops(db, user, actor_key(request, user), data)
        db.commit()
        return result | ({'selection': service.selection_response(db, row)} if row is not None else {})
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
