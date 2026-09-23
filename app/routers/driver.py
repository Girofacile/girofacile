"""
Portale autista — autenticazione separata, giri assegnati, chat, monitoraggio.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.delivery_signature import apply_delivery_signature
from ..core.dependencies import current_user, owned
from ..core.security import hash_password as secure_hash_password, password_needs_rehash, validate_password_strength, verify_password
from ..core.utils import local_now, local_today, date_to_iso, time_to_hhmm, minutes_from_hhmm
from ..services.plans import require_feature
from ..models import (
    ChatMessage, Customer, Delivery, DeliveryStatus,
    Driver, DriverAccount, DriverSetupToken, RoutePlan, User
)

router = APIRouter(prefix="/api/driver", tags=["driver"])

TEMPO_SCARICO_OPTIONS = [10, 15, 20, 30, 45, 60, 90]
MOTIVI_MANCATA = ["assente", "chiuso", "rifiutato", "altro"]


def _require_driver_chat_feature(driver_id: int, db: Session):
    """Blocca la chat autisti quando il piano aziendale non la include."""
    driver = db.get(Driver, driver_id)
    if not driver or not driver.user_id:
        raise HTTPException(404, "Autista non trovato")
    owner = db.get(User, driver.user_id)
    if not owner:
        raise HTTPException(404, "Azienda non trovata")
    require_feature(owner, "has_driver_chat")
    return driver, owner

MOTIVI_LABELS = {
    "assente": "Cliente assente",
    "chiuso": "Attività chiusa",
    "rifiutato": "Consegna rifiutata",
    "altro": "Altro motivo"
}

def update_customer_unload_time(customer: Customer, tempo: int):
    """Aggiorna il tempo scarico stimato usando una media progressiva.

    L'autista inserisce il tempo reale della singola consegna; il profilo
    cliente viene aggiornato senza sostituire brutalmente il dato storico.
    """
    try:
        tempo = int(tempo)
    except Exception:
        return
    if tempo <= 0:
        return
    count = int(getattr(customer, "tempo_scarico_rilevazioni", 0) or 0)
    current = int(getattr(customer, "tempo_scarico_min", 10) or 10)
    new_avg = round(((current * count) + tempo) / (count + 1))
    customer.tempo_scarico_min = int(new_avg)
    customer.tempo_scarico_rilevazioni = count + 1


# -----------------------------------------------------------------------
# Helpers auth
# -----------------------------------------------------------------------

def hash_password(password: str) -> str:
    # v70: nuovo hash professionale. La verifica resta retrocompatibile
    # tramite verify_password per gli account SHA-256 già presenti.
    return secure_hash_password(password)

def make_driver_token(driver_account_id: int) -> str:
    return hashlib.sha256(f"driver-{driver_account_id}-{secrets.token_hex(16)}".encode()).hexdigest()

def get_current_driver(
    driver_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db)
) -> DriverAccount:
    if not driver_session:
        raise HTTPException(401, "Non autenticato")
    # Token = sha256 of "driver-{id}-{secret}" stored as cookie
    # We store token in a simple way: "id:hash"
    try:
        parts = driver_session.split(":", 1)
        if len(parts) != 2:
            raise HTTPException(401, "Sessione non valida")
        da_id = int(parts[0])
        token_hash = parts[1]
        da = db.get(DriverAccount, da_id)
        if not da or not da.is_active:
            raise HTTPException(401, "Account non trovato")
        expected = hashlib.sha256(f"driver-session-{da_id}-{da.password_hash}".encode()).hexdigest()
        if token_hash != expected:
            raise HTTPException(401, "Sessione scaduta")
        return da
    except (ValueError, AttributeError):
        raise HTTPException(401, "Sessione non valida")

def make_session_token(da: DriverAccount) -> str:
    token_hash = hashlib.sha256(f"driver-session-{da.id}-{da.password_hash}".encode()).hexdigest()
    return f"{da.id}:{token_hash}"

def get_or_create_delivery_status(delivery_id: int, route_plan_id: int, db: Session) -> DeliveryStatus:
    ds = db.query(DeliveryStatus).filter(
        DeliveryStatus.delivery_id == delivery_id,
        DeliveryStatus.route_plan_id == route_plan_id
    ).first()
    if not ds:
        ds = DeliveryStatus(delivery_id=delivery_id, route_plan_id=route_plan_id, status="in_attesa")
        db.add(ds)
        db.commit()
        db.refresh(ds)
    return ds


def refresh_route_completion(route_plan_id: int, db: Session) -> None:
    """Chiude automaticamente il giro quando tutte le consegne sono gestite."""
    route = db.get(RoutePlan, route_plan_id)
    if not route:
        return
    deliveries = list(route.deliveries or [])
    if not deliveries:
        return
    statuses = {
        ds.delivery_id: ds.status
        for ds in db.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == route_plan_id).all()
    }
    all_closed = all(statuses.get(d.id) in ("completata", "mancata") for d in deliveries)
    if all_closed and route.status != "completato":
        route.status = "completato"
        route.completed_at = datetime.utcnow()
    elif not all_closed and route.status == "completato":
        route.status = "in_corso"
        route.completed_at = None


# -----------------------------------------------------------------------
# Setup account (primo accesso)
# -----------------------------------------------------------------------

@router.get("/setup/{token}")
def get_setup_info(token: str, db: Session = Depends(get_db)):
    """Restituisce info autista per la pagina di setup password."""
    st = db.query(DriverSetupToken).filter(DriverSetupToken.token == token).first()
    if not st:
        raise HTTPException(404, "Link non valido o scaduto")
    if datetime.utcnow() > st.expires_at:
        raise HTTPException(410, "Link scaduto. Contatta l'amministratore per riceverne uno nuovo.")
    if st.used_at:
        raise HTTPException(409, "Questo link è già stato utilizzato. Accedi con le tue credenziali.")
    driver = db.get(Driver, st.driver_id)
    if not driver:
        raise HTTPException(404, "Autista non trovato")
    return {
        "driver_name": f"{driver.nome} {driver.cognome or ''}".strip(),
        "email": driver.email,
        "token_valid": True
    }

@router.post("/setup/{token}")
def complete_setup(token: str, payload: dict, response: Response, db: Session = Depends(get_db)):
    """Completa il setup: imposta la password e crea l'account driver."""
    st = db.query(DriverSetupToken).filter(DriverSetupToken.token == token).first()
    if not st:
        raise HTTPException(404, "Link non valido")
    if datetime.utcnow() > st.expires_at:
        raise HTTPException(410, "Link scaduto")
    if st.used_at:
        raise HTTPException(409, "Link già utilizzato")

    password = (payload.get("password") or "").strip()
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    driver = db.get(Driver, st.driver_id)
    if not driver or not driver.email:
        raise HTTPException(400, "Email autista non configurata")

    # Controlla se esiste già un account
    existing = db.query(DriverAccount).filter(DriverAccount.driver_id == driver.id).first()
    if existing:
        existing.password_hash = hash_password(password)
        existing.is_active = True
        da = existing
    else:
        da = DriverAccount(
            driver_id=driver.id,
            email=driver.email.strip().lower(),
            password_hash=hash_password(password),
            is_active=True
        )
        db.add(da)

    st.used_at = datetime.utcnow()
    db.commit()
    db.refresh(da)

    # Auto-login
    session_token = make_session_token(da)
    response.set_cookie("driver_session", session_token, **cookie_options(60*60*24*30))
    return {"ok": True, "driver_name": f"{driver.nome} {driver.cognome or ''}".strip()}


