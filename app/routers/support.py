from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..models import SupportTicket, SystemErrorLog, User
from ..services.ai_assistant import ensure_company_ai_allowed, run_ai_text
import json

router = APIRouter(prefix="/api/support", tags=["support"])


class SupportTicketIn(BaseModel):
    oggetto: str = Field(default="Richiesta assistenza", max_length=250)
    messaggio: str = Field(default="", max_length=5000)
    notify_on_resolution: bool = True
    system_error_id: int | None = None
    tipo: str = Field(default="supporto", max_length=80)


def support_ticket_to_dict(t: SupportTicket) -> dict:
    return {
        "id": t.id,
        "tipo": t.tipo,
        "email": t.email,
        "oggetto": t.oggetto or "",
        "messaggio": t.messaggio or "",
        "status": t.status,
        "notify_on_resolution": bool(getattr(t, "notify_on_resolution", True)),
        "system_error_id": getattr(t, "system_error_id", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }



class AssistTicketTextIn(BaseModel):
    system_error_id: int


@router.post("/tickets/assist-text")
def support_ticket_assist_text(
    payload: AssistTicketTextIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Genera testo assistito solo per ticket collegati a un errore reale.

Non compare e non funziona per ticket manuali, perché senza errore collegato
non esiste contesto tecnico sufficiente.
"""
    ensure_company_ai_allowed(user, db)
    linked_error = db.get(SystemErrorLog, payload.system_error_id)
    if not linked_error or linked_error.user_id != user.id:
        raise HTTPException(404, "Errore sistema non trovato per questo account")
    context = {
        "company_name": user.company_name or user.username,
        "sector": user.company_sector or user.company_activity_type or "",
        "error": {
            "id": linked_error.id,
            "action": linked_error.action or "",
            "path": linked_error.path or "",
            "error_type": linked_error.error_type or "",
            "error_message": linked_error.error_message or "",
            "created_at": linked_error.created_at.isoformat() if linked_error.created_at else None,
        },
    }
    prompt = """Genera una descrizione breve e chiara per aprire un ticket assistenza GiroFacile.
Il testo deve essere scritto dal punto di vista dell'utente azienda.
Non inserire soluzioni tecniche, non inventare dati, non promettere tempistiche.
Massimo 5 righe.
"""
    result = run_ai_text(
        db, task="support_ticket_text", user_id=user.id,
        system_prompt="Sei l'assistente AI di GiroFacile. Aiuti l'utente a descrivere un problema tecnico già collegato a un errore sistema.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )
    return {"subject": f"Problema tecnico collegato all'errore #{linked_error.id}", "message": result.get("text", ""), **result}

@router.post("/tickets")
def create_support_ticket(
    payload: SupportTicketIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Crea un ticket utente e, se indicato, lo collega a un errore sistema.

    L'utente può collegare solo errori generati dal proprio account aziendale.
    """
    linked_error = None
    if payload.system_error_id:
        linked_error = db.get(SystemErrorLog, payload.system_error_id)
        if not linked_error or linked_error.user_id != user.id:
            raise HTTPException(404, "Errore sistema non trovato per questo account")

    # Il ticket deve usare l'email aggiornata del Profilo azienda.
    # user.email è l'email/account di login e può restare quella demo originale;
    # user.company_email è invece il campo modificabile nel Profilo azienda.
    email = (user.company_email or user.email or "").strip()
    if not email:
        raise HTTPException(400, "Nel profilo azienda manca un indirizzo email per ricevere aggiornamenti sul ticket")

    subject = (payload.oggetto or "Richiesta assistenza").strip()[:250]
    message = (payload.messaggio or "").strip()
    if not message:
        raise HTTPException(400, "Inserisci una descrizione del problema")

    ticket = SupportTicket(
        user_id=user.id,
        system_error_id=linked_error.id if linked_error else None,
        tipo=(payload.tipo or "supporto")[:80],
        email=email,
        oggetto=subject,
        messaggio=message,
        status="aperto",
        notify_on_resolution=bool(payload.notify_on_resolution),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ticket)

    if linked_error:
        linked_error.status = "in_progress"
        if not linked_error.seen_at:
            linked_error.seen_at = datetime.utcnow()
        note = f"Ticket assistenza collegato: #{ticket.id}"
        existing_note = linked_error.admin_note or ""
        linked_error.admin_note = (existing_note + "\n" + note).strip()[:4000]

    db.commit()
    db.refresh(ticket)
    return {"ok": True, "ticket": support_ticket_to_dict(ticket)}


@router.get("/tickets")
def my_support_tickets(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    rows = db.query(SupportTicket).filter(SupportTicket.user_id == user.id).order_by(SupportTicket.created_at.desc()).limit(50).all()
    return [support_ticket_to_dict(t) for t in rows]
