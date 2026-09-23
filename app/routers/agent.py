"""Portale agente — login separato e gestione clienti associati all'agente."""
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Cookie, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.config import APP_BASE_URL
from ..core.http_security import cookie_options
from ..core.security import hash_password as secure_hash_password, password_needs_rehash, validate_password_strength, verify_password
from ..core.utils import time_to_hhmm, parse_time_value
from ..database import get_db
from ..services.customer_import import read_customer_import, preflight_customer_import
from ..models import Agent, AgentAccount, AgentSetupToken, Customer, User
from ..schemas import CustomerIn
from ..services.geocoding import geocode_customer
from ..routers.customers import customer_to_dict
from ..services.agents_feature import require_agents_enabled
from ..services.plans import check_customer_limit

router = APIRouter(prefix="/api/agent", tags=["agent"])


def hash_password(password: str) -> str:
    # v70: nuovo hash professionale. La verifica resta retrocompatibile
    # tramite verify_password per gli account SHA-256 già presenti.
    return secure_hash_password(password)


def agent_full_name(agent: Agent | None) -> str:
    if not agent:
        return "Agente"
    return ((agent.nome or "") + (" " + agent.cognome if agent.cognome else "")).strip() or "Agente"


def make_session_token(account: AgentAccount) -> str:
    token_hash = hashlib.sha256(f"agent-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    return f"{account.id}:{token_hash}"


def get_current_agent(
    agent_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> AgentAccount:
    if not agent_session:
        raise HTTPException(401, "Non autenticato")
    try:
        raw_id, token_hash = agent_session.split(":", 1)
        account_id = int(raw_id)
    except Exception:
        raise HTTPException(401, "Sessione non valida")
    account = db.get(AgentAccount, account_id)
    if not account or not account.is_active:
        raise HTTPException(401, "Account agente non trovato")
    expected = hashlib.sha256(f"agent-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    if token_hash != expected:
        raise HTTPException(401, "Sessione scaduta")
    return account


def ensure_agent_owner(account: AgentAccount, db: Session) -> tuple[Agent, User]:
    agent = db.get(Agent, account.agent_id)
    if not agent or not agent.user_id:
        raise HTTPException(404, "Agente non trovato")
    user = db.get(User, agent.user_id)
    if not user:
        raise HTTPException(404, "Azienda non trovata")
    require_agents_enabled(user)
    return agent, user


@router.get("/setup/{token}")
def get_setup_info(token: str, db: Session = Depends(get_db)):
    st = db.query(AgentSetupToken).filter(AgentSetupToken.token == token).first()
    if not st:
        raise HTTPException(404, "Link non valido o scaduto")
    if st.used_at:
        raise HTTPException(409, "Questo link è già stato utilizzato. Accedi con le tue credenziali.")
    if datetime.utcnow() > st.expires_at:
        raise HTTPException(410, "Link scaduto. Contatta l'amministratore per riceverne uno nuovo.")
    agent = db.get(Agent, st.agent_id)
    if not agent:
        raise HTTPException(404, "Agente non trovato")
    company = db.get(User, agent.user_id) if agent.user_id else None
    require_agents_enabled(company)
    return {
        "agent_name": agent_full_name(agent),
        "email": agent.email,
        "company_name": company.company_name if company else None,
        "token_valid": True,
    }


@router.post("/setup/{token}")
def complete_setup(token: str, payload: dict, response: Response, db: Session = Depends(get_db)):
    st = db.query(AgentSetupToken).filter(AgentSetupToken.token == token).first()
    if not st:
        raise HTTPException(404, "Link non valido")
    if st.used_at:
        raise HTTPException(409, "Link già utilizzato")
    if datetime.utcnow() > st.expires_at:
        raise HTTPException(410, "Link scaduto")
    password = (payload.get("password") or "").strip()
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    agent = db.get(Agent, st.agent_id)
    if not agent or not agent.email:
        raise HTTPException(400, "Email agente non configurata")
    require_agents_enabled(db.get(User, agent.user_id))
    email = agent.email.strip().lower()
    existing = db.query(AgentAccount).filter(AgentAccount.agent_id == agent.id).first()
    if existing:
        existing.email = email
        existing.password_hash = hash_password(password)
        existing.is_active = True
        account = existing
    else:
        account = AgentAccount(agent_id=agent.id, email=email, password_hash=hash_password(password), is_active=True)
        db.add(account)
    st.used_at = datetime.utcnow()
    db.commit()
    db.refresh(account)
    response.set_cookie("agent_session", make_session_token(account), **cookie_options(60*60*24*30))
    return {"ok": True, "agent_name": agent_full_name(agent), "email": email}


@router.post("/login")
def agent_login(payload: dict, response: Response, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    password = (payload.get("password") or "").strip()
    account = db.query(AgentAccount).filter(func.lower(AgentAccount.email) == email).first()
    if not account or not verify_password(password, account.password_hash):
        raise HTTPException(401, "Email o password non corretti")
    if not account.is_active:
        raise HTTPException(403, "Account disabilitato")
    agent, user = ensure_agent_owner(account, db)
    if password_needs_rehash(account.password_hash):
        account.password_hash = hash_password(password)
    account.last_login = datetime.utcnow()
    db.commit()
    response.set_cookie("agent_session", make_session_token(account), **cookie_options(60*60*24*30))
    return {"ok": True, "agent_id": agent.id, "agent_name": agent_full_name(agent), "email": account.email, "company_name": user.company_name}


@router.post("/logout")
def agent_logout(response: Response):
    response.delete_cookie("agent_session")
    return {"ok": True}


@router.get("/me")
def agent_me(account: AgentAccount = Depends(get_current_agent), db: Session = Depends(get_db)):
    agent, user = ensure_agent_owner(account, db)
    return {
        "authenticated": True,
        "agent_id": agent.id,
        "agent_name": agent_full_name(agent),
        "email": account.email,
        "telefono": agent.telefono,
        "zona": agent.zona,
        "company_name": user.company_name,
    }


@router.get("/customers")
def list_agent_customers(q: str = "", db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, _ = ensure_agent_owner(account, db)
    query = db.query(Customer).filter(Customer.user_id == agent.user_id, Customer.agent_id == agent.id, Customer.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Customer.nome.ilike(like)) |
            (Customer.codice_cliente.ilike(like)) |
            (Customer.indirizzo.ilike(like)) |
            (Customer.comune.ilike(like))
        )
    rows = query.order_by(Customer.nome.asc()).limit(500).all()
    return [customer_to_dict(c) for c in rows]


@router.post("/customers")
def create_agent_customer(data: CustomerIn, db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, user = ensure_agent_owner(account, db)
    check_customer_limit(user, db)
    payload = data.model_dump()
    for _f in ["scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a"]:
        payload[_f] = parse_time_value(payload.get(_f))
    payload["agent_id"] = agent.id
    payload["stato_geocodifica"] = payload.get("stato_geocodifica") or "da_verificare"
    item = Customer(**payload, user_id=agent.user_id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return customer_to_dict(item)


@router.put("/customers/{customer_id}")
def update_agent_customer(customer_id: int, data: CustomerIn, db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, _ = ensure_agent_owner(account, db)
    item = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == agent.user_id, Customer.agent_id == agent.id, Customer.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(404, "Cliente non trovato")
    old_key = "|".join([item.indirizzo or "", item.comune or "", item.provincia or ""]).strip().lower()
    payload = data.model_dump()
    for _f in ["scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a"]:
        payload[_f] = parse_time_value(payload.get(_f))
    payload["agent_id"] = agent.id
    new_key = "|".join([payload.get("indirizzo") or "", payload.get("comune") or "", payload.get("provincia") or ""]).strip().lower()
    for k, v in payload.items():
        setattr(item, k, v)
    if old_key != new_key and (payload.get("lat") is None or payload.get("lon") is None):
        item.lat = None
        item.lon = None
        item.indirizzo_geocodificato = None
        item.stato_geocodifica = "da_verificare"
        item.affidabilita_geocodifica = None
        item.fonte_geocodifica = None
        item.google_place_id = None
        item.geocodificato_il = None
    db.commit()
    db.refresh(item)
    return customer_to_dict(item)


@router.delete("/customers/{customer_id}")
def delete_agent_customer(customer_id: int, db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, _ = ensure_agent_owner(account, db)
    item = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == agent.user_id, Customer.agent_id == agent.id, Customer.deleted_at.is_(None)).first()
    if not item:
        raise HTTPException(404, "Cliente non trovato")
    item.is_active = False
    item.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "archived": True}


@router.post("/customers/verify-address-preview")
def verify_agent_customer_address_preview(data: CustomerIn, db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, _ = ensure_agent_owner(account, db)
    payload = data.model_dump()
    for _f in ["scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a"]:
        payload[_f] = parse_time_value(payload.get(_f))
    temp = Customer(**payload, user_id=agent.user_id, agent_id=agent.id)
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


@router.post("/customers/import")
async def import_agent_customers(file: UploadFile = File(...), db: Session = Depends(get_db), account: AgentAccount = Depends(get_current_agent)):
    agent, user = ensure_agent_owner(account, db)
    df = await read_customer_import(file)
    preflight_customer_import(df, db, user, agent_id=agent.id)
    created, updated = 0, 0

    def get(row, col, default=None):
        if col not in row or pd.isna(row[col]):
            return default
        return row[col]

    def b(x):
        return str(x).strip().lower() in ["1", "si", "sì", "yes", "true", "vero"]

    for _, row in df.iterrows():
        codice = str(get(row, "codice_cliente", "") or "").strip()
        nome = str(get(row, "nome", "") or "").strip()
        indirizzo = str(get(row, "indirizzo", "") or "").strip()
        if not nome or not indirizzo:
            continue
        item = db.query(Customer).filter(Customer.user_id == agent.user_id, Customer.agent_id == agent.id, Customer.codice_cliente == codice, Customer.deleted_at.is_(None)).first() if codice else None
        if not item:
            item = Customer(user_id=agent.user_id, agent_id=agent.id)
            db.add(item)
            created += 1
        else:
            updated += 1
        item.codice_cliente = codice or item.codice_cliente
        item.nome = nome
        item.indirizzo = indirizzo
        item.comune = str(get(row, "comune", "") or "")
        item.provincia = str(get(row, "provincia", "") or "")
        item.telefono = str(get(row, "telefono", "") or "")
        item.referente = str(get(row, "referente", "") or "")
        item.email = str(get(row, "email", "") or "")
        item.scarico_mattina_da = parse_time_value(get(row, "scarico_mattina_da", ""))
        item.scarico_mattina_a = parse_time_value(get(row, "scarico_mattina_a", ""))
        item.scarico_pomeriggio_da = parse_time_value(get(row, "scarico_pomeriggio_da", ""))
        item.scarico_pomeriggio_a = parse_time_value(get(row, "scarico_pomeriggio_a", ""))
        try:
            item.tempo_scarico_min = int(get(row, "tempo_scarico_min", item.tempo_scarico_min or 10) or 10)
        except Exception:
            item.tempo_scarico_min = item.tempo_scarico_min or 10
        item.ztl = b(get(row, "ztl", False))
        item.sponda = b(get(row, "sponda", False))
        item.transpallet = b(get(row, "transpallet", False))
        item.note = str(get(row, "note", "") or "")
        item.stato_geocodifica = item.stato_geocodifica or "da_verificare"
    db.commit()
    return {"ok": True, "created": created, "updated": updated}
