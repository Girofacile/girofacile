from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..core.dependencies import current_user, owned
from ..core.utils import local_today, parse_date_value
from ..database import get_db
from ..models import Driver, DriverAccount, RoutePlan, User, Vehicle
from ..services.fuel_prices import get_daily_prices
from ..services.vehicle_lookup import VehicleLookupError, lookup_vehicle_by_plate, normalize_plate
from ..schemas import DriverIn, VehicleIn
from ..services.plans import check_vehicle_limit, check_driver_limit

# ---- Shared helpers ----


def normalize_optional(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_email(value):
    value = normalize_optional(value)
    return value.lower() if value else None


def normalize_vehicle_targa(value):
    value = normalize_optional(value)
    if not value:
        return None
    return "".join(ch for ch in value.upper() if ch.isalnum())


def ensure_vehicle_targa_unique(db: Session, user: User, targa: str | None, exclude_id: int | None = None):
    targa = normalize_optional(targa)
    if not targa:
        return
    q = owned(db.query(Vehicle), Vehicle, user).filter(Vehicle.targa == targa)
    if exclude_id is not None:
        q = q.filter(Vehicle.id != exclude_id)
    if q.first():
        raise HTTPException(400, "Esiste già un mezzo con questa targa nella tua azienda.")


def ensure_driver_email_unique(db: Session, user: User, email: str | None, exclude_id: int | None = None):
    email = normalize_email(email)
    if not email:
        return
    q = owned(db.query(Driver), Driver, user).filter(Driver.email == email)
    if exclude_id is not None:
        q = q.filter(Driver.id != exclude_id)
    if q.first():
        raise HTTPException(400, "Esiste già un autista con questa email nella tua azienda.")

def computed_route_status_simple(plan) -> str:
    """Import locale per evitare import circolare con routes.py"""
    from ..routers.routes import computed_route_status
    return computed_route_status(plan)


# ========== VEHICLES ==========

vehicles_router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def vehicle_status(vehicle, db: Session) -> str:
    """Stato del mezzo, isolato dalla sessione principale.

    In alcune installazioni aggiornate da versioni precedenti una query sulle
    route può fallire per differenze di schema. Eseguirla sulla connection
    dell'engine evita di lasciare la Session in stato aborted e quindi di far
    fallire l'intero endpoint /api/vehicles.
    """
    today = local_today()
    vehicle_id = getattr(vehicle, "id", None)
    if not vehicle_id:
        return "Disponibile"
    try:
        engine = db.get_bind()
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT status FROM route_plans WHERE vehicle_id = :vehicle_id AND data_giro = :today"),
                {"vehicle_id": vehicle_id, "today": today},
            ).fetchall()
        for row in rows:
            stored = ((row[0] if row else None) or "programmato").lower()
            if stored == "in_corso":
                return "In uso"
    except Exception as exc:
        print(f"[VEHICLES] stato mezzo {vehicle_id}: fallback Disponibile ({exc})")
    return "Disponibile"


def _vehicle_value(vehicle, name, default=None):
    try:
        value = getattr(vehicle, name, default)
    except Exception:
        return default
    return default if value is None else value


