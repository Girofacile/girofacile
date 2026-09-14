import io
import json
import re
import unicodedata
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from ..core.dependencies import current_user
from ..database import get_db
from ..models import TransferBookingPortalSetting, TransferBookingRequest, User, Notification

router = APIRouter(tags=["transfer-portal"])

DEFAULT_FIELDS = {
    "email": "required",
    "phone": "required",
    "passengers": "required",
    "luggage": "visible",
    "flight_train": "visible",
    "child_seat": "visible",
    "pets": "visible",
    "notes": "visible",
    "round_trip": "visible",
}


def _slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "transfer"


def _unique_slug(db: Session, base: str, current_id: int | None = None) -> str:
    slug = base
    counter = 2
    while True:
        row = db.query(TransferBookingPortalSetting).filter(TransferBookingPortalSetting.public_slug == slug).first()
        if not row or (current_id and row.id == current_id):
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def _defaults(user: User) -> dict:
    name = user.company_name or user.username or "Servizio Transfer"
    return {
        "company_name": name,
        "public_slug": _slugify(name),
        "logo_data_url": user.company_logo_url or "",
        "theme": "modern",
        "primary_color": "#0f766e",
        "secondary_color": "#ecfdf5",
        "button_color": "#0f766e",
        "text_color": "#102a2a",
        "background_color": "#f4fbfa",
        "hero_image_data_url": "",
        "title": "Prenota il tuo transfer",
        "subtitle": "Inserisci i dati della corsa e riceverai rapidamente la conferma.",
        "intro_text": "Servizio transfer professionale, puntuale e personalizzato.",
        "confirmation_message": "Richiesta inviata correttamente. Ti contatteremo appena la corsa sarà confermata.",
        "closed_message": "Le prenotazioni online sono momentaneamente sospese. Contattaci per assistenza.",
        "footer_text": "Servizio su prenotazione",
        "phone": user.company_phone or "",
        "whatsapp": user.company_phone or "",
        "email": user.company_email or user.email or "",
        "website": "",
        "fields": DEFAULT_FIELDS,
        "services": ["Transfer aeroportuale", "Transfer stazione", "Transfer privato", "Navetta"],
        "portal_status": "draft",
        "accept_bookings": True,
        "min_advance_minutes": 30,
        "show_girofacile_brand": True,
        "updated_at": None,
    }


def _serialize(row: TransferBookingPortalSetting, user: User | None = None) -> dict:
    data = {
        "company_name": row.company_name,
        "public_slug": row.public_slug,
        "logo_data_url": row.logo_data_url or "",
        "theme": row.theme,
        "primary_color": row.primary_color,
        "secondary_color": row.secondary_color,
        "button_color": row.button_color,
        "text_color": row.text_color,
        "background_color": row.background_color,
        "hero_image_data_url": row.hero_image_data_url or "",
        "title": row.title,
        "subtitle": row.subtitle,
        "intro_text": row.intro_text or "",
        "confirmation_message": row.confirmation_message,
        "closed_message": row.closed_message,
        "footer_text": row.footer_text or "",
        "phone": row.phone or "",
        "whatsapp": row.whatsapp or "",
        "email": row.email or "",
        "website": row.website or "",
        "fields": json.loads(row.fields_json or "{}"),
        "services": json.loads(row.services_json or "[]"),
        "portal_status": row.portal_status,
        "accept_bookings": bool(row.accept_bookings),
        "min_advance_minutes": row.min_advance_minutes,
        "show_girofacile_brand": bool(row.show_girofacile_brand),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if user:
        data["public_url"] = f"/prenota/{row.public_slug}"
    return data


def _get_or_create(db: Session, user: User) -> TransferBookingPortalSetting:
    row = db.query(TransferBookingPortalSetting).filter(TransferBookingPortalSetting.user_id == user.id).first()
    if row:
        return row
    d = _defaults(user)
    row = TransferBookingPortalSetting(
        user_id=user.id,
        company_name=d["company_name"],
        public_slug=_unique_slug(db, d["public_slug"]),
        logo_data_url=d["logo_data_url"],
        theme=d["theme"],
        primary_color=d["primary_color"],
        secondary_color=d["secondary_color"],
        button_color=d["button_color"],
        text_color=d["text_color"],
        background_color=d["background_color"],
        title=d["title"], subtitle=d["subtitle"], intro_text=d["intro_text"],
        confirmation_message=d["confirmation_message"], closed_message=d["closed_message"],
        footer_text=d["footer_text"], phone=d["phone"], whatsapp=d["whatsapp"], email=d["email"],
        website=d["website"], fields_json=json.dumps(d["fields"]), services_json=json.dumps(d["services"]),
        portal_status=d["portal_status"], accept_bookings=d["accept_bookings"],
        min_advance_minutes=d["min_advance_minutes"], show_girofacile_brand=d["show_girofacile_brand"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/api/transfer/booking-portal")
def get_booking_portal(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if (user.company_sector or "") != "transfer":
        raise HTTPException(status_code=403, detail="Funzione disponibile per il settore Transfer")
    row = _get_or_create(db, user)
    return _serialize(row, user)


@router.put("/api/transfer/booking-portal")
def update_booking_portal(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if (user.company_sector or "") != "transfer":
        raise HTTPException(status_code=403, detail="Funzione disponibile per il settore Transfer")
    row = _get_or_create(db, user)
    text_fields = [
        "company_name", "logo_data_url", "theme", "primary_color", "secondary_color", "button_color",
        "text_color", "background_color", "hero_image_data_url", "title", "subtitle", "intro_text",
        "confirmation_message", "closed_message", "footer_text", "phone", "whatsapp", "email", "website",
        "portal_status",
    ]
    for field in text_fields:
        if field in payload:
            value = str(payload.get(field) or "").strip()
            if field in {"logo_data_url", "hero_image_data_url"} and len(value) > 3_500_000:
                raise HTTPException(status_code=413, detail="Immagine troppo grande. Limite 2,5 MB.")
            setattr(row, field, value)
    if "public_slug" in payload:
        proposed = _slugify(str(payload.get("public_slug") or row.company_name))
        row.public_slug = _unique_slug(db, proposed, row.id)
    if "fields" in payload and isinstance(payload["fields"], dict):
        normalized = {}
        for key, default_value in DEFAULT_FIELDS.items():
            value = payload["fields"].get(key, default_value)
            normalized[key] = value if value in {"hidden", "visible", "required"} else default_value
        row.fields_json = json.dumps(normalized)
    if "services" in payload and isinstance(payload["services"], list):
        row.services_json = json.dumps([str(x).strip() for x in payload["services"] if str(x).strip()][:20])
    if "accept_bookings" in payload:
        row.accept_bookings = bool(payload["accept_bookings"])
    if "show_girofacile_brand" in payload:
        row.show_girofacile_brand = bool(payload["show_girofacile_brand"])
    if "min_advance_minutes" in payload:
        row.min_advance_minutes = max(0, min(10080, int(payload["min_advance_minutes"] or 0)))
    if row.portal_status not in {"draft", "published", "closed"}:
        row.portal_status = "draft"
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {"ok": True, "message": "Portale prenotazioni aggiornato", "settings": _serialize(row, user)}


@router.get("/api/transfer/booking-portal/qr.png")
def booking_portal_qr(
    request: Request,
    source: str = Query("", max_length=120),
    size: int = Query(420, ge=180, le=1200),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if (user.company_sector or "") != "transfer":
        raise HTTPException(status_code=403, detail="Funzione disponibile per il settore Transfer")
    row = _get_or_create(db, user)
    suffix = f"?source={source.strip()}" if source.strip() else ""
    url = f"{str(request.base_url).rstrip('/')}/prenota/{row.public_slug}{suffix}"
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        image = image.resize((size, size))
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        headers = {"Content-Disposition": f'inline; filename="qr-{row.public_slug}.png"', "Cache-Control": "no-store"}
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Impossibile generare il QR Code: {exc}")


@router.get("/api/public/transfer/{slug}")
def public_booking_config(slug: str, db: Session = Depends(get_db)):
    row = db.query(TransferBookingPortalSetting).filter(TransferBookingPortalSetting.public_slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail="Portale prenotazioni non trovato")
    data = _serialize(row)
    return data


@router.post("/api/public/transfer/{slug}/bookings")
def create_public_booking(slug: str, payload: dict, db: Session = Depends(get_db)):
    portal = db.query(TransferBookingPortalSetting).filter(TransferBookingPortalSetting.public_slug == slug).first()
    if not portal:
        raise HTTPException(status_code=404, detail="Portale prenotazioni non trovato")
    if portal.portal_status != "published" or not portal.accept_bookings:
        raise HTTPException(status_code=409, detail=portal.closed_message or "Prenotazioni non disponibili")
    required = ["customer_name", "pickup_address", "destination_address", "pickup_date", "pickup_time"]
    missing = [key for key in required if not str(payload.get(key) or "").strip()]
    fields = json.loads(portal.fields_json or "{}")
    if fields.get("phone") == "required" and not str(payload.get("phone") or "").strip(): missing.append("phone")
    if fields.get("email") == "required" and not str(payload.get("email") or "").strip(): missing.append("email")
    if missing:
        raise HTTPException(status_code=422, detail="Compila tutti i campi obbligatori")
    request_row = TransferBookingRequest(
        user_id=portal.user_id,
        portal_id=portal.id,
        customer_name=str(payload.get("customer_name") or "").strip(),
        phone=str(payload.get("phone") or "").strip() or None,
        email=str(payload.get("email") or "").strip() or None,
        pickup_address=str(payload.get("pickup_address") or "").strip(),
        destination_address=str(payload.get("destination_address") or "").strip(),
        pickup_date=str(payload.get("pickup_date") or "").strip(),
        pickup_time=str(payload.get("pickup_time") or "").strip(),
        passengers=max(1, int(payload.get("passengers") or 1)),
        luggage=str(payload.get("luggage") or "").strip() or None,
        service_type=str(payload.get("service_type") or "").strip() or None,
        flight_train=str(payload.get("flight_train") or "").strip() or None,
        child_seat=bool(payload.get("child_seat")), pets=bool(payload.get("pets")), round_trip=bool(payload.get("round_trip")),
        notes=str(payload.get("notes") or "").strip() or None,
        booking_source=str(payload.get("booking_source") or "direct").strip()[:120] or "direct",
        status="new",
    )
    db.add(request_row)
    db.flush()
    # v79: applica la modalità operativa scelta dall'azienda.
    settings = _get_operational_settings(db, db.get(User, portal.user_id))
    if settings.dispatch_mode in {"assisted", "automatic"}:
        drivers = db.query(Driver).filter(
            Driver.user_id == portal.user_id,
            Driver.deleted_at.is_(None),
            Driver.is_active.is_(True),
        ).all()
        if drivers:
            # Prima base deterministica: privilegia l'autista con meno corse già assegnate nella data richiesta.
            def workload(driver):
                return db.query(TransferBookingRequest).filter(
                    TransferBookingRequest.driver_id == driver.id,
                    TransferBookingRequest.pickup_date == request_row.pickup_date,
                    TransferBookingRequest.status.notin_(["cancelled", "rejected", "completed"]),
                ).count()
            chosen = sorted(drivers, key=lambda d: (workload(d), d.id))[0]
            request_row.driver_id = chosen.id
            request_row.assigned_at = datetime.utcnow()
            if settings.dispatch_mode == "automatic":
                request_row.status = "proposed"
                request_row.assignment_status = "proposed"
            else:
                request_row.status = "pending"
                request_row.assignment_status = "suggested"
    db.add(Notification(
        user_id=portal.user_id,
        entity_key=f"transfer-booking-{request_row.id}",
        type="transfer_booking",
        title="Nuova prenotazione Transfer",
        message=f"{request_row.customer_name}: {request_row.pickup_address} → {request_row.destination_address} alle {request_row.pickup_time}",
        entity_type="transfer_booking",
        entity_id=request_row.id,
        action_tab="transfer-bookings",
        action_label="Apri prenotazione",
    ))
    db.commit()
    db.refresh(request_row)
    return {"ok": True, "booking_id": request_row.id, "message": portal.confirmation_message}

# -----------------------------------------------------------------------
# v79 — Centro operativo Transfer
# -----------------------------------------------------------------------
from fastapi import Response
from ..models import Driver, DriverAccount, Vehicle, TransferOperationalSetting, TransferBookingEvent
from ..routers.driver import make_session_token


def _transfer_only(user: User):
    if (user.company_sector or "") != "transfer":
        raise HTTPException(status_code=403, detail="Funzione disponibile per il settore Transfer")


def _get_operational_settings(db: Session, user: User) -> TransferOperationalSetting:
    row = db.query(TransferOperationalSetting).filter(TransferOperationalSetting.user_id == user.id).first()
    if row:
        return row
    row = TransferOperationalSetting(user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row



def _add_booking_event(db: Session, row: TransferBookingRequest, event_type: str, title: str, detail: str | None = None, actor: str = "Amministratore"):
    db.add(TransferBookingEvent(booking_id=row.id, user_id=row.user_id, event_type=event_type, title=title, detail=detail, actor=actor))

def _minutes(value: str | None) -> int:
    try:
        h, m = str(value or "00:00").split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return 0

def _assignment_suggestions(db: Session, user: User, booking: TransferBookingRequest):
    settings = _get_operational_settings(db, user)
    start = _minutes(booking.pickup_time)
    duration = int(booking.estimated_minutes or 60)
    buffer_m = int(settings.airport_buffer_minutes if "aero" in ((booking.service_type or "") + " " + (booking.destination_address or "")).lower() else settings.min_buffer_minutes)
    drivers = db.query(Driver).filter(Driver.user_id == user.id, Driver.deleted_at.is_(None), Driver.is_active.is_(True)).all()
    out=[]
    for d in drivers:
        existing = db.query(TransferBookingRequest).filter(TransferBookingRequest.user_id == user.id, TransferBookingRequest.driver_id == d.id, TransferBookingRequest.pickup_date == booking.pickup_date, TransferBookingRequest.id != booking.id, TransferBookingRequest.status.notin_(["cancelled","rejected","completed"])).all()
        conflict=False; closest_gap=9999
        for x in existing:
            xs=_minutes(x.pickup_time); xe=xs+int(x.estimated_minutes or 60)
            gap_before=start-xe; gap_after=xs-(start+duration)
            closest_gap=min(closest_gap, abs(gap_before), abs(gap_after))
            if not (gap_before >= buffer_m or gap_after >= buffer_m): conflict=True
        if conflict: continue
        workload=len(existing)
        score=max(1,100-workload*12-min(30,0 if closest_gap==9999 else int(30/max(1,closest_gap/10))))
        reasons=["nessuna sovrapposizione oraria", f"{workload} corse già assegnate nella giornata"]
        if closest_gap!=9999: reasons.append(f"margine minimo stimato {closest_gap} min")
        out.append({"driver_id":d.id,"driver_name":f"{d.nome} {d.cognome or ''}".strip(),"score":score,"workload":workload,"reasons":reasons})
    return sorted(out,key=lambda x:(-x["score"],x["workload"],x["driver_name"]))[:5]



def _ensure_transfer_runtime_schema(db: Session) -> None:
    """Ripara in modo idempotente lo schema Transfer prima delle letture.

    Utile soprattutto per installazioni aggiornate copiando solo i file, dove
    PostgreSQL può avere ancora una tabella transfer_booking_requests di una
    versione precedente. Non modifica né elimina dati esistenti.
    """
    from sqlalchemy import inspect, text
    from ..database import Base

    bind = db.get_bind()
    # Crea eventuali nuove tabelle, inclusa transfer_booking_events.
    Base.metadata.create_all(bind=bind)
    inspector = inspect(bind)
    if not inspector.has_table("transfer_booking_requests"):
        return

    existing = {c["name"] for c in inspector.get_columns("transfer_booking_requests")}
    dialect = bind.dialect
    prep = dialect.identifier_preparer
    q = prep.quote
    wanted = {
        "driver_id": "INTEGER",
        "vehicle_id": "INTEGER",
        "assignment_status": "VARCHAR(30) DEFAULT 'unassigned'",
        "assigned_at": "TIMESTAMP",
        "accepted_at": "TIMESTAMP",
        "rejected_at": "TIMESTAMP",
        "estimated_minutes": "INTEGER",
        "estimated_km": "FLOAT",
        "admin_note": "TEXT",
        "booking_source": "VARCHAR(120)",
    }
    for name, definition in wanted.items():
        if name in existing:
            continue
        db.execute(text(f"ALTER TABLE {q('transfer_booking_requests')} ADD COLUMN {q(name)} {definition}"))
    db.commit()


def _safe_booking_rows(db: Session, user: User, status: str = "", date: str = ""):
    """Esegue la lettura dopo avere verificato lo schema Transfer."""
    _ensure_transfer_runtime_schema(db)
    q = db.query(TransferBookingRequest).filter(TransferBookingRequest.user_id == user.id)
    if status:
        q = q.filter(TransferBookingRequest.status == status)
    if date:
        q = q.filter(TransferBookingRequest.pickup_date == date)
    return q.order_by(TransferBookingRequest.pickup_date.asc(), TransferBookingRequest.pickup_time.asc(), TransferBookingRequest.created_at.desc()).all()

def _booking_dict(row: TransferBookingRequest, db: Session) -> dict:
    driver = db.get(Driver, row.driver_id) if row.driver_id else None
    vehicle = db.get(Vehicle, row.vehicle_id) if row.vehicle_id else None
    return {
        "id": row.id,
        "customer_name": row.customer_name,
        "phone": row.phone,
        "email": row.email,
        "pickup_address": row.pickup_address,
        "destination_address": row.destination_address,
        "pickup_date": row.pickup_date,
        "pickup_time": row.pickup_time,
        "passengers": row.passengers,
        "luggage": row.luggage,
        "service_type": row.service_type,
        "flight_train": row.flight_train,
        "child_seat": bool(row.child_seat),
        "pets": bool(row.pets),
        "round_trip": bool(row.round_trip),
        "notes": row.notes,
        "status": row.status,
        "assignment_status": row.assignment_status or "unassigned",
        "driver_id": row.driver_id,
        "driver_name": f"{driver.nome} {driver.cognome or ''}".strip() if driver else None,
        "vehicle_id": row.vehicle_id,
        "vehicle_name": (getattr(vehicle, "nome", None) or getattr(vehicle, "modello", None) or getattr(vehicle, "targa", None)) if vehicle else None,
        "assigned_at": row.assigned_at.isoformat() if row.assigned_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "estimated_minutes": row.estimated_minutes,
        "estimated_km": row.estimated_km,
        "admin_note": row.admin_note,
        "booking_source": row.booking_source or "direct",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/api/transfer/operations/settings")
def get_transfer_operational_settings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    row = _get_operational_settings(db, user)
    return {
        "dispatch_mode": row.dispatch_mode,
        "auto_strategy": row.auto_strategy,
        "driver_response_seconds": row.driver_response_seconds,
        "notify_email": bool(row.notify_email),
        "notify_internal": bool(row.notify_internal),
        "allow_driver_reject": bool(row.allow_driver_reject),
        "min_buffer_minutes": row.min_buffer_minutes,
        "airport_buffer_minutes": row.airport_buffer_minutes,
    }


@router.put("/api/transfer/operations/settings")
def update_transfer_operational_settings(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    row = _get_operational_settings(db, user)
    mode = str(payload.get("dispatch_mode") or row.dispatch_mode)
    row.dispatch_mode = mode if mode in {"manual", "assisted", "automatic"} else "manual"
    strategy = str(payload.get("auto_strategy") or row.auto_strategy)
    row.auto_strategy = strategy if strategy in {"best_fit", "nearest", "least_empty_km", "balanced"} else "best_fit"
    row.driver_response_seconds = max(15, min(600, int(payload.get("driver_response_seconds") or 60)))
    row.notify_email = bool(payload.get("notify_email", True))
    row.notify_internal = bool(payload.get("notify_internal", True))
    row.allow_driver_reject = bool(payload.get("allow_driver_reject", True))
    row.min_buffer_minutes = max(0, min(180, int(payload.get("min_buffer_minutes") or 15)))
    row.airport_buffer_minutes = max(0, min(240, int(payload.get("airport_buffer_minutes") or 30)))
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Impostazioni Transfer salvate"}


@router.get("/api/transfer/bookings/{booking_id}")
def get_transfer_booking_detail(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    row = db.query(TransferBookingRequest).filter(TransferBookingRequest.id == booking_id, TransferBookingRequest.user_id == user.id).first()
    if not row: raise HTTPException(404, "Prenotazione non trovata")
    events = db.query(TransferBookingEvent).filter(TransferBookingEvent.booking_id == row.id).order_by(TransferBookingEvent.created_at.desc()).all()
    data=_booking_dict(row,db)
    data["history"]=[{"id":e.id,"type":e.event_type,"title":e.title,"detail":e.detail,"actor":e.actor,"created_at":e.created_at.isoformat()} for e in events]
    return data

@router.get("/api/transfer/bookings/{booking_id}/suggestions")
def get_transfer_booking_suggestions(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    row = db.query(TransferBookingRequest).filter(TransferBookingRequest.id == booking_id, TransferBookingRequest.user_id == user.id).first()
    if not row: raise HTTPException(404, "Prenotazione non trovata")
    return {"booking_id":row.id,"suggestions":_assignment_suggestions(db,user,row)}


@router.get("/api/transfer/bookings")
def list_transfer_bookings(status: str = "", date: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    rows = _safe_booking_rows(db, user, status=status, date=date)
    return [_booking_dict(x, db) for x in rows]


@router.get("/api/transfer/dashboard")
def transfer_dashboard_summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    today = datetime.now().strftime("%Y-%m-%d")
    rows = _safe_booking_rows(db, user)
    today_rows = [x for x in rows if x.pickup_date == today]
    active = [x for x in today_rows if x.status in {"accepted", "in_progress", "arrived", "passenger_on_board"}]
    pending = [x for x in rows if x.status in {"new", "pending", "to_assign"}]
    unassigned = [x for x in rows if not x.driver_id and x.status not in {"completed", "cancelled", "rejected"}]
    completed = [x for x in today_rows if x.status == "completed"]
    drivers = db.query(Driver).filter(Driver.user_id == user.id, Driver.deleted_at.is_(None), Driver.is_active.is_(True)).all()
    assigned_ids = {x.driver_id for x in active if x.driver_id}
    return {
        "today": len(today_rows), "active": len(active), "pending": len(pending),
        "unassigned": len(unassigned), "completed": len(completed),
        "drivers_available": max(0, len(drivers)-len(assigned_ids)), "drivers_busy": len(assigned_ids),
        "next_bookings": [_booking_dict(x, db) for x in sorted(today_rows, key=lambda r: r.pickup_time)[:8]],
    }


@router.post("/api/transfer/bookings")
def create_manual_transfer_booking(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    required = ["customer_name", "pickup_address", "destination_address", "pickup_date", "pickup_time"]
    if any(not str(payload.get(k) or "").strip() for k in required):
        raise HTTPException(422, "Compila tutti i campi obbligatori")
    portal = _get_or_create(db, user)
    row = TransferBookingRequest(
        user_id=user.id, portal_id=portal.id,
        customer_name=str(payload.get("customer_name") or "").strip(),
        phone=str(payload.get("phone") or "").strip() or None,
        email=str(payload.get("email") or "").strip() or None,
        pickup_address=str(payload.get("pickup_address") or "").strip(),
        destination_address=str(payload.get("destination_address") or "").strip(),
        pickup_date=str(payload.get("pickup_date") or "").strip(),
        pickup_time=str(payload.get("pickup_time") or "").strip(),
        passengers=max(1, int(payload.get("passengers") or 1)),
        luggage=str(payload.get("luggage") or "").strip() or None,
        service_type=str(payload.get("service_type") or "").strip() or None,
        flight_train=str(payload.get("flight_train") or "").strip() or None,
        notes=str(payload.get("notes") or "").strip() or None,
        booking_source="manual",
        status="new", assignment_status="unassigned",
    )
    db.add(row); db.flush(); _add_booking_event(db,row,"created","Prenotazione inserita manualmente",f"{row.pickup_address} → {row.destination_address}"); db.commit(); db.refresh(row)
    return {"ok": True, "message": "Prenotazione inserita", "booking": _booking_dict(row, db)}


@router.put("/api/transfer/bookings/{booking_id}")
def update_transfer_booking(booking_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    row = db.query(TransferBookingRequest).filter(TransferBookingRequest.id == booking_id, TransferBookingRequest.user_id == user.id).first()
    if not row:
        raise HTTPException(404, "Prenotazione non trovata")
    if "driver_id" in payload:
        driver_id = int(payload.get("driver_id") or 0) or None
        if driver_id:
            driver = db.query(Driver).filter(Driver.id == driver_id, Driver.user_id == user.id, Driver.deleted_at.is_(None)).first()
            if not driver: raise HTTPException(404, "Autista non trovato")
        row.driver_id = driver_id
        row.assignment_status = "proposed" if driver_id else "unassigned"
        row.assigned_at = datetime.utcnow() if driver_id else None
        _add_booking_event(db,row,"assignment","Autista assegnato" if driver_id else "Assegnazione rimossa", f"Driver ID: {driver_id}" if driver_id else None)
        if driver_id and row.status in {"new", "pending", "to_assign"}: row.status = "proposed"
    if "vehicle_id" in payload:
        row.vehicle_id = int(payload.get("vehicle_id") or 0) or None
    if "status" in payload:
        status = str(payload.get("status") or "")
        allowed = {"new","pending","to_assign","proposed","accepted","arrived","passenger_on_board","in_progress","completed","rejected","cancelled","no_show"}
        if status in allowed:
            old_status=row.status
            row.status = status
            if old_status != status: _add_booking_event(db,row,"status",f"Stato aggiornato: {status}",f"Da {old_status} a {status}")
            if status == "accepted": row.accepted_at = datetime.utcnow(); row.assignment_status = "accepted"
            elif status == "rejected": row.rejected_at = datetime.utcnow(); row.assignment_status = "rejected"
            elif status == "completed": row.assignment_status = "completed"
    editable = {"customer_name","phone","email","pickup_address","destination_address","pickup_date","pickup_time","luggage","service_type","flight_train","notes"}
    changed=[]
    for field in editable:
        if field in payload:
            value=str(payload.get(field) or "").strip() or None
            if field in {"customer_name","pickup_address","destination_address","pickup_date","pickup_time"} and not value:
                raise HTTPException(422, f"Il campo {field} è obbligatorio")
            if getattr(row,field)!=value: setattr(row,field,value); changed.append(field)
    if "passengers" in payload:
        val=max(1,int(payload.get("passengers") or 1))
        if row.passengers!=val: row.passengers=val; changed.append("passengers")
    for field in ("child_seat","pets","round_trip"):
        if field in payload:
            val=bool(payload.get(field))
            if getattr(row,field)!=val: setattr(row,field,val); changed.append(field)
    if "estimated_minutes" in payload: row.estimated_minutes=max(1,int(payload.get("estimated_minutes") or 60)); changed.append("estimated_minutes")
    if "estimated_km" in payload: row.estimated_km=max(0,float(payload.get("estimated_km") or 0)); changed.append("estimated_km")
    if "admin_note" in payload: row.admin_note = str(payload.get("admin_note") or "").strip() or None; changed.append("admin_note")
    if changed: _add_booking_event(db,row,"updated","Prenotazione aggiornata",", ".join(changed))
    db.commit(); db.refresh(row)
    return {"ok": True, "message": "Prenotazione aggiornata", "booking": _booking_dict(row, db)}


@router.get("/api/transfer/admin-driver")
def get_admin_driver_profile(db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    driver = db.query(Driver).filter(Driver.user_id == user.id, Driver.is_admin_driver.is_(True), Driver.deleted_at.is_(None)).first()
    return {"exists": bool(driver), "driver": _booking_driver_dict(driver) if driver else None}


def _booking_driver_dict(driver: Driver) -> dict:
    return {"id": driver.id, "nome": driver.nome, "cognome": driver.cognome, "email": driver.email, "telefono": driver.telefono, "patente": driver.patente, "photo_url": driver.photo_url, "is_active": bool(driver.is_active)}


@router.post("/api/transfer/admin-driver")
def create_admin_driver_profile(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    existing = db.query(Driver).filter(Driver.user_id == user.id, Driver.is_admin_driver.is_(True), Driver.deleted_at.is_(None)).first()
    if existing:
        return {"ok": True, "message": "Profilo autista amministratore già presente", "driver": _booking_driver_dict(existing)}
    full = (user.username or user.company_name or "Amministratore").strip().split(" ", 1)
    driver = Driver(
        user_id=user.id, nome=str(payload.get("nome") or full[0]).strip(),
        cognome=str(payload.get("cognome") or (full[1] if len(full)>1 else "")).strip() or None,
        email=(user.email or user.company_email or f"admin-{user.id}@girofacile.local").strip().lower(),
        telefono=str(payload.get("telefono") or user.company_phone or "").strip() or None,
        patente=str(payload.get("patente") or "").strip() or None,
        note="Profilo autista collegato all'account amministratore", is_admin_driver=True, is_active=True,
    )
    db.add(driver); db.commit(); db.refresh(driver)
    account = db.query(DriverAccount).filter(DriverAccount.driver_id == driver.id).first()
    if not account:
        account = DriverAccount(driver_id=driver.id, email=f"admin-driver-{user.id}@girofacile.local", password_hash=user.password_hash, is_active=True)
        db.add(account); db.commit()
    return {"ok": True, "message": "Profilo autista amministratore creato", "driver": _booking_driver_dict(driver)}


@router.post("/api/transfer/admin-driver/enter")
def enter_admin_driver_portal(response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _transfer_only(user)
    driver = db.query(Driver).filter(Driver.user_id == user.id, Driver.is_admin_driver.is_(True), Driver.deleted_at.is_(None)).first()
    if not driver: raise HTTPException(409, "Crea prima il profilo autista amministratore")
    account = db.query(DriverAccount).filter(DriverAccount.driver_id == driver.id).first()
    if not account:
        account = DriverAccount(driver_id=driver.id, email=f"admin-driver-{user.id}@girofacile.local", password_hash=user.password_hash, is_active=True)
        db.add(account); db.commit(); db.refresh(account)
    response.set_cookie("driver_session", make_session_token(account), **cookie_options(60*60*24*30))
    return {"ok": True, "url": "/driver", "return_to_dashboard": True}
