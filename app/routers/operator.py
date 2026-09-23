"""
Router portale operatore.
Accessibile tramite token senza login — /giro/{token}
"""
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..services.delivery_signature import apply_delivery_signature
from ..models import (
    Customer, Delivery, DeliveryStatus, RoutePlan, RouteToken, User
)

router = APIRouter(tags=["operator"])

TEMPO_SCARICO_OPTIONS = [10, 15, 20, 30, 45, 60, 90]
MOTIVI_MANCATA = ["assente", "chiuso", "rifiutato", "altro"]

def update_customer_unload_time(customer: Customer, tempo: int):
    """Aggiorna il tempo scarico stimato usando una media progressiva."""
    try:
        tempo = int(tempo)
    except Exception:
        return
    if tempo <= 0:
        return
    count = int(getattr(customer, "tempo_scarico_rilevazioni", 0) or 0)
    current = int(getattr(customer, "tempo_scarico_min", 10) or 10)
    customer.tempo_scarico_min = int(round(((current * count) + tempo) / (count + 1)))
    customer.tempo_scarico_rilevazioni = count + 1


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def get_route_by_token(token: str, db: Session) -> tuple[RouteToken, RoutePlan]:
    rt = db.query(RouteToken).filter(RouteToken.token == token).first()
    if not rt:
        raise HTTPException(404, "Link non valido o scaduto")
    if rt.expires_at and datetime.utcnow() > rt.expires_at:
        raise HTTPException(410, "Link scaduto")
    plan = db.get(RoutePlan, rt.route_plan_id)
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    return rt, plan


def get_or_create_delivery_status(delivery_id: int, route_plan_id: int, db: Session) -> DeliveryStatus:
    ds = db.query(DeliveryStatus).filter(
        DeliveryStatus.delivery_id == delivery_id,
        DeliveryStatus.route_plan_id == route_plan_id
    ).first()
    if not ds:
        ds = DeliveryStatus(
            delivery_id=delivery_id,
            route_plan_id=route_plan_id,
            status="in_attesa"
        )
        db.add(ds)
        db.commit()
        db.refresh(ds)
    return ds


def delivery_to_operator_dict(delivery: Delivery, status: DeliveryStatus | None) -> dict:
    return {
        "id": delivery.id,
        "ordine": delivery.ordine,
        "customer_id": delivery.customer_id,
        "cliente_nome": delivery.cliente_nome,
        "indirizzo": delivery.indirizzo,
        "peso_kg": delivery.peso_kg,
        "colli": delivery.colli,
        "scarico_mattina_da": time_to_hhmm(delivery.scarico_mattina_da),
        "scarico_mattina_a": time_to_hhmm(delivery.scarico_mattina_a),
        "scarico_pomeriggio_da": time_to_hhmm(delivery.scarico_pomeriggio_da),
        "scarico_pomeriggio_a": time_to_hhmm(delivery.scarico_pomeriggio_a),
        "tempo_scarico_min": delivery.tempo_scarico_min,
        "ztl": delivery.ztl,
        "sponda": delivery.sponda,
        "note": delivery.note,
        "arrivo_stimato": time_to_hhmm(delivery.arrivo_stimato),
        "partenza_stimata": time_to_hhmm(delivery.partenza_stimata),
        "km_tappa": delivery.km_tappa,
        "warning": delivery.warning,
        "status": status.status if status else "in_attesa",
        "motivo_mancata": status.motivo_mancata if status else None,
        "tempo_scarico_effettivo": status.tempo_scarico_effettivo if status else None,
        "note_operatore": status.note_operatore if status else None,
        "completata_il": status.completata_il.isoformat() if status and status.completata_il else None,
    }


# -----------------------------------------------------------------------
# Generazione token (richiede login responsabile)
# -----------------------------------------------------------------------