# -----------------------------------------------------------------------
# Login / Logout
# -----------------------------------------------------------------------

@router.post("/login")
def driver_login(payload: dict, response: Response, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    password = (payload.get("password") or "").strip()
    da = db.query(DriverAccount).filter(DriverAccount.email == email).first()
    if not da or not verify_password(password, da.password_hash):
        raise HTTPException(401, "Email o password non corretti")
    if not da.is_active:
        raise HTTPException(403, "Account disabilitato")
    if password_needs_rehash(da.password_hash):
        da.password_hash = hash_password(password)
    da.last_login = datetime.utcnow()
    db.commit()
    session_token = make_session_token(da)
    response.set_cookie("driver_session", session_token, **cookie_options(60*60*24*30))
    driver = db.get(Driver, da.driver_id)
    return {
        "ok": True,
        "driver_id": da.driver_id,
        "driver_name": f"{driver.nome} {driver.cognome or ''}".strip() if driver else "",
        "email": da.email
    }

@router.post("/logout")
def driver_logout(response: Response):
    response.delete_cookie("driver_session")
    return {"ok": True}

@router.get("/me")
def driver_me(da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    driver = db.get(Driver, da.driver_id)
    return {
        "authenticated": True,
        "driver_id": da.driver_id,
        "driver_name": f"{driver.nome} {driver.cognome or ''}".strip() if driver else "",
        "email": da.email,
        "telefono": driver.telefono if driver else None,
        "is_admin_driver": bool(driver and getattr(driver, "is_admin_driver", False)),
    }


# -----------------------------------------------------------------------
# Giri assegnati
# -----------------------------------------------------------------------

@router.get("/routes")
def get_driver_routes(da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    """Restituisce tutti i giri assegnati all'autista."""
    routes = db.query(RoutePlan).filter(
        RoutePlan.driver_id == da.driver_id
    ).order_by(RoutePlan.data_giro.desc()).all()

    result = []
    for r in routes:
        deliveries = r.deliveries or []
        statuses = {
            ds.delivery_id: ds
            for ds in db.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == r.id).all()
        }
        completate = sum(1 for ds in statuses.values() if ds.status == "completata")
        mancate = sum(1 for ds in statuses.values() if ds.status == "mancata")

        today = local_today()
        current_status = r.status or "programmato"
        can_start = r.data_giro == today and current_status in ("programmato", "bozza")
        before_time = False
        if can_start and r.orario_partenza:
            try:
                mins = minutes_from_hhmm(r.orario_partenza)
                h, m = divmod(mins or 0, 60)
                now = datetime.now()
                scheduled = now.replace(hour=h, minute=m, second=0, microsecond=0)
                before_time = now < scheduled
            except Exception:
                pass

        result.append({
            "id": r.id,
            "nome": r.nome,
            "data_giro": date_to_iso(r.data_giro),
            "orario_partenza": time_to_hhmm(r.orario_partenza),
            "orario_rientro_stimato": time_to_hhmm(r.orario_rientro_stimato),
            "status": current_status,
            "totale_km": r.totale_km,
            "totale_minuti": r.totale_minuti,
            "n_consegne": len(deliveries),
            "completate": completate,
            "mancate": mancate,
            "deposit_nome": r.deposit.nome if r.deposit else None,
            "vehicle_nome": r.vehicle.nome if r.vehicle else None,
            "can_start": can_start,
            "before_time": before_time,
            "is_future": r.data_giro > today,
            "is_past": r.data_giro < today,
        })
    return result

@router.post("/routes/{route_id}/start")
def start_route(route_id: int, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    """Avvia il giro (cambia status a in_corso)."""
    r = db.query(RoutePlan).filter(
        RoutePlan.id == route_id,
        RoutePlan.driver_id == da.driver_id
    ).first()
    if not r:
        raise HTTPException(404, "Giro non trovato")
    if r.status not in ("completato", "annullato"):
        r.status = "in_corso"
        if not getattr(r, "started_at", None):
            r.started_at = local_now().replace(tzinfo=None)
    db.commit()

    # Inizializza DeliveryStatus per tutte le consegne
    for d in (r.deliveries or []):
        get_or_create_delivery_status(d.id, r.id, db)

    return {"ok": True}

@router.get("/routes/{route_id}")
def get_driver_route_detail(route_id: int, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    """Dettaglio giro per l'autista."""
    r = db.query(RoutePlan).filter(
        RoutePlan.id == route_id,
        RoutePlan.driver_id == da.driver_id
    ).first()
    if not r:
        raise HTTPException(404, "Giro non trovato")

    deliveries = sorted(r.deliveries or [], key=lambda x: x.ordine or 0)
    statuses = {
        ds.delivery_id: ds
        for ds in db.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == r.id).all()
    }
    for d in deliveries:
        if d.id not in statuses:
            statuses[d.id] = get_or_create_delivery_status(d.id, r.id, db)

    completate = sum(1 for ds in statuses.values() if ds.status == "completata")
    mancate = sum(1 for ds in statuses.values() if ds.status == "mancata")
    prossima_idx = next((i for i, d in enumerate(deliveries) if statuses.get(d.id) and statuses[d.id].status == "in_attesa"), None)

    def ds_dict(d):
        ds = statuses.get(d.id)
        return {
            "id": d.id, "ordine": d.ordine, "customer_id": d.customer_id,
            "cliente_nome": d.cliente_nome, "indirizzo": d.indirizzo,
            "colli": d.colli, "peso_kg": d.peso_kg,
            "scarico_mattina_da": time_to_hhmm(d.scarico_mattina_da), "scarico_mattina_a": time_to_hhmm(d.scarico_mattina_a),
            "scarico_pomeriggio_da": time_to_hhmm(d.scarico_pomeriggio_da), "scarico_pomeriggio_a": time_to_hhmm(d.scarico_pomeriggio_a),
            "tempo_scarico_min": d.tempo_scarico_min, "ztl": d.ztl, "sponda": d.sponda,
            "note": d.note, "arrivo_stimato": time_to_hhmm(d.arrivo_stimato), "partenza_stimata": time_to_hhmm(d.partenza_stimata),
            "km_tappa": d.km_tappa, "warning": d.warning,
            "status": ds.status if ds else "in_attesa",
            "motivo_mancata": ds.motivo_mancata if ds else None,
            "tempo_scarico_effettivo": ds.tempo_scarico_effettivo if ds else None,
            "note_operatore": ds.note_operatore if ds else None,
            "completata_il": ds.completata_il.isoformat() if ds and ds.completata_il else None,
            "signature_data": ds.signature_data if ds else None,
            "signed_by_name": ds.signed_by_name if ds else None,
            "signed_at": ds.signed_at.isoformat() if ds and ds.signed_at else None,
            "signature_note": ds.signature_note if ds else None,
        }

    return {
        "route": {
            "id": r.id, "nome": r.nome, "data_giro": date_to_iso(r.data_giro),
            "orario_partenza": time_to_hhmm(r.orario_partenza), "orario_rientro_stimato": time_to_hhmm(r.orario_rientro_stimato),
            "totale_km": r.totale_km, "totale_minuti": r.totale_minuti,
            "status": r.status, "google_maps_url": r.google_maps_url,
            "deposit_nome": r.deposit.nome if r.deposit else None,
            "deposit_indirizzo": r.deposit.indirizzo if r.deposit else None,
        },
        "consegne": [ds_dict(d) for d in deliveries],
        "progress": {
            "totale": len(deliveries), "completate": completate, "mancate": mancate,
            "rimanenti": len(deliveries) - completate - mancate,
            "prossima_idx": prossima_idx,
            "percentuale": round((completate + mancate) / len(deliveries) * 100) if deliveries else 0,
        },
        "settings": {
            "delivery_signature_enabled": bool(getattr(db.get(User, r.user_id), "delivery_signature_enabled", False)) if r.user_id else False,
        },
        "tempo_scarico_options": TEMPO_SCARICO_OPTIONS,
        "motivi_mancata": MOTIVI_MANCATA,
        "motivi_labels": MOTIVI_LABELS,
    }


# -----------------------------------------------------------------------
# Consegne
# -----------------------------------------------------------------------

@router.post("/delivery/{delivery_id}/signature")
def save_delivery_signature(delivery_id: int, payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if not d:
        raise HTTPException(404, "Consegna non trovata")
    r = db.get(RoutePlan, d.route_plan_id)
    if not r or r.driver_id != da.driver_id:
        raise HTTPException(403, "Non autorizzato")
    owner = db.get(User, r.user_id) if r and r.user_id else None
    if not owner or not getattr(owner, "delivery_signature_enabled", False):
        raise HTTPException(400, "Firma cliente non attiva per questa azienda")

    ds = get_or_create_delivery_status(delivery_id, d.route_plan_id, db)
    apply_delivery_signature(ds, payload, owner, required=True)
    db.commit()
    return {"ok": True}

@router.post("/delivery/{delivery_id}/complete")
def complete_delivery(delivery_id: int, payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if not d:
        raise HTTPException(404, "Consegna non trovata")
    r = db.get(RoutePlan, d.route_plan_id)
    if not r or r.driver_id != da.driver_id:
        raise HTTPException(403, "Non autorizzato")
    ds = get_or_create_delivery_status(delivery_id, d.route_plan_id, db)
    owner = db.get(User, r.user_id) if r.user_id else None
    apply_delivery_signature(ds, payload, owner, required=True)
    ds.status = "completata"
    ds.tempo_scarico_effettivo = payload.get("tempo_scarico")
    ds.note_operatore = payload.get("note") or None
    ds.completata_il = local_now().replace(tzinfo=None)

    if payload.get("tempo_scarico") and d.customer_id:
        customer = db.get(Customer, d.customer_id)
        if customer:
            update_customer_unload_time(customer, payload["tempo_scarico"])
    refresh_route_completion(d.route_plan_id, db)
    db.commit()
    return {"ok": True}

@router.post("/delivery/{delivery_id}/missed")
def missed_delivery(delivery_id: int, payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if not d:
        raise HTTPException(404, "Consegna non trovata")
    r = db.get(RoutePlan, d.route_plan_id)
    if not r or r.driver_id != da.driver_id:
        raise HTTPException(403, "Non autorizzato")
    ds = get_or_create_delivery_status(delivery_id, d.route_plan_id, db)
    ds.status = "mancata"
    ds.motivo_mancata = payload.get("motivo") or "altro"
    ds.note_operatore = payload.get("note") or None
    ds.completata_il = local_now().replace(tzinfo=None)
    refresh_route_completion(d.route_plan_id, db)
    db.commit()
    return {"ok": True}

@router.post("/delivery/{delivery_id}/note")
def add_note(delivery_id: int, payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    d = db.get(Delivery, delivery_id)
    if not d:
        raise HTTPException(404, "Consegna non trovata")
    r = db.get(RoutePlan, d.route_plan_id)
    if not r or r.driver_id != da.driver_id:
        raise HTTPException(403, "Non autorizzato")
    ds = get_or_create_delivery_status(delivery_id, d.route_plan_id, db)
    ds.note_operatore = (payload.get("note") or "").strip() or None
    db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------
# Chat
# -----------------------------------------------------------------------

@router.get("/chat/direct")
def get_driver_direct_chat(since_id: int = 0, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    """Chat libera autista/amministratore, non collegata a un giro."""
    _require_driver_chat_feature(da.driver_id, db)
    msgs = db.query(ChatMessage).filter(
        ChatMessage.route_plan_id == 0,
        ChatMessage.driver_id == da.driver_id,
        ChatMessage.id > since_id
    ).order_by(ChatMessage.created_at).all()
    for m in msgs:
        if m.sender_type == "admin" and not m.read_at:
            m.read_at = datetime.utcnow()
    db.commit()
    return [{"id": m.id, "sender_type": m.sender_type, "sender_name": m.sender_name,
             "message": m.message, "created_at": m.created_at.isoformat()} for m in msgs]


@router.post("/chat/direct")
def send_driver_direct_message(payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    """Invia messaggio libero al responsabile, senza selezionare un giro."""
    driver, _owner = _require_driver_chat_feature(da.driver_id, db)
    name = f"{driver.nome} {driver.cognome or ''}".strip() if driver else "Autista"
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "Messaggio vuoto")
    msg = ChatMessage(route_plan_id=0, driver_id=da.driver_id, sender_type="driver", sender_name=name, message=message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "id": msg.id}


@router.get("/chat/{route_id}")
def get_driver_chat(route_id: int, since_id: int = 0, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    r = db.query(RoutePlan).filter(RoutePlan.id == route_id, RoutePlan.driver_id == da.driver_id).first()
    if not r:
        raise HTTPException(404, "Giro non trovato")
    msgs = db.query(ChatMessage).filter(
        ChatMessage.route_plan_id == route_id,
        ChatMessage.id > since_id
    ).order_by(ChatMessage.created_at).all()
    # Marca come letti i messaggi admin
    for m in msgs:
        if m.sender_type == "admin" and not m.read_at:
            m.read_at = datetime.utcnow()
    db.commit()
    return [{"id": m.id, "sender_type": m.sender_type, "sender_name": m.sender_name,
             "message": m.message, "created_at": m.created_at.isoformat()} for m in msgs]

@router.post("/chat/{route_id}")
def send_driver_message(route_id: int, payload: dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    r = db.query(RoutePlan).filter(RoutePlan.id == route_id, RoutePlan.driver_id == da.driver_id).first()
    if not r:
        raise HTTPException(404, "Giro non trovato")
    driver = db.get(Driver, da.driver_id)
    name = f"{driver.nome} {driver.cognome or ''}".strip() if driver else "Autista"
    msg = ChatMessage(
        route_plan_id=route_id, driver_id=da.driver_id, sender_type="driver", sender_name=name,
        message=(payload.get("message") or "").strip()
    )
    if not msg.message:
        raise HTTPException(400, "Messaggio vuoto")
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "id": msg.id}




# -----------------------------------------------------------------------
# Chat lato admin
# -----------------------------------------------------------------------


@router.get("/admin/chat-threads")
def list_admin_chat_threads(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_driver_chat")
    """Elenco chat libere autisti/amministratore.

    Le conversazioni non sono più obbligatoriamente legate a un giro.
    Ogni thread è associato all'autista; eventuali chat di giro restano
    disponibili nel dettaglio del giro, ma il centro Chat autisti usa
    la conversazione diretta.
    """
    drivers = owned(db.query(Driver), Driver, user).order_by(Driver.nome.asc(), Driver.cognome.asc()).all()
    out = []
    for driver in drivers:
        last = db.query(ChatMessage).filter(
            ChatMessage.route_plan_id == 0,
            ChatMessage.driver_id == driver.id
        ).order_by(ChatMessage.created_at.desc()).first()
        unread = db.query(ChatMessage).filter(
            ChatMessage.route_plan_id == 0,
            ChatMessage.driver_id == driver.id,
            ChatMessage.sender_type == "driver",
            ChatMessage.read_at == None
        ).count()
        out.append({
            "driver_id": driver.id,
            "route_id": None,
            "route_name": "Chat libera amministratore",
            "route_status": None,
            "date": None,
            "driver_name": f"{driver.nome} {driver.cognome or ''}".strip(),
            "driver_photo_url": driver.photo_url,
            "vehicle_name": None,
            "unread": unread,
            "last_message": (last.message if last else None),
            "last_sender_type": (last.sender_type if last else None),
            "last_message_at": (last.created_at.isoformat() if last else None),
        })
    out.sort(key=lambda x: (x["unread"] <= 0, x["last_message_at"] or "", x["driver_name"]), reverse=False)
    return out

@router.get("/admin/chat/{route_id}")
def get_admin_chat(route_id: int, since_id: int = 0, mark_read: bool = True, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_driver_chat")
    """Chat lato admin — protetta dall'account azienda."""
    route = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not route:
        raise HTTPException(404, "Giro non trovato")
    msgs = db.query(ChatMessage).filter(
        ChatMessage.route_plan_id == route_id,
        ChatMessage.id > since_id
    ).order_by(ChatMessage.created_at).all()
    unread = sum(1 for m in msgs if m.sender_type == "driver" and not m.read_at)
    if mark_read:
        for m in msgs:
            if m.sender_type == "driver" and not m.read_at:
                m.read_at = datetime.utcnow()
        db.commit()
    return {
        "messages": [{"id": m.id, "sender_type": m.sender_type, "sender_name": m.sender_name,
                      "message": m.message, "created_at": m.created_at.isoformat(),
                      "read_at": m.read_at.isoformat() if m.read_at else None} for m in msgs],
        "unread": unread
    }

@router.post("/admin/chat/{route_id}")
def send_admin_message(route_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_driver_chat")
    """Invia messaggio admin."""
    route = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not route:
        raise HTTPException(404, "Giro non trovato")
    sender = (payload.get("sender_name") or "Amministratore").strip()
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "Messaggio vuoto")
    msg = ChatMessage(route_plan_id=route_id, sender_type="admin", sender_name=sender, message=message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "id": msg.id}


@router.get("/admin/direct-chat/{driver_id}")
def get_admin_direct_chat(driver_id: int, since_id: int = 0, mark_read: bool = True, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_driver_chat")
    """Legge la chat libera con un autista."""
    driver = owned(db.query(Driver), Driver, user).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(404, "Autista non trovato")
    msgs = db.query(ChatMessage).filter(
        ChatMessage.route_plan_id == 0,
        ChatMessage.driver_id == driver_id,
        ChatMessage.id > since_id
    ).order_by(ChatMessage.created_at).all()
    unread = sum(1 for m in msgs if m.sender_type == "driver" and not m.read_at)
    if mark_read:
        for m in msgs:
            if m.sender_type == "driver" and not m.read_at:
                m.read_at = datetime.utcnow()
        db.commit()
    return {
        "messages": [{"id": m.id, "sender_type": m.sender_type, "sender_name": m.sender_name,
                      "message": m.message, "created_at": m.created_at.isoformat(),
                      "read_at": m.read_at.isoformat() if m.read_at else None} for m in msgs],
        "unread": unread
    }


@router.post("/admin/direct-chat/{driver_id}")
def send_admin_direct_message(driver_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_driver_chat")
    """Invia messaggio libero all'autista."""
    driver = owned(db.query(Driver), Driver, user).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(404, "Autista non trovato")
    sender = (payload.get("sender_name") or "Amministratore").strip()
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "Messaggio vuoto")
    msg = ChatMessage(route_plan_id=0, driver_id=driver_id, sender_type="admin", sender_name=sender, message=message)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return {"ok": True, "id": msg.id}


# -----------------------------------------------------------------------
# Generazione token setup (chiamato quando si aggiunge/modifica autista)
# -----------------------------------------------------------------------

def create_driver_setup_token(driver_id: int, db: Session) -> str:
    """Genera e salva un token di setup per l'autista."""
    db.query(DriverSetupToken).filter(
        DriverSetupToken.driver_id == driver_id,
        DriverSetupToken.used_at == None
    ).delete()
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(days=7)
    st = DriverSetupToken(driver_id=driver_id, token=token, expires_at=expires)
    db.add(st)
    db.commit()
    return token

# -----------------------------------------------------------------------
# v79 — Corse Transfer assegnate all'autista
# -----------------------------------------------------------------------
@router.get('/transfer-bookings')
def get_driver_transfer_bookings(da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    from ..models import TransferBookingRequest, Vehicle
    driver = db.get(Driver, da.driver_id)
    if not driver:
        raise HTTPException(404, 'Autista non trovato')
    rows = db.query(TransferBookingRequest).filter(
        TransferBookingRequest.driver_id == driver.id,
        TransferBookingRequest.status.notin_(['cancelled'])
    ).order_by(TransferBookingRequest.pickup_date.asc(), TransferBookingRequest.pickup_time.asc()).all()
    result=[]
    for r in rows:
        vehicle=db.get(Vehicle, r.vehicle_id) if r.vehicle_id else None
        result.append({
            'id':r.id,'customer_name':r.customer_name,'phone':r.phone,'email':r.email,
            'pickup_address':r.pickup_address,'destination_address':r.destination_address,
            'pickup_date':r.pickup_date,'pickup_time':r.pickup_time,'passengers':r.passengers,
            'luggage':r.luggage,'service_type':r.service_type,'flight_train':r.flight_train,
            'notes':r.notes,'status':r.status,'assignment_status':r.assignment_status,
            'vehicle_name':vehicle.nome if vehicle else None,
        })
    return result


@router.put('/transfer-bookings/{booking_id}')
def update_driver_transfer_booking(booking_id:int, payload:dict, da: DriverAccount = Depends(get_current_driver), db: Session = Depends(get_db)):
    from ..models import TransferBookingRequest
    row=db.query(TransferBookingRequest).filter(
        TransferBookingRequest.id==booking_id,
        TransferBookingRequest.driver_id==da.driver_id
    ).first()
    if not row:
        raise HTTPException(404,'Corsa non trovata')
    status=str(payload.get('status') or '')
    allowed={'accepted','rejected','arrived','passenger_on_board','in_progress','completed','no_show'}
    if status not in allowed:
        raise HTTPException(422,'Stato non valido')
    row.status=status
    if status=='accepted':
        row.assignment_status='accepted'; row.accepted_at=datetime.utcnow()
    elif status=='rejected':
        row.assignment_status='rejected'; row.rejected_at=datetime.utcnow(); row.driver_id=None
    elif status=='completed':
        row.assignment_status='completed'
    db.commit()
    return {'ok':True,'message':'Corsa aggiornata'}