def _iso_or_none(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def vehicle_to_dict(vehicle, db: Session) -> dict:
    consumo_legacy = _vehicle_value(vehicle, "consumo_l_100km", 0) or 0
    return {
        "id": _vehicle_value(vehicle, "id"),
        "nome": _vehicle_value(vehicle, "nome", ""),
        "targa": _vehicle_value(vehicle, "targa"),
        "marca": _vehicle_value(vehicle, "marca"),
        "modello": _vehicle_value(vehicle, "modello"),
        "anno_immatricolazione": _vehicle_value(vehicle, "anno_immatricolazione"),
        "cilindrata_cc": _vehicle_value(vehicle, "cilindrata_cc"),
        "potenza_kw": _vehicle_value(vehicle, "potenza_kw"),
        "classe_euro": _vehicle_value(vehicle, "classe_euro"),
        "carrozzeria": _vehicle_value(vehicle, "carrozzeria"),
        "lookup_provider": _vehicle_value(vehicle, "lookup_provider"),
        "lookup_at": _iso_or_none(_vehicle_value(vehicle, "lookup_at")),
        "consumo_l_100km": consumo_legacy,
        "alimentazione": _vehicle_value(vehicle, "alimentazione", "gasolio") or "gasolio",
        "consumo_primario_100km": _vehicle_value(vehicle, "consumo_primario_100km", consumo_legacy) or consumo_legacy,
        "consumo_kwh_100km": _vehicle_value(vehicle, "consumo_kwh_100km", 0) or 0,
        "capacita_kg": _vehicle_value(vehicle, "capacita_kg", 0) or 0,
        "capacita_colli": _vehicle_value(vehicle, "capacita_colli", 0) or 0,
        "ha_sponda": bool(_vehicle_value(vehicle, "ha_sponda", False)),
        "accesso_ztl": bool(_vehicle_value(vehicle, "accesso_ztl", False)),
        "note": _vehicle_value(vehicle, "note"),
        "photo_url": _vehicle_value(vehicle, "photo_url"),
        "stato": vehicle_status(vehicle, db),
    }


@vehicles_router.get("/fuel-prices/current")
def current_fuel_prices(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return get_daily_prices(db)


@vehicles_router.get("/lookup-plate/{plate}")
def lookup_plate(plate: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        normalized = normalize_plate(plate)

        # Registro targa gratuito interno: se la stessa targa è già presente
        # nell'azienda, riutilizziamo i dati salvati senza chiamare servizi esterni.
        existing = (
            owned(db.query(Vehicle), Vehicle, user)
            .filter(Vehicle.targa == normalized)
            .first()
        )
        if existing:
            return {
                "targa": normalized,
                "marca": existing.marca,
                "modello": existing.modello,
                "anno_immatricolazione": existing.anno_immatricolazione,
                "alimentazione": existing.alimentazione,
                "cilindrata_cc": existing.cilindrata_cc,
                "potenza_kw": existing.potenza_kw,
                "classe_euro": existing.classe_euro,
                "carrozzeria": existing.carrozzeria,
                "provider": "girofacile",
                "manual_required": False,
                "message": "Dati recuperati dal registro targa interno di GiroFacile.",
            }

        return lookup_vehicle_by_plate(normalized)
    except VehicleLookupError as exc:
        raise HTTPException(400, str(exc)) from exc


@vehicles_router.get("")
def list_vehicles(db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        rows = owned(db.query(Vehicle), Vehicle, user).order_by(Vehicle.nome.asc()).all()
        return [vehicle_to_dict(x, db) for x in rows]
    except Exception as exc:
        # Log locale utile: l'errore resta visibile nel terminale senza
        # trasformare una singola riga legacy in un 500 opaco.
        db.rollback()
        print(f"[VEHICLES] errore caricamento lista ORM: {type(exc).__name__}: {exc}")

        # Fallback compatibile con database legacy: leggiamo le colonne
        # effettivamente presenti e restituiamo comunque il registro mezzi.
        engine = db.get_bind()
        from sqlalchemy import inspect
        columns = {c["name"] for c in inspect(engine).get_columns("vehicles")}
        clauses = []
        params = {}
        if "user_id" in columns:
            clauses.append("user_id = :uid")
            params["uid"] = user.id
        if "deleted_at" in columns:
            clauses.append("deleted_at IS NULL")
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        order_sql = " ORDER BY nome ASC" if "nome" in columns else ""
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM vehicles{where_sql}{order_sql}"), params)
            mappings = result.mappings().all()

        output = []
        for row in mappings:
            class RowVehicle:
                pass
            item = RowVehicle()
            for key, value in row.items():
                setattr(item, key, value)
            output.append(vehicle_to_dict(item, db))
        return output


@vehicles_router.post("")
def create_vehicle(data: VehicleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_vehicle_limit(user, db)
    payload = data.model_dump()
    payload["consumo_l_100km"] = payload.get("consumo_primario_100km") or payload.get("consumo_l_100km") or 0
    payload["targa"] = normalize_vehicle_targa(payload.get("targa"))
    ensure_vehicle_targa_unique(db, user, payload.get("targa"))
    if payload.get("lookup_provider"):
        payload["lookup_at"] = datetime.utcnow()
    item = Vehicle(**payload, user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@vehicles_router.put("/{item_id}")
def update_vehicle(item_id: int, data: VehicleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Vehicle), Vehicle, user).filter(Vehicle.id == item_id).first()
    if not item:
        raise HTTPException(404, "Mezzo non trovato")
    payload = data.model_dump()
    payload["consumo_l_100km"] = payload.get("consumo_primario_100km") or payload.get("consumo_l_100km") or 0
    payload["targa"] = normalize_vehicle_targa(payload.get("targa"))
    ensure_vehicle_targa_unique(db, user, payload.get("targa"), exclude_id=item.id)
    if payload.get("lookup_provider"):
        payload["lookup_at"] = datetime.utcnow()
    for k, v in payload.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@vehicles_router.delete("/{item_id}")
def delete_vehicle(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Vehicle), Vehicle, user).filter(Vehicle.id == item_id).first()
    if not item:
        raise HTTPException(404, "Mezzo non trovato")
    item.is_active = False
    item.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "archived": True}


# ========== DRIVERS ==========

drivers_router = APIRouter(prefix="/api/drivers", tags=["drivers"])


def driver_status(driver, db: Session) -> str:
    today = local_today()
    routes = db.query(RoutePlan).filter(
        RoutePlan.driver_id == driver.id, RoutePlan.data_giro == today
    ).all()
    for r in routes:
        if computed_route_status_simple(r) == "in_corso":
            return "In servizio"
    return "Disponibile"


def driver_to_dict(driver, db: Session) -> dict:
    total_routes = db.query(RoutePlan).filter(RoutePlan.driver_id == driver.id).count()
    account = db.query(DriverAccount).filter(DriverAccount.driver_id == driver.id).first()
    return {
        "id": driver.id,
        "nome": driver.nome,
        "cognome": driver.cognome,
        "telefono": driver.telefono,
        "email": driver.email,
        "patente": driver.patente,
        "scadenza_patente": driver.scadenza_patente.isoformat() if driver.scadenza_patente else None,
        "cqc": driver.cqc,
        "scadenza_cqc": driver.scadenza_cqc.isoformat() if driver.scadenza_cqc else None,
        "adr": driver.adr,
        "note": driver.note,
        "photo_url": driver.photo_url,
        "stato": driver_status(driver, db),
        "giri_assegnati": total_routes,
        "account_attivo": bool(account and account.is_active),
        "account_email": account.email if account else None,
    }


@drivers_router.get("")
def list_drivers(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = owned(db.query(Driver), Driver, user).order_by(Driver.nome.asc(), Driver.cognome.asc()).all()
    return [driver_to_dict(x, db) for x in rows]


def _driver_full_name(driver: Driver) -> str:
    return f"{driver.nome or ''} {driver.cognome or ''}".strip() or "Autista"


def _company_name(user: User) -> str:
    return (user.company_name or user.username or "GiroFacile").strip()


def _admin_name(user: User) -> str:
    return (user.username or user.company_name or "amministratore").strip()


def _normalize_driver_payload(data: DriverIn) -> dict:
    payload = data.model_dump()
    payload["email"] = (payload.get("email") or "").strip().lower() or None
    payload["telefono"] = (payload.get("telefono") or "").strip() or None
    payload["cognome"] = (payload.get("cognome") or "").strip() or None
    payload["photo_url"] = payload.get("photo_url") or None

    # Il frontend invia le date dagli <input type="date"> come stringhe
    # YYYY-MM-DD, mentre SQLAlchemy/PostgreSQL si aspettano veri oggetti date.
    # Senza questa conversione il salvataggio dell'autista può fallire al commit.
    payload["scadenza_patente"] = parse_date_value(payload.get("scadenza_patente"))
    payload["scadenza_cqc"] = parse_date_value(payload.get("scadenza_cqc"))
    return payload


def _send_driver_invite(driver: Driver, db: Session, user: User, *, is_reinvite: bool = False) -> dict:
    """Genera il link di primo accesso e prova a inviare l'email all'autista.

    Ritorna sempre anche il link: se l'SMTP non è configurato, l'admin può copiarlo
    e inviarlo manualmente su WhatsApp o email personale.
    """
    if not driver.email:
        return {
            "invite_email_sent": False,
            "invite_setup_url": None,
            "invite_portal_url": None,
            "invite_message": "Nessuna email configurata per l'autista.",
        }

    from ..core.config import APP_BASE_URL
    from ..routers.driver import create_driver_setup_token
    from ..services.email import send_driver_invitation

    base_url = APP_BASE_URL.rstrip("/")
    token = create_driver_setup_token(driver.id, db)
    setup_url = f"{base_url}/driver/setup/{token}"
    portal_url = f"{base_url}/driver"
    sent = send_driver_invitation(
        to_email=driver.email,
        driver_name=_driver_full_name(driver),
        company_name=_company_name(user),
        setup_url=setup_url,
        admin_name=_admin_name(user),
        portal_url=portal_url,
        is_reinvite=is_reinvite,
    )
    return {
        "invite_email_sent": bool(sent),
        "invite_setup_url": setup_url,
        "invite_portal_url": portal_url,
        "invite_message": "Invito inviato via email." if sent else "Email non inviata: controlla la configurazione SMTP. Usa il link di invito manuale.",
    }


@drivers_router.post("")
def create_driver(data: DriverIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_driver_limit(user, db)
    payload = _normalize_driver_payload(data)
    payload["email"] = normalize_email(payload.get("email"))
    ensure_driver_email_unique(db, user, payload.get("email"))
    item = Driver(**payload, user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)

    result = driver_to_dict(item, db)
    if item.email:
        # Il salvataggio anagrafico non deve mai essere annullato da un problema
        # secondario (SMTP/token di invito). L'autista è già stato salvato.
        try:
            result.update(_send_driver_invite(item, db, user, is_reinvite=False))
        except Exception as exc:
            result.update({
                "invite_email_sent": False,
                "invite_setup_url": None,
                "invite_portal_url": None,
                "invite_message": f"Autista creato, ma invito non disponibile: {exc}",
            })
    else:
        result.update({
            "invite_email_sent": False,
            "invite_setup_url": None,
            "invite_portal_url": None,
            "invite_message": "Autista creato senza email: l'invito non è stato inviato.",
        })
    return result


@drivers_router.put("/{item_id}")
def update_driver(item_id: int, data: DriverIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Driver), Driver, user).filter(Driver.id == item_id).first()
    if not item:
        raise HTTPException(404, "Autista non trovato")

    old_email = (item.email or "").strip().lower()
    payload = _normalize_driver_payload(data)
    payload["email"] = normalize_email(payload.get("email"))
    ensure_driver_email_unique(db, user, payload.get("email"), exclude_id=item.id)
    for k, v in payload.items():
        setattr(item, k, v)

    new_email = (item.email or "").strip().lower()
    if new_email:
        account = db.query(DriverAccount).filter(DriverAccount.driver_id == item.id).first()
        if account and account.email != new_email:
            account.email = new_email

    db.commit()
    db.refresh(item)

    result = driver_to_dict(item, db)
    if new_email and new_email != old_email:
        try:
            result.update(_send_driver_invite(item, db, user, is_reinvite=False))
        except Exception as exc:
            result.update({
                "invite_email_sent": False,
                "invite_setup_url": None,
                "invite_portal_url": None,
                "invite_message": f"Autista aggiornato, ma invito non disponibile: {exc}",
            })
    return result


@drivers_router.post("/{item_id}/invite")
def invite_driver(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Rigenera il link di primo accesso e invia l'invito all'autista."""
    item = owned(db.query(Driver), Driver, user).filter(Driver.id == item_id).first()
    if not item:
        raise HTTPException(404, "Autista non trovato")
    if not item.email:
        raise HTTPException(400, "Inserisci un'email per inviare l'invito all'autista")
    invite = _send_driver_invite(item, db, user, is_reinvite=True)
    return {
        "ok": True,
        "email_sent": invite["invite_email_sent"],
        "setup_url": invite["invite_setup_url"],
        "portal_url": invite["invite_portal_url"],
        "message": invite["invite_message"],
    }


@drivers_router.delete("/{item_id}")
def delete_driver(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Driver), Driver, user).filter(Driver.id == item_id).first()
    if not item:
        raise HTTPException(404, "Autista non trovato")
    item.is_active = False
    item.deleted_at = datetime.utcnow()
    account = db.query(DriverAccount).filter(DriverAccount.driver_id == item.id).first()
    if account:
        account.is_active = False
    db.commit()
    return {"ok": True, "archived": True}
