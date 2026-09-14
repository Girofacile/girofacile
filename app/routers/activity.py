"""Registro attività aziendale.

Questa sezione è diversa dalle notifiche: le notifiche servono ad avvisare
l'amministratore su eventi da leggere, mentre il registro attività è una
cronologia consultabile di quello che è successo nel gestionale.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..models import (
    ActivityEvent,
    Agent,
    ChatMessage,
    Customer,
    Delivery,
    DeliveryStatus,
    Driver,
    RoutePlan,
    User,
)

router = APIRouter(prefix="/api/activity", tags=["activity"])


def _driver_name(driver: Driver | None) -> str:
    if not driver:
        return "Autista"
    return f"{driver.nome or ''} {driver.cognome or ''}".strip() or "Autista"


def _agent_name(agent: Agent | None) -> str:
    if not agent:
        return "Agente"
    return f"{agent.nome or ''} {agent.cognome or ''}".strip() or "Agente"


def _payload(e: ActivityEvent, count: int | None = None, description: str | None = None) -> dict:
    data = {
        "id": e.id,
        "type": e.type,
        "actor_type": e.actor_type,
        "actor_name": e.actor_name,
        "title": e.title,
        "description": description if description is not None else e.description,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "action_tab": e.action_tab,
        "severity": e.severity,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
    if count and count > 1:
        data["count"] = count
    return data


def _compact_activity_rows(rows: list[ActivityEvent]) -> list[dict]:
    """Compatta eventi ripetitivi per rendere il registro più leggibile.

    Gli eventi importanti come giri, consegne mancate e chat restano singoli.
    Gli eventi molto ripetitivi, come clienti inseriti da agente o indirizzi da
    verificare, vengono raggruppati per giorno, attore e severità.
    """
    compact_types = {"customer", "address"}
    groups: dict[tuple, dict] = {}
    output: list[dict] = []

    for row in rows:
        if row.type not in compact_types:
            output.append(_payload(row))
            continue
        day = row.created_at.date().isoformat() if row.created_at else ""
        key = (row.type, row.title, row.actor_name or "", row.severity or "info", row.action_tab or "", day)
        if key not in groups:
            groups[key] = {"row": row, "count": 0, "examples": []}
            output.append(groups[key])
        groups[key]["count"] += 1
        if len(groups[key]["examples"]) < 3 and row.description:
            groups[key]["examples"].append(row.description)

    final: list[dict] = []
    for item in output:
        if isinstance(item, dict) and "row" in item:
            row = item["row"]
            count = item["count"]
            if count > 1:
                examples = " ".join(item["examples"][:2])
                desc = f"{count} eventi simili raggruppati. {examples}".strip()
                final.append(_payload(row, count=count, description=desc))
            else:
                final.append(_payload(row))
        else:
            final.append(item)
    return final


def log_activity(
    db: Session,
    user_id: int,
    entity_key: str,
    type_: str,
    title: str,
    description: str | None = None,
    actor_type: str | None = "system",
    actor_name: str | None = "GiroFacile",
    entity_type: str | None = None,
    entity_id: int | None = None,
    action_tab: str | None = None,
    severity: str = "info",
    created_at: datetime | None = None,
) -> ActivityEvent:
    """Crea un evento solo se non esiste già.

    La entity_key viene resa univoca per azienda così possiamo sincronizzare
    eventi storici senza duplicati.
    """
    key = f"u{user_id}:{entity_key}"
    existing = db.query(ActivityEvent).filter(ActivityEvent.entity_key == key).first()
    if existing:
        return existing
    event = ActivityEvent(
        user_id=user_id,
        entity_key=key,
        type=type_,
        title=title,
        description=description,
        actor_type=actor_type,
        actor_name=actor_name,
        entity_type=entity_type,
        entity_id=entity_id,
        action_tab=action_tab,
        severity=severity,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(event)
    return event


def sync_activity_events(db: Session, user: User) -> None:
    """Genera eventi mancanti partendo dai dati operativi già presenti.

    È una base professionale per l'audit log: da qui in avanti potremo
    aggiungere chiamate dirette a log_activity nelle funzioni di creazione e
    modifica, ma intanto il registro si popola anche sui dati esistenti.
    """
    user_id = user.id
    since = datetime.utcnow() - timedelta(days=60)

    # Configurazione azienda / onboarding.
    if user.company_name or user.company_email or user.company_vat or user.company_address:
        log_activity(
            db, user_id, "company_profile_configured", "company",
            "Profilo azienda configurato",
            "Sono stati inseriti o aggiornati i dati principali dell'azienda.",
            actor_type="admin", actor_name="Amministratore",
            entity_type="company", entity_id=user.id, action_tab="company",
            severity="success", created_at=user.created_at,
        )
    if user.onboarding_completed:
        log_activity(
            db, user_id, "onboarding_completed", "onboarding",
            "Configurazione guidata completata",
            "L'azienda ha completato i passaggi iniziali di configurazione.",
            actor_type="admin", actor_name="Amministratore",
            entity_type="company", entity_id=user.id, action_tab="company",
            severity="success", created_at=user.onboarding_completed_at or datetime.utcnow(),
        )

    # Agenti e autisti creati.
    for agent in db.query(Agent).filter(Agent.user_id == user_id, Agent.deleted_at.is_(None)).order_by(Agent.id.desc()).limit(200).all():
        log_activity(
            db, user_id, f"agent_created:{agent.id}", "agent",
            "Agente creato",
            f"È stato creato il profilo agente {_agent_name(agent)}.",
            actor_type="admin", actor_name="Amministratore",
            entity_type="agent", entity_id=agent.id, action_tab="agenti",
            severity="info", created_at=agent.created_at,
        )

    for driver in db.query(Driver).filter(Driver.user_id == user_id, Driver.deleted_at.is_(None)).order_by(Driver.id.desc()).limit(200).all():
        log_activity(
            db, user_id, f"driver_created:{driver.id}", "driver",
            "Autista creato",
            f"È stato creato il profilo autista {_driver_name(driver)}.",
            actor_type="admin", actor_name="Amministratore",
            entity_type="driver", entity_id=driver.id, action_tab="autisti",
            severity="info", created_at=driver.created_at,
        )

    # Clienti collegati ad agenti.
    for customer in db.query(Customer).filter(Customer.user_id == user_id, Customer.agent_id.isnot(None), Customer.deleted_at.is_(None)).order_by(Customer.id.desc()).limit(250).all():
        agent = db.get(Agent, customer.agent_id) if customer.agent_id else None
        log_activity(
            db, user_id, f"agent_customer:{customer.id}", "customer",
            "Cliente inserito da agente",
            f"{_agent_name(agent)} ha inserito o associato il cliente {customer.nome}.",
            actor_type="agent", actor_name=_agent_name(agent),
            entity_type="customer", entity_id=customer.id, action_tab="clienti",
            severity="success",
        )

    # Clienti con indirizzo da verificare: utile come log operativo.
    for customer in db.query(Customer).filter(Customer.user_id == user_id, Customer.stato_geocodifica != "ok", Customer.deleted_at.is_(None)).order_by(Customer.id.desc()).limit(100).all():
        log_activity(
            db, user_id, f"customer_address_unverified:{customer.id}", "address",
            "Cliente con indirizzo da verificare",
            f"Il cliente {customer.nome} non risulta ancora verificato con Google.",
            actor_type="system", actor_name="GiroFacile",
            entity_type="customer", entity_id=customer.id, action_tab="clienti",
            severity="warning",
        )

    # Giri avviati/completati.
    routes = (
        db.query(RoutePlan)
        .filter(RoutePlan.user_id == user_id)
        .filter((RoutePlan.started_at.isnot(None)) | (RoutePlan.completed_at.isnot(None)))
        .order_by(RoutePlan.id.desc())
        .limit(250)
        .all()
    )
    for route in routes:
        driver = db.get(Driver, route.driver_id) if route.driver_id else None
        if route.started_at and route.started_at >= since:
            log_activity(
                db, user_id, f"route_started:{route.id}", "route",
                "Giro avviato",
                f"Il giro {route.nome} è stato avviato da {_driver_name(driver)}.",
                actor_type="driver", actor_name=_driver_name(driver),
                entity_type="route", entity_id=route.id, action_tab="dashboard-in-progress",
                severity="info", created_at=route.started_at,
            )
        if route.completed_at and route.completed_at >= since:
            log_activity(
                db, user_id, f"route_completed:{route.id}", "route",
                "Giro completato",
                f"Il giro {route.nome} è stato completato. I dati finali sono disponibili nei report.",
                actor_type="driver", actor_name=_driver_name(driver),
                entity_type="route", entity_id=route.id, action_tab="storico",
                severity="success", created_at=route.completed_at,
            )

    # Consegne completate/mancate.
    statuses = db.query(DeliveryStatus).order_by(DeliveryStatus.id.desc()).limit(400).all()
    for status in statuses:
        route = db.get(RoutePlan, status.route_plan_id)
        if not route or route.user_id != user_id:
            continue
        if status.completata_il and status.completata_il < since:
            continue
        delivery = db.get(Delivery, status.delivery_id)
        name = delivery.cliente_nome if delivery else "Consegna"
        if status.status == "completata":
            log_activity(
                db, user_id, f"delivery_completed:{status.id}", "delivery",
                "Consegna completata",
                f"{name} è stata completata nel giro {route.nome}.",
                actor_type="driver", actor_name="Autista",
                entity_type="delivery_status", entity_id=status.id, action_tab="storico",
                severity="success", created_at=status.completata_il or datetime.utcnow(),
            )
        elif status.status == "mancata":
            reason = f" Motivo: {status.motivo_mancata}." if status.motivo_mancata else ""
            log_activity(
                db, user_id, f"delivery_missed:{status.id}", "delivery",
                "Consegna mancata",
                f"{name} risulta mancata nel giro {route.nome}.{reason}",
                actor_type="driver", actor_name="Autista",
                entity_type="delivery_status", entity_id=status.id, action_tab="storico",
                severity="danger", created_at=status.completata_il or datetime.utcnow(),
            )

    # Messaggi chat autista -> admin.
    for msg in (
        db.query(ChatMessage)
        .filter(ChatMessage.sender_type == "driver")
        .order_by(ChatMessage.id.desc())
        .limit(200)
        .all()
    ):
        driver = db.get(Driver, msg.driver_id) if msg.driver_id else None
        if not driver or driver.user_id != user_id:
            continue
        log_activity(
            db, user_id, f"chat_message:{msg.id}", "chat",
            "Messaggio ricevuto da autista",
            f"{_driver_name(driver)} ha scritto: {msg.message[:120]}",
            actor_type="driver", actor_name=_driver_name(driver),
            entity_type="chat", entity_id=msg.id, action_tab="chat-autisti",
            severity="info", created_at=msg.created_at,
        )

    db.commit()


@router.get("")
def list_activity(
    limit: int = 80,
    type: str = "",
    severity: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    sync_activity_events(db, user)
    q = db.query(ActivityEvent).filter(ActivityEvent.user_id == user.id)
    if type:
        q = q.filter(ActivityEvent.type == type)
    if severity:
        q = q.filter(ActivityEvent.severity == severity)
    rows = q.order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc()).limit(max(1, min(limit, 300))).all()
    items = _compact_activity_rows(rows) if not type else [_payload(x) for x in rows]
    return {"items": items[:max(1, min(limit, 300))]}


@router.post("/{event_id}/hide")
def hide_activity_event(event_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    event = db.get(ActivityEvent, event_id)
    if not event or event.user_id != user.id:
        return {"ok": True}
    db.delete(event)
    db.commit()
    return {"ok": True}