@router.post("/api/routes/{route_id}/generate-token")
def generate_route_token(
    route_id: int,
    payload: dict = {},
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Genera un token sicuro per il portale operatore e invia email all'autista."""
    from ..services.email import send_route_assignment
    import os

    plan = db.query(RoutePlan).filter(
        RoutePlan.id == route_id,
        RoutePlan.user_id == user.id
    ).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")

    # Invalida eventuali token precedenti
    db.query(RouteToken).filter(RouteToken.route_plan_id == route_id).delete()

    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=3)
    rt = RouteToken(
        route_plan_id=route_id,
        token=token,
        expires_at=expires,
    )
    db.add(rt)
    db.commit()

    # Costruisci URL base
    base_url = payload.get("base_url", "https://app.girofacile.it")
    portal_url = f"{base_url}/giro/{token}"

    # Invia email all'autista se ha email configurata
    email_sent = False
    if plan.driver and plan.driver.email:
        driver_name = ((plan.driver.nome or "") + " " + (plan.driver.cognome or "")).strip()
        email_sent = send_route_assignment(
            to_email=plan.driver.email,
            driver_name=driver_name,
            route_name=plan.nome or "Giro consegne",
            data_giro=date_to_iso(plan.data_giro) or "",
            orario_partenza=time_to_hhmm(plan.orario_partenza) or "",
            deposit_nome=plan.deposit.nome if plan.deposit else "",
            n_consegne=len(plan.deliveries or []),
            km_totali=float(plan.totale_km or 0),
            link_portale=portal_url,
        )

    return {
        "token": token,
        "expires_at": expires.isoformat(),
        "url": f"/giro/{token}",
        "portal_url": portal_url,
        "email_sent": email_sent,
        "driver_email": plan.driver.email if plan.driver else None,
    }


# -----------------------------------------------------------------------
# Portale operatore (pubblico, solo token)
# -----------------------------------------------------------------------

@router.get("/api/operator/{token}")
def get_operator_route(token: str, db: Session = Depends(get_db)):
    """Restituisce i dati del giro per l'operatore."""
    rt, plan = get_route_by_token(token, db)

    # Aggiorna used_at al primo accesso
    if not rt.used_at:
        rt.used_at = datetime.utcnow()
        db.commit()

    deliveries = sorted(plan.deliveries or [], key=lambda x: x.ordine or 0)
    statuses = {
        ds.delivery_id: ds
        for ds in db.query(DeliveryStatus).filter(
            DeliveryStatus.route_plan_id == plan.id
        ).all()
    }

    # Inizializza stati mancanti
    for d in deliveries:
        if d.id not in statuses:
            ds = get_or_create_delivery_status(d.id, plan.id, db)
            statuses[d.id] = ds

    completate = sum(1 for ds in statuses.values() if ds.status == "completata")
    mancate = sum(1 for ds in statuses.values() if ds.status == "mancata")

    # Calcola prossima fermata
    prossima_idx = None
    for i, d in enumerate(deliveries):
        if statuses.get(d.id) and statuses[d.id].status == "in_attesa":
            prossima_idx = i
            break

    return {
        "route": {
            "id": plan.id,
            "nome": plan.nome,
            "data_giro": date_to_iso(plan.data_giro),
            "orario_partenza": time_to_hhmm(plan.orario_partenza),
            "orario_rientro_stimato": time_to_hhmm(plan.orario_rientro_stimato),
            "totale_km": plan.totale_km,
            "totale_minuti": plan.totale_minuti,
            "google_maps_url": plan.google_maps_url,
            "deposit_nome": plan.deposit.nome if plan.deposit else None,
            "deposit_indirizzo": plan.deposit.indirizzo if plan.deposit else None,
            "driver_nome": (
                ((plan.driver.nome or "") + " " + (plan.driver.cognome or "")).strip()
                if plan.driver else None
            ),
            "vehicle_nome": plan.vehicle.nome if plan.vehicle else None,
        },
        "consegne": [delivery_to_operator_dict(d, statuses.get(d.id)) for d in deliveries],
        "progress": {
            "totale": len(deliveries),
            "completate": completate,
            "mancate": mancate,
            "rimanenti": len(deliveries) - completate - mancate,
            "prossima_idx": prossima_idx,
            "percentuale": round((completate + mancate) / len(deliveries) * 100) if deliveries else 0,
        },
        "delivery_signature_enabled": bool(getattr(db.get(User, plan.user_id), "delivery_signature_enabled", False)),
        "tempo_scarico_options": TEMPO_SCARICO_OPTIONS,
        "motivi_mancata": MOTIVI_MANCATA,
    }


