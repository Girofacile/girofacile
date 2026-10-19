from ..services.customer_planning import planning_customer_filters, customer_is_plannable
from datetime import datetime
from ..core.clock import utc_now
import time
from pathlib import Path
import math

from pydantic import BaseModel, Field
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.dependencies import current_user, owned
from ..core.utils import time_to_hhmm, parse_time_value
from ..database import get_db
from ..services.customer_import import read_customer_import, preflight_customer_import, customer_address_key, invalidate_imported_address, unload_minutes
from ..models import Agent, Customer, User
from ..routers.agents import agent_full_name
from ..schemas import CustomerIn
from ..services.geocoding import apply_geocode, geocode_customer, geocode_address, GeocodingUnavailable
from ..services.ztl import customer_ztl
from ..services import distance_cache as dc
from ..services.plans import check_customer_limit
from ..services.agents_feature import agents_enabled

router = APIRouter(prefix="/api/customers", tags=["customers"])

def normalize_customer_times(customer):
    customer.scarico_mattina_da = parse_time_value(customer.scarico_mattina_da)
    customer.scarico_mattina_a = parse_time_value(customer.scarico_mattina_a)
    customer.scarico_pomeriggio_da = parse_time_value(customer.scarico_pomeriggio_da)
    customer.scarico_pomeriggio_a = parse_time_value(customer.scarico_pomeriggio_a)
    return customer



def normalize_optional(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def ensure_customer_code_unique(db: Session, user: User, codice: str | None, exclude_id: int | None = None):
    codice = normalize_optional(codice)
    if not codice:
        return
    q = owned(db.query(Customer), Customer, user).filter(Customer.codice_cliente == codice)
    if exclude_id is not None:
        q = q.filter(Customer.id != exclude_id)
    if q.first():
        raise HTTPException(400, "Esiste già un cliente con questo codice cliente nella tua azienda.")


def customer_to_dict(customer) -> dict:
    return {
        "id": customer.id,
        "user_id": customer.user_id,
        "agent_id": customer.agent_id,
        "agent_name": agent_full_name(customer.agent) if customer.agent else "Cliente interno",
        "codice_cliente": customer.codice_cliente,
        "nome": customer.nome,
        "indirizzo": customer.indirizzo,
        "comune": customer.comune,
        "provincia": customer.provincia,
        "telefono": customer.telefono,
        "referente": customer.referente,
        "email": customer.email,
        "scarico_mattina_da": time_to_hhmm(customer.scarico_mattina_da),
        "scarico_mattina_a": time_to_hhmm(customer.scarico_mattina_a),
        "scarico_pomeriggio_da": time_to_hhmm(customer.scarico_pomeriggio_da),
        "scarico_pomeriggio_a": time_to_hhmm(customer.scarico_pomeriggio_a),
        "tempo_scarico_min": customer.tempo_scarico_min,
        "ztl": customer.ztl,
        **customer_ztl(customer),
        "sponda": customer.sponda,
        "transpallet": customer.transpallet,
        "note": customer.note,
        "lat": customer.lat,
        "lon": customer.lon,
        "indirizzo_geocodificato": customer.indirizzo_geocodificato,
        "stato_geocodifica": customer.stato_geocodifica or "da_verificare",
        "affidabilita_geocodifica": customer.affidabilita_geocodifica,
        "fonte_geocodifica": customer.fonte_geocodifica,
        "google_place_id": customer.google_place_id,
        "geocodificato_il": customer.geocodificato_il.isoformat() if customer.geocodificato_il else None,
    }


def safe_geocode_customer(customer):
    """Geocodifica senza bloccare il salvataggio del cliente se il provider non risponde."""
    try:
        result = geocode_customer(customer)
        apply_geocode(customer, result)
        return result
    except Exception as exc:
        customer.stato_geocodifica = customer.stato_geocodifica or "da_verificare"
        return {"status": "errore", "message": str(exc)}


@router.get("")
def list_customers(
    q: str = "", provincia: str = "", comune: str = "",
    ztl: str = "", sponda: str = "", agent_id: str = "",
    limit: int = 300, offset: int = 0, planning_only: bool = False,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    query = owned(db.query(Customer), Customer, user)
    if planning_only:
        query = query.filter(*planning_customer_filters())
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Customer.nome.ilike(like), Customer.codice_cliente.ilike(like),
            Customer.indirizzo.ilike(like), Customer.comune.ilike(like),
        ))
    if provincia:
        query = query.filter(Customer.provincia.ilike(f"%{provincia}%"))
    if comune:
        query = query.filter(Customer.comune.ilike(f"%{comune}%"))
    if not agents_enabled(user):
        agent_id = ""
    if agent_id == "interno":
        query = query.filter(Customer.agent_id.is_(None))
    elif agent_id:
        try:
            query = query.filter(Customer.agent_id == int(agent_id))
        except Exception:
            pass
    if sponda in ["true", "false"]:
        query = query.filter(Customer.sponda == (sponda == "true"))
    query = query.order_by(Customer.nome.asc(), Customer.id.asc())
    if ztl in ["true", "false"]:
        # Il segnale automatico e' derivato dalle coordinate, non dal campo manuale DB.
        all_rows = query.all()
        filtered = [row for row in all_rows if customer_ztl(row)["ztl"] == (ztl == "true")]
        rows = filtered[max(0, offset):max(0, offset) + max(10, min(limit, 1000))]
    else:
        rows = query.offset(max(0, offset)).limit(max(10, min(limit, 1000))).all()
    return [customer_to_dict(x) for x in rows]


