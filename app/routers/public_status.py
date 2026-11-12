"""Stato pubblico della piattaforma: avvisi e manutenzione, raggiungibile anche durante la manutenzione."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db

router = APIRouter(tags=["public"])


@router.get("/api/public/status")
def platform_status(response: Response, db: Session = Depends(get_db)):
    from ..services.maintenance import public_status
    response.headers["Cache-Control"] = "no-store"
    return public_status(db)