@router.post("/api/operator/{token}/delivery/{delivery_id}/complete")
def complete_delivery(
    token: str,
    delivery_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Segna una consegna come completata."""
    rt, plan = get_route_by_token(token, db)

    delivery = db.query(Delivery).filter(
        Delivery.id == delivery_id,
        Delivery.route_plan_id == plan.id
    ).first()
    if not delivery:
        raise HTTPException(404, "Consegna non trovata")

    ds = get_or_create_delivery_status(delivery_id, plan.id, db)
    owner = db.get(User, plan.user_id)
    apply_delivery_signature(ds, payload, owner, required=True)
    ds.status = "completata"
    ds.tempo_scarico_effettivo = payload.get("tempo_scarico")
    ds.note_operatore = payload.get("note") or None
    from ..core.utils import local_now
    ds.completata_il = local_now().replace(tzinfo=None)

    # Aggiorna tempo scarico nel profilo cliente con media progressiva
    tempo = payload.get("tempo_scarico")
    if tempo and delivery.customer_id:
        customer = db.get(Customer, delivery.customer_id)
        if customer:
            update_customer_unload_time(customer, tempo)

    from .driver import refresh_route_completion
    refresh_route_completion(plan.id, db)
    db.commit()
    return {"ok": True, "status": "completata"}


@router.post("/api/operator/{token}/delivery/{delivery_id}/missed")
def missed_delivery(
    token: str,
    delivery_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Segna una consegna come mancata."""
    rt, plan = get_route_by_token(token, db)

    delivery = db.query(Delivery).filter(
        Delivery.id == delivery_id,
        Delivery.route_plan_id == plan.id
    ).first()
    if not delivery:
        raise HTTPException(404, "Consegna non trovata")

    motivo = (payload.get("motivo") or "altro").strip()
    if motivo not in MOTIVI_MANCATA:
        motivo = "altro"

    ds = get_or_create_delivery_status(delivery_id, plan.id, db)
    ds.status = "mancata"
    ds.motivo_mancata = motivo
    ds.note_operatore = payload.get("note") or None
    from ..core.utils import local_now
    ds.completata_il = local_now().replace(tzinfo=None)
    db.commit()
    return {"ok": True, "status": "mancata"}


@router.post("/api/operator/{token}/delivery/{delivery_id}/note")
def add_delivery_note(
    token: str,
    delivery_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Aggiunge una nota a una consegna."""
    rt, plan = get_route_by_token(token, db)
    delivery = db.query(Delivery).filter(
        Delivery.id == delivery_id,
        Delivery.route_plan_id == plan.id
    ).first()
    if not delivery:
        raise HTTPException(404, "Consegna non trovata")

    ds = get_or_create_delivery_status(delivery_id, plan.id, db)
    ds.note_operatore = (payload.get("note") or "").strip() or None
    db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------
# Monitoring (dashboard responsabile)
# -----------------------------------------------------------------------

@router.get("/api/routes/{route_id}/live")
def route_live_status(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Stato in tempo reale del giro per la dashboard."""
    plan = db.query(RoutePlan).filter(
        RoutePlan.id == route_id,
        RoutePlan.user_id == user.id
    ).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")

    deliveries = sorted(plan.deliveries or [], key=lambda x: x.ordine or 0)
    statuses = {
        ds.delivery_id: ds
        for ds in db.query(DeliveryStatus).filter(
            DeliveryStatus.route_plan_id == plan.id
        ).all()
    }

    completate = sum(1 for ds in statuses.values() if ds.status == "completata")
    mancate = sum(1 for ds in statuses.values() if ds.status == "mancata")
    fatte = completate + mancate

    # Stima rientro aggiornata
    minuti_rimasti = None
    if fatte > 0 and len(deliveries) > 0:
        try:
            minuti_per_consegna = float(plan.totale_minuti or 0) / len(deliveries)
            minuti_rimasti = round((len(deliveries) - fatte) * minuti_per_consegna)
        except Exception:
            pass

    # Token attivo
    rt = db.query(RouteToken).filter(RouteToken.route_plan_id == route_id).first()

    return {
        "route_id": route_id,
        "nome": plan.nome,
        "data_giro": date_to_iso(plan.data_giro),
        "totale": len(deliveries),
        "completate": completate,
        "mancate": mancate,
        "rimanenti": len(deliveries) - fatte,
        "percentuale": round(fatte / len(deliveries) * 100) if deliveries else 0,
        "minuti_rimasti": minuti_rimasti,
        "token_attivo": rt.token if rt else None,
        "link_operatore": f"/giro/{rt.token}" if rt else None,
        "consegne": [delivery_to_operator_dict(d, statuses.get(d.id)) for d in deliveries],
    }