@router.post("")
def create_customer(data: CustomerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    check_customer_limit(user, db)
    payload = data.model_dump()
    if not agents_enabled(user):
        payload.pop("agent_id", None)
    payload["codice_cliente"] = normalize_optional(payload.get("codice_cliente"))
    ensure_customer_code_unique(db, user, payload.get("codice_cliente"))
    if payload.get("agent_id"):
        agent = owned(db.query(Agent), Agent, user).filter(Agent.id == payload["agent_id"]).first()
        if not agent:
            raise HTTPException(400, "Agente non trovato")
    # La geocodifica non parte più automaticamente al salvataggio.
    # Le coordinate vengono salvate solo se l'utente ha premuto
    # "Verifica indirizzo con Google" nel pop-up cliente.
    payload["stato_geocodifica"] = payload.get("stato_geocodifica") or "da_verificare"
    item = Customer(**payload, user_id=user.id)
    db.add(item)
    normalize_customer_times(item)
    db.commit()
    db.refresh(item)
    return customer_to_dict(item)


@router.put("/{item_id}")
def update_customer(item_id: int, data: CustomerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Customer), Customer, user).filter(Customer.id == item_id).first()
    if not item:
        raise HTTPException(404, "Cliente non trovato")
    old_coordinates = (item.lat, item.lon)
    old_key = "|".join([item.indirizzo or "", item.comune or "", item.provincia or ""]).strip().lower()
    payload = data.model_dump()
    if not agents_enabled(user):
        payload.pop("agent_id", None)
    payload["codice_cliente"] = normalize_optional(payload.get("codice_cliente"))
    ensure_customer_code_unique(db, user, payload.get("codice_cliente"), exclude_id=item.id)
    if payload.get("agent_id"):
        agent = owned(db.query(Agent), Agent, user).filter(Agent.id == payload["agent_id"]).first()
        if not agent:
            raise HTTPException(400, "Agente non trovato")
    new_key = "|".join([
        payload.get("indirizzo") or "", payload.get("comune") or "", payload.get("provincia") or ""
    ]).strip().lower()
    payload["stato_geocodifica"] = payload.get("stato_geocodifica") or (
        "da_verificare" if old_key != new_key or old_coordinates != (payload.get("lat"), payload.get("lon"))
        else item.stato_geocodifica or "da_verificare")
    for k, v in payload.items():
        setattr(item, k, v)
    if old_key != new_key and (payload.get("lat") is None or payload.get("lon") is None):
        # Se l'indirizzo è stato cambiato senza verifica Google, azzeriamo le coordinate.
        # Non geocodifichiamo automaticamente per evitare chiamate Google mentre si salva.
        item.lat = None
        item.lon = None
        item.indirizzo_geocodificato = None
        item.stato_geocodifica = "da_verificare"
        item.affidabilita_geocodifica = None
        item.fonte_geocodifica = None
        item.google_place_id = None
        item.geocodificato_il = None
    normalize_customer_times(item)
    if old_key != new_key or old_coordinates != (item.lat, item.lon):
        dc.invalidate_key(db, dc.customer_key(item.id, user_id=user.id), user_id=user.id)
    db.commit()
    db.refresh(item)
    return customer_to_dict(item)


@router.delete("/{item_id}")
def delete_customer(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Customer), Customer, user).filter(Customer.id == item_id).first()
    if not item:
        raise HTTPException(404, "Cliente non trovato")
    item.is_active = False
    item.deleted_at = utc_now()
    db.commit()
    dc.invalidate_key(db, dc.customer_key(item_id, user_id=user.id), user_id=user.id)
    return {"ok": True, "archived": True}


