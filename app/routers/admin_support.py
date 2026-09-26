"""Admin support: extracted from the SaaS administration router."""
from datetime import datetime
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.dependencies import require_superadmin
from ..database import get_db
from ..models import SupportTicket, SystemErrorLog, User
from ..services.error_monitor import error_log_to_dict
from ..services.email import send_ticket_resolved
from ..services.ai_assistant import run_ai_text

from .admin_helpers import (
    _require_perm,
    ticket_to_dict,
    user_to_dict,
)

router = APIRouter()


@router.get("/tickets")
def admin_tickets(
    status: str = "",
    tipo: str = "",
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_tickets")
    q = db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    if tipo:
        q = q.filter(SupportTicket.tipo == tipo)
    rows = q.order_by(SupportTicket.created_at.desc()).all()
    return [ticket_to_dict(t, db) for t in rows]


@router.put("/tickets/{ticket_id}")
def admin_update_ticket(ticket_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_tickets")
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")
    valid_statuses = ("aperto", "in_lavorazione", "chiuso")
    new_status = (payload.get("status") or ticket.status or "aperto").strip()
    if new_status not in valid_statuses:
        raise HTTPException(400, "Stato non valido")

    previous_status = ticket.status
    ticket.status = new_status
    ticket.admin_note = payload.get("admin_note", ticket.admin_note)
    ticket.updated_at = datetime.utcnow()

    linked_error = db.get(SystemErrorLog, getattr(ticket, "system_error_id", None)) if getattr(ticket, "system_error_id", None) else None
    if linked_error:
        if new_status == "in_lavorazione":
            linked_error.status = "in_progress"
            if not linked_error.seen_at:
                linked_error.seen_at = datetime.utcnow()
        elif new_status == "chiuso":
            linked_error.status = "resolved"
            linked_error.resolved_at = datetime.utcnow()
            if ticket.admin_note:
                linked_error.admin_note = (linked_error.admin_note or "") + f"\nTicket #{ticket.id} chiuso: {ticket.admin_note}"
                linked_error.admin_note = linked_error.admin_note.strip()[:4000]

    db.commit()
    db.refresh(ticket)

    # Se richiesto, avvisa l'utente quando il ticket viene chiuso.
    if new_status == "chiuso" and previous_status != "chiuso" and getattr(ticket, "notify_on_resolution", True) and not getattr(ticket, "resolved_email_sent", False):
        # Prima di inviare l'avviso di risoluzione, rilegge l'email aggiornata dal Profilo azienda.
        # Questo evita che un ticket usi ancora la vecchia email demo/account se l'azienda
        # ha modificato il campo email dal Profilo azienda.
        linked_user = db.get(User, ticket.user_id) if ticket.user_id else None
        destination_email = ((linked_user.company_email if linked_user else None) or ticket.email or "").strip()
        if destination_email and destination_email != ticket.email:
            ticket.email = destination_email
            db.commit()
            db.refresh(ticket)
        sent = send_ticket_resolved(destination_email, ticket_to_dict(ticket, db)) if destination_email else False
        ticket.resolved_email_sent = bool(sent)
        db.commit()
        db.refresh(ticket)

    return ticket_to_dict(ticket, db)


@router.get("/system-errors")
def admin_system_errors(
    status: str = "",
    severity: str = "",
    limit: int = 100,
    db: Session = Depends(get_db),
    superadmin: dict = Depends(require_superadmin),
):
    _require_perm(superadmin, "view_errors")
    limit = max(1, min(limit, 300))
    q = db.query(SystemErrorLog)
    if status:
        q = q.filter(SystemErrorLog.status == status)
    if severity:
        q = q.filter(SystemErrorLog.severity == severity)
    rows = q.order_by(SystemErrorLog.created_at.desc()).limit(limit).all()
    return [error_log_to_dict(r) for r in rows]


@router.get("/system-errors/summary")
def admin_system_errors_summary(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    new_count = db.query(SystemErrorLog).filter(SystemErrorLog.status == "new").count()
    critical_count = db.query(SystemErrorLog).filter(
        SystemErrorLog.status != "resolved",
        SystemErrorLog.severity == "critical",
    ).count()
    high_count = db.query(SystemErrorLog).filter(
        SystemErrorLog.status != "resolved",
        SystemErrorLog.severity == "high",
    ).count()
    last = db.query(SystemErrorLog).order_by(SystemErrorLog.created_at.desc()).first()
    return {
        "new": new_count,
        "critical_open": critical_count,
        "high_open": high_count,
        "last_error": error_log_to_dict(last) if last else None,
    }


@router.get("/system-errors/{error_id}")
def admin_system_error_detail(error_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    row = db.get(SystemErrorLog, error_id)
    if not row:
        raise HTTPException(404, "Errore non trovato")
    if row.status == "new":
        row.status = "seen"
        row.seen_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return error_log_to_dict(row)


@router.put("/system-errors/{error_id}")
def admin_update_system_error(error_id: int, payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_errors")
    row = db.get(SystemErrorLog, error_id)
    if not row:
        raise HTTPException(404, "Errore non trovato")
    status = payload.get("status")
    if status in ("new", "seen", "in_progress", "resolved", "ignored"):
        row.status = status
        if status in ("seen", "in_progress") and not row.seen_at:
            row.seen_at = datetime.utcnow()
        if status == "resolved":
            row.resolved_at = datetime.utcnow()
    if "admin_note" in payload:
        row.admin_note = (payload.get("admin_note") or "")[:4000]
    if status == "resolved":
        linked_tickets = db.query(SupportTicket).filter(
            SupportTicket.system_error_id == row.id,
            SupportTicket.status != "chiuso",
        ).all()
        for ticket in linked_tickets:
            ticket.status = "chiuso"
            ticket.updated_at = datetime.utcnow()
            if row.admin_note and not ticket.admin_note:
                ticket.admin_note = row.admin_note
            if getattr(ticket, "notify_on_resolution", True) and not getattr(ticket, "resolved_email_sent", False):
                sent = send_ticket_resolved(ticket.email, ticket_to_dict(ticket, db))
                ticket.resolved_email_sent = bool(sent)
    db.commit()
    db.refresh(row)
    return error_log_to_dict(row)


@router.post("/tickets/{ticket_id}/ai-analysis")
def admin_ticket_ai_analysis(ticket_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_tickets")
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket non trovato")
    if not getattr(ticket, "system_error_id", None):
        raise HTTPException(400, "Analisi AI disponibile solo per ticket collegati a un errore sistema")
    err = db.get(SystemErrorLog, ticket.system_error_id)
    linked_user = db.get(User, ticket.user_id) if ticket.user_id else None
    context = {
        "ticket": ticket_to_dict(ticket, db),
        "error": error_log_to_dict(err) if err else None,
        "company": user_to_dict(linked_user, db) if linked_user else None,
        "sector": (linked_user.company_sector if linked_user else "") or (err.company_sector if err else ""),
    }
    prompt = """Analizza questo ticket GiroFacile collegato a errore tecnico.
Produci una risposta breve in italiano con sezioni: Problema rilevato, Possibile causa, Impatto sull'utente, Come risolvere, Risposta suggerita al cliente.
Non inventare dati, usa solo il contesto fornito.
"""
    result = run_ai_text(
        db, task="admin_error_analysis", user_id=ticket.user_id,
        system_prompt="Sei un assistente tecnico interno per il Super Admin SaaS GiroFacile. Scrivi in modo pratico, breve e operativo.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )
    return result


@router.post("/system-errors/{error_id}/ai-analysis")
def admin_error_ai_analysis(error_id: int, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_errors")
    err = db.get(SystemErrorLog, error_id)
    if not err:
        raise HTTPException(404, "Errore non trovato")
    linked_user = db.get(User, err.user_id) if err.user_id else None
    context = {
        "error": error_log_to_dict(err),
        "company": user_to_dict(linked_user, db) if linked_user else None,
        "sector": (linked_user.company_sector if linked_user else "") or err.company_sector or "",
    }
    prompt = """Analizza questo errore tecnico GiroFacile.
Produci una scheda breve in italiano con: Problema rilevato, Possibile causa, Impatto sull'utente, Come risolvere, Risposta suggerita.
Non inventare dati e non promettere soluzioni già completate.
"""
    return run_ai_text(
        db, task="admin_error_analysis", user_id=err.user_id,
        system_prompt="Sei un assistente tecnico interno per il Super Admin SaaS GiroFacile. Scrivi in modo pratico, breve e operativo.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )
