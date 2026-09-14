from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.dependencies import current_user, owned
from ..database import get_db
from ..models import Deposit, User
from ..schemas import DepositIn
from ..services.plans import check_deposit_limit
from ..services import distance_cache as dc

router = APIRouter(prefix="/api/deposits", tags=["deposits"])


@router.get("")
def list_deposits(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return owned(db.query(Deposit), Deposit, user).order_by(
        Deposit.predefinito.desc(), Deposit.nome.asc()
    ).all()


@router.post("")
def create_deposit(data: DepositIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_deposit_limit(user, db)
    if data.predefinito:
        owned(db.query(Deposit), Deposit, user).update({"predefinito": False})
    item = Deposit(**data.model_dump(), user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{item_id}")
def update_deposit(item_id: int, data: DepositIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Deposit), Deposit, user).filter(Deposit.id == item_id).first()
    if not item:
        raise HTTPException(404, "Deposito non trovato")
    if data.predefinito:
        owned(db.query(Deposit), Deposit, user).filter(Deposit.id != item_id).update({"predefinito": False})
    address_changed = (data.indirizzo or "").strip().lower() != (item.indirizzo or "").strip().lower()
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    if address_changed:
        item.lat = None
        item.lon = None
        dc.invalidate_key(db, dc.deposit_key(item.id, user_id=user.id), user_id=user.id)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_deposit(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Deposit), Deposit, user).filter(Deposit.id == item_id).first()
    if not item:
        raise HTTPException(404, "Deposito non trovato")
    item.is_active = False
    item.deleted_at = datetime.utcnow()
    item.predefinito = False
    db.commit()
    dc.invalidate_key(db, dc.deposit_key(item_id, user_id=user.id), user_id=user.id)
    return {"ok": True, "archived": True}
