"""Notifiche interne Dashboard amministratore.

Le notifiche sono pensate per dare all'amministratore una vista rapida degli
avvenimenti operativi più importanti senza dover aprire ogni sezione.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..services.agents_feature import agents_enabled
from ..models import (
    Agent,
    ChatMessage,
    Customer,
    Delivery,
    DeliveryStatus,
    Driver,
    Notification,
    RoutePlan,
    User,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _driver_name(driver: Driver | None) -> str:
    if not driver:
        return "Autista"
    return f"{driver.nome or ''} {driver.cognome or ''}".strip() or "Autista"


def _agent_name(agent: Agent | None) -> str:
    if not agent:
        return "Agente"
    return f"{agent.nome or ''} {agent.cognome or ''}".strip() or "Agente"


def _notif_payload(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "action_tab": n.action_tab,
        "action_label": n.action_label,
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


def _ensure_notification(
    db: Session,
    user_id: int,
    entity_key: str,
    type_: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    action_tab: str | None = None,
    action_label: str | None = None,
    created_at: datetime | None = None,
):
    key = f"u{user_id}:{entity_key}"
    exists = db.query(Notification).filter(Notification.entity_key == key).first()
    if exists:
        return exists
    n = Notification(
        user_id=user_id,
        entity_key=key,
        type=type_,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        action_tab=action_tab,
        action_label=action_label,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(n)
    return n


def sync_operational_notifications(db: Session, user: User) -> None:
    """Genera notifiche operative mancanti partendo dai dati reali.

    Non invia email e non crea notifiche duplicate: ogni evento ha una chiave
    stabile. Questa prima versione copre eventi ad alto valore operativo:
    chat autisti, clienti creati da agenti, giri avviati/completati e consegne
    mancate.
    """
    user_id = user.id
    since = datetime.utcnow() - timedelta(days=14)

    # Chat libere o collegate a giri: notifica se ci sono messaggi autista non letti.
    unread_driver_msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.sender_type == "driver", ChatMessage.read_at.is_(None))
        .order_by(ChatMessage.created_at.desc())
        .limit(200)
        .all()
    )
    seen_drivers: set[int] = set()
    for msg in unread_driver_msgs:
        driver = db.get(Driver, msg.driver_id) if msg.driver_id else None
        if not driver or driver.user_id != user_id or driver.id in seen_drivers:
            continue
        seen_drivers.add(driver.id)
        count = (
            db.query(ChatMessage)
            .filter(ChatMessage.driver_id == driver.id, ChatMessage.sender_type == "driver", ChatMessage.read_at.is_(None))
            .count()
        )
        _ensure_notification(
            db,
            user_id,
            f"chat_driver_unread:{driver.id}:{count}",
            "chat",
            "Nuovo messaggio autista",
            f"{_driver_name(driver)} ha {count} messagg{'io' if count == 1 else 'i'} non lett{'o' if count == 1 else 'i'}.",
            "driver",
            driver.id,
            "chat-autisti",
            "Apri chat",
            msg.created_at,
        )

    # Clienti creati/associati ad agenti.
    agent_customers = (
        db.query(Customer)
        .filter(Customer.user_id == user_id, Customer.agent_id.isnot(None), Customer.deleted_at.is_(None))
        .order_by(Customer.id.desc())
        .limit(50)
        .all()
    )
    for customer in agent_customers if agents_enabled(user) else []:
        agent = db.get(Agent, customer.agent_id) if customer.agent_id else None
        _ensure_notification(
            db,
            user_id,
            f"agent_customer:{customer.id}",
            "agent_customer",
            "Nuovo cliente da agente",
            f"{_agent_name(agent)} ha inserito o associato il cliente {customer.nome}.",
            "customer",
            customer.id,
            "clienti",
            "Vai ai clienti",
        )

    # Giri avviati e completati di recente.
    recent_routes = (
        db.query(RoutePlan)
        .filter(RoutePlan.user_id == user_id)
        .filter((RoutePlan.started_at.isnot(None)) | (RoutePlan.completed_at.isnot(None)))
        .order_by(RoutePlan.id.desc())
        .limit(80)
        .all()
    )
    for route in recent_routes:
        if route.started_at and route.started_at >= since:
            _ensure_notification(
                db,
                user_id,
                f"route_started:{route.id}",
                "route_started",
                "Giro avviato",
                f"Il giro {route.nome} è stato avviato dall'autista.",
                "route",
                route.id,
                "dashboard-in-progress",
                "Apri controllo",
                route.started_at,
            )
        if route.completed_at and route.completed_at >= since:
            _ensure_notification(
                db,
                user_id,
                f"route_completed:{route.id}",
                "route_completed",
                "Giro completato",
                f"Il giro {route.nome} è stato completato. I dati finali sono disponibili nei report.",
                "route",
                route.id,
                "storico",
                "Vedi storico",
                route.completed_at,
            )

    # Consegne mancate recenti.
    missed = (
        db.query(DeliveryStatus)
        .filter(DeliveryStatus.status == "mancata")
        .order_by(DeliveryStatus.id.desc())
        .limit(100)
        .all()
    )
    for ds in missed:
        route = db.get(RoutePlan, ds.route_plan_id)
        if not route or route.user_id != user_id:
            continue
        if ds.completata_il and ds.completata_il < since:
            continue
        delivery = db.get(Delivery, ds.delivery_id)
        name = delivery.cliente_nome if delivery else "una consegna"
        reason = f" Motivo: {ds.motivo_mancata}." if ds.motivo_mancata else ""
        _ensure_notification(
            db,
            user_id,
            f"delivery_missed:{ds.id}",
            "delivery_missed",
            "Consegna mancata",
            f"{name} risulta mancata nel giro {route.nome}.{reason}",
            "delivery_status",
            ds.id,
            "dashboard-in-progress",
            "Controlla giro",
            ds.completata_il or datetime.utcnow(),
        )

    db.commit()


@router.get("")
def list_notifications(
    limit: int = 20,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    sync_operational_notifications(db, user)
    q = db.query(Notification).filter(Notification.user_id == user.id)
    if not agents_enabled(user):
        q = q.filter(Notification.type != "agent_customer")
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.is_read.asc(), Notification.created_at.desc()).limit(max(1, min(limit, 100))).all()
    unread = q.filter(Notification.is_read.is_(False)).count()
    return {"unread": unread, "items": [_notif_payload(n) for n in rows]}


@router.get("/count")
def notification_count(db: Session = Depends(get_db), user: User = Depends(current_user)):
    sync_operational_notifications(db, user)
    q = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False))
    if not agents_enabled(user):
        q = q.filter(Notification.type != "agent_customer")
    unread = q.count()
    return {"unread": unread}


@router.post("/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notifica non trovata")
    n.is_read = True
    n.read_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).all()
    now = datetime.utcnow()
    for n in rows:
        n.is_read = True
        n.read_at = now
    db.commit()
    return {"ok": True, "updated": len(rows)}
