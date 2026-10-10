"""Orders API. Source ingestion and planning are deliberately separate releases."""
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..core.dependencies import current_user
from ..database import get_db
from ..models import User
from ..order_models import Order, OrderSource
from ..schemas.orders import OrderCreate, OrderUpdate, OrderAction, OrderVersion, CustomerResolution
from ..services import orders as service

router = APIRouter(prefix='/api/orders', tags=['orders'])


def actor_key(request, user):
    actor = getattr(request.state, 'company_collaborator', None)
    return f'collaborator:{actor.id}' if actor else f'owner:{user.id}'


@router.get('')
def list_orders(q: str = Query('', max_length=200), status: str | None = None,
                source_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                sort: Literal['received_at', 'requested_date', 'number'] = 'received_at',
                direction: Literal['asc', 'desc'] = 'desc', page: int = Query(1, ge=1, le=1000000),
                page_size: int = Query(25, ge=1, le=100),
                db: Session = Depends(get_db), user: User = Depends(current_user)):
    if status and status not in service.STATUSES:
        raise HTTPException(422, 'Stato ordine non valido')
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'La data iniziale deve precedere la data finale')
    query = db.query(Order).filter(Order.user_id == user.id)
    if q.strip():
        value = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.filter(or_(*(field.ilike(value, escape='\\') for field in
                                  (Order.number, Order.recipient_name, Order.delivery_address))))
    if status: query = query.filter(Order.status == status)
    if source_id is not None: query = query.filter(Order.source_id == source_id)
    if date_from: query = query.filter(Order.requested_date >= date_from)
    if date_to: query = query.filter(Order.requested_date <= date_to)
    total = query.count()
    column = getattr(Order, sort)
    ordered = column.asc() if direction == 'asc' else column.desc()
    rows = query.order_by(ordered.nullslast(), Order.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    sources = {s.id: s.name for s in db.query(OrderSource).filter_by(user_id=user.id)}
    counts = dict(db.query(Order.status, func.count(Order.id)).filter(Order.user_id == user.id).group_by(Order.status).all())
    return {'items': [service.summary(row, sources[row.source_id]) for row in rows],
            'total': total, 'page': page, 'page_size': page_size,
            'metrics': {key: counts.get(key, 0) for key in ('nuovo', 'da_verificare', 'pronto', 'assegnato')},
            'sources': [{'id': key, 'name': value} for key, value in sources.items()]}


@router.post('', status_code=201)
def create_order(data: OrderCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = service.create_order(db, user.id, data, actor_key(request, user))
    db.commit()
    return service.detail(db, order)


@router.get('/{order_id}')
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return service.detail(db, service.get_order(db, user.id, order_id))


@router.put('/{order_id}')
def update_order(order_id: int, data: OrderUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = service.get_order(db, user.id, order_id, lock=True)
    service.update_order(db, order, data, actor_key(request, user))
    db.commit()
    return service.detail(db, order)


@router.post('/{order_id}/status')
def change_status(order_id: int, data: OrderAction, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = service.get_order(db, user.id, order_id, lock=True)
    service.transition(db, order, data, actor_key(request, user))
    db.commit()
    return service.detail(db, order)


@router.post('/{order_id}/verify-address')
def verify_address(order_id: int, data: OrderVersion, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    order = service.get_order(db, user.id, order_id, lock=True)
    service.verify_address(db, order, data.version, actor_key(request, user))
    db.commit()
    return service.detail(db, order)


@router.get('/{order_id}/customers')
def customer_candidates(order_id: int, q: str | None = Query(None, max_length=200), db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.order_customers import recognize, search
    order = service.get_order(db,user.id,order_id)
    return {'kind':'search','candidates':search(db,user.id,q)} if q is not None else recognize(db,order)


@router.post('/{order_id}/customer')
def resolve_customer(order_id: int, data: CustomerResolution,
                     request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.order_customers import resolve
    from ..services.route_orders import lock_company
    from ..services.company_permissions import permissions_for
    actor = getattr(request.state,'company_collaborator',None)
    if data.action == 'create' and actor is not None and 'customers.create' not in permissions_for(actor):
        raise HTTPException(403,'Per creare una nuova anagrafica serve il permesso Crea clienti.')
    try:
        lock_company(db,user.id)
        order = service.get_order(db,user.id,order_id,lock=True)
        resolve(db,user,order,data,actor_key(request,user))
        db.commit()
        return service.detail(db,order)
    except Exception:
        db.rollback(); raise