@router.post("/verify-address-preview")
def verify_customer_address_preview(data: CustomerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Verifica un indirizzo con Google prima del salvataggio cliente.

    Non crea e non modifica record nel database: serve al pop-up cliente per
    mostrare l'indirizzo corretto, latitudine e longitudine prima di salvare.
    """
    payload = data.model_dump()
    if not agents_enabled(user):
        payload.pop("agent_id", None)

    # I campi Time nel modello SQLAlchemy richiedono oggetti datetime.time,
    # non stringhe tipo "08:00". Convertiamo prima di creare Customer temporaneo.
    for _field in (
        "scarico_mattina_da",
        "scarico_mattina_a",
        "scarico_pomeriggio_da",
        "scarico_pomeriggio_a",
    ):
        payload[_field] = parse_time_value(payload.get(_field))

    temp = Customer(**payload, user_id=user.id)
    result = geocode_customer(temp, db=db)
    return {
        "result": result,
        "suggested": {
            "indirizzo": result.get("formatted") or payload.get("indirizzo"),
            "lat": result.get("lat"),
            "lon": result.get("lon"),
            "stato_geocodifica": result.get("status", "non_trovato"),
            "affidabilita_geocodifica": result.get("confidence"),
            "fonte_geocodifica": result.get("source"),
            "google_place_id": result.get("place_id"),
        },
    }



class SelectedCustomerVerification(BaseModel):
    customer_ids: list[int] = Field(min_length=1, max_length=3)


class SelectedCustomerResolution(BaseModel):
    customer_id: int
    action: Literal["correct", "manual"]
    original_address: str
    original_comune: str = ""
    address: str = Field(min_length=1, max_length=500)
    comune: str = Field(min_length=1, max_length=200)
    provincia: str | None = Field(default=None, max_length=100)
    lat: float | None = None
    lon: float | None = None


def selected_customer_issue(customer, message, kind="address", candidate=None):
    return {
        "id": customer.id, "recipient_name": customer.nome,
        "address": customer.indirizzo or "", "comune": customer.comune or "",
        "provincia": customer.provincia or "", "message": message,
        "kind": kind, "candidate": candidate,
    }


@router.post("/verify-selected")
def verify_selected_customer_addresses(
    data: SelectedCustomerVerification,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Verifica solo i clienti selezionati, a piccoli lotti come gli ordini.

    Nessun controllo su indirizzi gia' confermati e nessun blocco del giro
    finche' non si apre l'editor per i soli indirizzi problematici.
    """
    ids = list(dict.fromkeys(data.customer_ids))
    customers = owned(db.query(Customer), Customer, user).filter(Customer.id.in_(ids)).all()
    by_id = {customer.id: customer for customer in customers}
    if len(by_id) != len(ids):
        raise HTTPException(404, "Uno o piu' clienti selezionati non sono disponibili.")
    issues = []
    aborted = False
    for cid in ids:
        customer = by_id[cid]
        if customer_is_plannable(customer):
            continue
        if not (customer.indirizzo or "").strip():
            issues.append(selected_customer_issue(customer, "Completa l'indirizzo del cliente."))
            continue
        try:
            result = geocode_address(
                customer.indirizzo, customer.comune or "", customer.provincia or "",
                db=db, user_id=user.id, strict=True,
            )
        except GeocodingUnavailable as exc:
            # Interrompi il lotto per non ripetere chiamate a pagamento in caso di guasto.
            issues.extend(selected_customer_issue(by_id[rest], str(exc), "service")
                          for rest in ids[ids.index(cid):] if not customer_is_plannable(by_id[rest]))
            aborted = True
            break
        apply_geocode(customer, result)
        dc.invalidate_key(db, dc.customer_key(cid, user_id=user.id), user_id=user.id)
        if not customer_is_plannable(customer):
            candidate = ({"lat": customer.lat, "lon": customer.lon}
                         if customer.lat is not None and customer.lon is not None else None)
            message = ("Google ha trovato una posizione da confermare sulla mappa."
                       if candidate else "Indirizzo non trovato. Correggilo o scegli la posizione sulla mappa.")
            issues.append(selected_customer_issue(customer, message, candidate=candidate))
    db.commit()
    return {"issues": issues, "aborted": aborted}


@router.post("/resolve-selected-address")
def resolve_selected_customer_address(
    data: SelectedCustomerResolution,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    """Correzione mirata del cliente, senza modificare fascia, note o altri campi."""
    customer = owned(db.query(Customer), Customer, user).filter(Customer.id == data.customer_id).first()
    if customer is None:
        raise HTTPException(404, "Cliente non trovato")
    if (customer.indirizzo or "") != data.original_address or (customer.comune or "") != data.original_comune:
        raise HTTPException(409, "L'indirizzo e' stato modificato. Ricarica la selezione.")
    address, city = data.address.strip(), data.comune.strip()
    if not address or not city:
        raise HTTPException(422, "Inserisci indirizzo e comune.")
    if data.action == "manual":
        if data.lat is None or data.lon is None or not all((
            math.isfinite(data.lat), math.isfinite(data.lon),
            -90 <= data.lat <= 90, -180 <= data.lon <= 180,
        )):
            raise HTTPException(422, "Scegli una posizione valida sulla mappa.")
    customer.indirizzo = address
    customer.comune = city
    customer.provincia = (data.provincia or "").strip() or None
    if data.action == "correct":
        apply_geocode(customer, {"status": "da_verificare"})
    else:
        apply_geocode(customer, {
            "status": "verificato", "lat": data.lat, "lon": data.lon,
            "formatted": ", ".join(x for x in [address, city, customer.provincia] if x),
            "source": "manuale", "confidence": None, "place_id": None,
        })
    dc.invalidate_key(db, dc.customer_key(customer.id, user_id=user.id), user_id=user.id)
    db.commit()
    db.refresh(customer)
    return {"customer": customer_to_dict(customer)}


@router.post("/{item_id}/verify-address")
def verify_customer_address(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned(db.query(Customer), Customer, user).filter(Customer.id == item_id).first()
    if not item:
        raise HTTPException(404, "Cliente non trovato")
    result = geocode_customer(item, db=db)
    apply_geocode(item, result)
    db.commit()
    db.refresh(item)
    # Le coordinate potrebbero essere cambiate: invalidiamo la cache relativa.
    dc.invalidate_key(db, dc.customer_key(item.id, user_id=user.id), user_id=user.id)
    return {"customer": customer_to_dict(item), "result": result}


@router.post("/verify-pending")
def verify_pending_addresses(
    limit: int = 60,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    rows = (
        owned(db.query(Customer), Customer, user)
        .filter(or_(Customer.stato_geocodifica.is_(None), Customer.stato_geocodifica != "verificato"))
        .limit(max(1, min(limit, 100)))
        .all()
    )
    stats = {"verificato": 0, "da_verificare": 0, "non_trovato": 0}
    for item in rows:
        result = geocode_customer(item, db=db)
        apply_geocode(item, result)
        stats[result.get("status", "non_trovato")] = stats.get(result.get("status", "non_trovato"), 0) + 1
        db.commit()
        dc.invalidate_key(db, dc.customer_key(item.id, user_id=user.id), user_id=user.id)
        time.sleep(0.15)
    return {"processed": len(rows), **stats}


@router.post("/import")
async def import_customers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    df = await read_customer_import(file)
    preflight_customer_import(df, db, user)
    created, updated = 0, 0

    def get(row, col, default=None):
        if col not in row or pd.isna(row[col]):
            return default
        return row[col]

    def b(x):
        return str(x).strip().lower() in ["1", "si", "sì", "yes", "true", "vero"]

    agents = owned(db.query(Agent), Agent, user).all() if agents_enabled(user) else []
    agent_lookup_by_code = {str(a.codice_agente or "").strip().lower(): a.id for a in agents if a.codice_agente}
    agent_lookup_by_name = {agent_full_name(a).strip().lower(): a.id for a in agents}

    for _, row in df.iterrows():
        codice = str(get(row, "codice_cliente", "") or "").strip()
        nome = str(get(row, "nome", "") or "").strip()
        indirizzo = str(get(row, "indirizzo", "") or "").strip()
        if not nome or not indirizzo:
            continue
        item = (
            owned(db.query(Customer), Customer, user).filter(Customer.codice_cliente == codice).first()
            if codice else None
        )
        if not item:
            item = Customer(user_id=user.id)
            db.add(item)
            created += 1
        else:
            updated += 1
        previous_address = customer_address_key(item)
        item.codice_cliente = codice or None
        item.nome = nome
        item.indirizzo = indirizzo
        codice_agente = str(get(row, "codice_agente", "") or "").strip().lower()
        agente_nome = str(get(row, "agente", "") or "").strip().lower()
        if agents_enabled(user):
            item.agent_id = agent_lookup_by_code.get(codice_agente) or agent_lookup_by_name.get(agente_nome) or None
        item.comune = get(row, "comune")
        item.provincia = get(row, "provincia")
        item.telefono = str(get(row, "telefono", "") or "")
        item.referente = get(row, "referente")
        item.email = get(row, "email")
        item.scarico_mattina_da = parse_time_value(get(row, "scarico_mattina_da"))
        item.scarico_mattina_a = parse_time_value(get(row, "scarico_mattina_a"))
        item.scarico_pomeriggio_da = parse_time_value(get(row, "scarico_pomeriggio_da"))
        item.scarico_pomeriggio_a = parse_time_value(get(row, "scarico_pomeriggio_a"))
        item.tempo_scarico_min = unload_minutes(get(row, "tempo_scarico_min"))
        item.ztl = b(get(row, "ztl", False))
        item.sponda = b(get(row, "sponda", False))
        item.transpallet = b(get(row, "transpallet", False))
        item.note = get(row, "note")
        invalidate_imported_address(db, item, previous_address)
    db.commit()
    return {"created": created, "updated": updated}
