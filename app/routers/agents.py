import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.dependencies import current_user, owned
from ..database import get_db
from ..core.config import APP_BASE_URL
from ..models import Agent, AgentAccount, AgentSetupToken, Customer, User
from ..schemas import AgentIn
from ..services.plans import require_feature
from ..services.email import send_agent_invitation

router = APIRouter(prefix="/api/agents", tags=["agents"])


def normalize_optional(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_email(value):
    value = normalize_optional(value)
    return value.lower() if value else None


def ensure_agent_unique_fields(db: Session, user: User, email: str | None = None, codice_agente: str | None = None, exclude_id: int | None = None):
    email = normalize_email(email)
    codice_agente = normalize_optional(codice_agente)
    if email:
        q = owned(db.query(Agent), Agent, user).filter(Agent.email == email)
        if exclude_id is not None:
            q = q.filter(Agent.id != exclude_id)
        if q.first():
            raise HTTPException(400, "Esiste già un agente con questa email nella tua azienda.")
    if codice_agente:
        q = owned(db.query(Agent), Agent, user).filter(Agent.codice_agente == codice_agente)
        if exclude_id is not None:
            q = q.filter(Agent.id != exclude_id)
        if q.first():
            raise HTTPException(400, "Esiste già un agente con questo codice nella tua azienda.")


def agent_full_name(agent) -> str:
    if not agent:
        return "Cliente interno"
    return ((agent.nome or "") + (" " + agent.cognome if agent.cognome else "")).strip() or "Agente"


def agent_to_dict(agent, db: Session | None = None, user: User | None = None) -> dict:
    customer_count = 0
    if db is not None:
        q = db.query(Customer).filter(Customer.agent_id == agent.id, Customer.deleted_at.is_(None))
        if user is not None:
            q = owned(q, Customer, user)
        customer_count = q.count()
    return {
        "id": agent.id,
        "codice_agente": agent.codice_agente,
        "nome": agent.nome,
        "cognome": agent.cognome,
        "full_name": agent_full_name(agent),
        "telefono": agent.telefono,
        "email": agent.email,
        "zona": agent.zona,
        "attivo": agent.attivo,
        "note": agent.note,
        "photo_url": agent.photo_url,
        "clienti_assegnati": customer_count,
        "account_attivo": bool(db.query(AgentAccount).filter(AgentAccount.agent_id == agent.id, AgentAccount.is_active == True).first()) if db is not None else False,
    }


def _create_agent_invite(agent: Agent, db: Session, user: User, is_reinvite: bool = False) -> dict:
    if not agent.email:
        return {"email_sent": False, "invite_setup_url": None, "message": "Email agente assente"}
    token = secrets.token_urlsafe(32)
    st = AgentSetupToken(
        agent_id=agent.id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=7),
        used_at=None,
    )
    db.add(st)
    db.commit()
    setup_url = f"{APP_BASE_URL}/agent/setup/{token}"
    portal_url = f"{APP_BASE_URL}/agent"
    sent = False
    try:
        sent = send_agent_invitation(
            to_email=agent.email.strip().lower(),
            agent_name=agent_full_name(agent),
            company_name=user.company_name or user.username or "Azienda",
            setup_url=setup_url,
            admin_name=user.company_name or user.username,
            portal_url=portal_url,
            is_reinvite=is_reinvite,
        )
    except Exception as exc:
        print(f"[AGENT_INVITE] Errore invito agente {agent.email}: {exc}")
    return {"email_sent": bool(sent), "invite_setup_url": setup_url, "portal_url": portal_url}


@router.get("")
def list_agents(
    q: str = "", stato: str = "",
    db: Session = Depends(get_db), user: User = Depends(current_user)
):
    require_feature(user, "has_agents")
    query = owned(db.query(Agent), Agent, user)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Agent.nome.ilike(like), Agent.cognome.ilike(like),
            Agent.codice_agente.ilike(like), Agent.email.ilike(like),
            Agent.telefono.ilike(like), Agent.zona.ilike(like),
        ))
    if stato == "attivi":
        query = query.filter(Agent.attivo == True)
    if stato == "non_attivi":
        query = query.filter(Agent.attivo == False)
    rows = query.order_by(Agent.nome.asc(), Agent.cognome.asc()).all()
    return [agent_to_dict(x, db, user) for x in rows]


@router.post("")
def create_agent(data: AgentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_agents")
    payload = data.model_dump()
    payload["nome"] = (payload.get("nome") or "").strip() or "Agente"
    payload["email"] = normalize_email(payload.get("email"))
    payload["codice_agente"] = normalize_optional(payload.get("codice_agente"))
    ensure_agent_unique_fields(db, user, email=payload.get("email"), codice_agente=payload.get("codice_agente"))
    item = Agent(**payload, user_id=user.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    out = agent_to_dict(item, db, user)
    if item.email:
        out["invite"] = _create_agent_invite(item, db, user, is_reinvite=False)
    return out


@router.put("/{item_id}")
def update_agent(item_id: int, data: AgentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_agents")
    item = owned(db.query(Agent), Agent, user).filter(Agent.id == item_id).first()
    if not item:
        raise HTTPException(404, "Agente non trovato")
    old_email = (item.email or "").strip().lower()
    payload = data.model_dump()
    payload["nome"] = (payload.get("nome") or "").strip() or "Agente"
    payload["email"] = normalize_email(payload.get("email"))
    payload["codice_agente"] = normalize_optional(payload.get("codice_agente"))
    ensure_agent_unique_fields(db, user, email=payload.get("email"), codice_agente=payload.get("codice_agente"), exclude_id=item.id)
    for k, v in payload.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    out = agent_to_dict(item, db, user)
    new_email = (item.email or "").strip().lower()
    has_account = db.query(AgentAccount).filter(AgentAccount.agent_id == item.id).first()
    if new_email and (new_email != old_email or not has_account):
        out["invite"] = _create_agent_invite(item, db, user, is_reinvite=bool(has_account))
    return out


@router.post("/{item_id}/invite")
def invite_agent(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_agents")
    item = owned(db.query(Agent), Agent, user).filter(Agent.id == item_id).first()
    if not item:
        raise HTTPException(404, "Agente non trovato")
    if not item.email:
        raise HTTPException(400, "L'agente non ha una email configurata")
    has_account = db.query(AgentAccount).filter(AgentAccount.agent_id == item.id).first()
    return {"ok": True, **_create_agent_invite(item, db, user, is_reinvite=bool(has_account))}


@router.delete("/{item_id}")
def delete_agent(item_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_feature(user, "has_agents")
    item = owned(db.query(Agent), Agent, user).filter(Agent.id == item_id).first()
    if not item:
        raise HTTPException(404, "Agente non trovato")
    item.attivo = False
    item.is_active = False
    item.deleted_at = datetime.utcnow()
    account = db.query(AgentAccount).filter(AgentAccount.agent_id == item.id).first()
    if account:
        account.is_active = False
    # I clienti restano collegati all'agente per mantenere lo storico commerciale.
    db.commit()
    return {"ok": True, "archived": True}
