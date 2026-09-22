from datetime import datetime, timedelta
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..core.config import APP_BASE_URL, APP_USER, SUPERADMIN_USERNAME, SUPERADMIN_PASSWORD, TRIAL_DAYS
from ..core.http_security import cookie_options
from ..core.dependencies import current_user, is_admin_user
from ..core.security import hash_password, make_token, make_superadmin_token, make_superadmin_collaborator_token, password_needs_rehash, validate_password_strength, verify_password, verify_token, verify_superadmin_token
from ..database import get_db
from ..models import Agent, AgentAccount, Customer, Deposit, Driver, DriverAccount, PasswordResetToken, RoutePlan, User, Vehicle, SuperAdminCollaborator
from ..schemas import SignupIn
from ..services.plans import user_plan_info
from ..services.agents_feature import require_agents_enabled
from ..services.sector_config import get_sector_config, normalize_sector_key, public_sector_options

router = APIRouter()


def _workspace_operational_for_user(user: User) -> bool:
    """v50: i settori già verticalizzati hanno dashboard operativa attiva.

    Distribuzione/Cash & Carry mantiene la dashboard storica completa.
    Logistica/Corrieri locali viene attivata con la nuova interfaccia v50.
    Gli altri settori restano nella dashboard pulita finché non vengono cuciti su misura.
    """
    # v89: un unico prodotto per tutte le aziende che effettuano consegne.
    return True



@router.post("/api/signup")
def signup(data: SignupIn, response: Response, db: Session = Depends(get_db)):
    username = (data.username or "").strip()
    password = data.password or ""
    email = (data.email or "").strip().lower() or None
    if len(username) < 3:
        raise HTTPException(400, "Inserisci un nome utente di almeno 3 caratteri")
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "Nome utente già registrato")
    if email and db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email già registrata")
    trial_ends = datetime.utcnow() + timedelta(days=TRIAL_DAYS)
    selected_plan = (getattr(data, "plan", None) or "starter").strip().lower()
    if selected_plan not in {"starter", "business", "pro"}:
        selected_plan = "starter"
    user = User(
        username=username,
        email=email,
        company_name=(data.company_name or "").strip() or None,
        company_phone=(data.company_phone or "").strip() or None,
        company_vat=(data.company_vat or "").strip() or None,
        company_fiscal_code=(data.company_fiscal_code or "").strip() or None,
        company_pec=(data.company_pec or "").strip() or None,
        company_sdi=(data.company_sdi or "").strip() or None,
        company_address=(data.company_address or "").strip() or None,
        company_city=(data.company_city or "").strip() or None,
        company_zip=(data.company_zip or "").strip() or None,
        company_country=(data.company_country or "Italia").strip() or "Italia",
        company_legal_address=(data.company_legal_address or "").strip() or None,
        company_billing_address=(data.company_billing_address or "").strip() or None,
        company_sector="distribution",  # v89: valore legacy interno; nessuna verticalizzazione UI
        company_activity_type=(data.company_activity_type or "").strip() or None,
        company_size=(data.company_size or "").strip() or None,
        daily_deliveries=(data.daily_deliveries or "").strip() or None,
        has_time_windows=bool(data.has_time_windows),
        needs_signature=bool(data.needs_signature),
        needs_photo_proof=bool(data.needs_photo_proof),
        has_refrigerated_goods=bool(data.has_refrigerated_goods),
        has_ztl=bool(data.has_ztl),
        needs_tail_lift=bool(data.needs_tail_lift),
        universal_features_initialized=True,
        delivery_signature_enabled=bool(data.needs_signature),
        password_hash=hash_password(password),
        plan=selected_plan,
        plan_status="trial",
        trial_ends_at=trial_ends,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    response.set_cookie(
        "session", make_token(user.id),
        **cookie_options(60 * 60 * 24 * 7),
    )
    # Email di benvenuto
    if email:
        try:
            from ..services.email import send_welcome
            send_welcome(
                to_email=email,
                username=username,
                company_name=data.company_name or username,
                trial_days=TRIAL_DAYS,
            )
        except Exception:
            pass
    return {
        "ok": True,
        "username": user.username,
        "company_name": user.company_name,
        "is_admin": is_admin_user(user),
        **user_plan_info(user),
    }




# -----------------------------------------------------------------------
# Login separato Super Admin SaaS
# -----------------------------------------------------------------------
def _is_superadmin_credentials(identifier: str, password: str) -> bool:
    return (identifier or "").strip().lower() == (SUPERADMIN_USERNAME or "admin").strip().lower() and hmac_compare(password or "", SUPERADMIN_PASSWORD or "")


def hmac_compare(a: str, b: str) -> bool:
    # confronto costante semplice senza esporre il valore delle credenziali
    import hmac
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


@router.post("/api/admin/login")
def superadmin_login(payload: dict, response: Response, db: Session = Depends(get_db)):
    identifier = (payload.get("username") or payload.get("email") or "").strip()
    identifier_norm = identifier.lower()
    password = payload.get("password") or ""
    if _is_superadmin_credentials(identifier, password):
        response.delete_cookie("session")
        response.delete_cookie("driver_session")
        response.delete_cookie("agent_session")
        response.set_cookie("superadmin_session", make_superadmin_token(SUPERADMIN_USERNAME), **cookie_options(60 * 60 * 24 * 7))
        return {"ok": True, "role": "superadmin", "redirect_url": "/admin"}

    collaborator = db.query(SuperAdminCollaborator).filter(func.lower(SuperAdminCollaborator.email) == identifier_norm).first()
    if collaborator and collaborator.is_active and verify_password(password, collaborator.password_hash):
        collaborator.last_access_at = datetime.utcnow()
        db.commit()
        response.delete_cookie("session")
        response.delete_cookie("driver_session")
        response.delete_cookie("agent_session")
        response.set_cookie("superadmin_session", make_superadmin_collaborator_token(collaborator.id), **cookie_options(60 * 60 * 24 * 7))
        return {"ok": True, "role": "collaborator", "redirect_url": "/admin"}

    raise HTTPException(401, "Credenziali Super Admin non corrette")


@router.post("/api/admin/logout")
def superadmin_logout(response: Response):
    response.delete_cookie("superadmin_session")
    return {"ok": True}


@router.get("/api/admin/me")
def superadmin_me(request: Request, db: Session = Depends(get_db)):
    username = verify_superadmin_token(request.cookies.get("superadmin_session"))
    if not username:
        return {"authenticated": False, "role": None}
    if str(username).startswith("collab:"):
        try:
            collaborator_id = int(str(username).split(":", 1)[1])
        except Exception:
            return {"authenticated": False, "role": None}
        collaborator = db.get(SuperAdminCollaborator, collaborator_id)
        if not collaborator or not collaborator.is_active:
            return {"authenticated": False, "role": None}
        import json
        try:
            permissions = json.loads(collaborator.permissions_json or "{}")
        except Exception:
            permissions = {}
        return {
            "authenticated": True,
            "role": "collaborator",
            "username": collaborator.email,
            "display_name": collaborator.full_name,
            "permissions": permissions,
            "redirect_url": "/admin",
        }
    if username.strip().lower() != (SUPERADMIN_USERNAME or "admin").strip().lower():
        return {"authenticated": False, "role": None}
    return {"authenticated": True, "role": "superadmin", "username": username, "display_name": username, "permissions": {"all": True}, "redirect_url": "/admin"}

@router.post("/api/login")
async def login(payload: dict, response: Response, db: Session = Depends(get_db)):
    """Login unico multi-ruolo.

    L'utente inserisce email/username e password da /login. Il backend
    riconosce automaticamente il ruolo e restituisce la destinazione corretta:
    admin/azienda -> /dashboard, autista -> /driver, agente -> /agent.
    """
    identifier = (payload.get("username") or payload.get("email") or "").strip()
    identifier_norm = identifier.lower()
    password = payload.get("password") or ""

    # Super Admin SaaS: anche se viene inserito per errore nel login unico,
    # non viene mai trattato come profilo aziendale.
    if _is_superadmin_credentials(identifier, password):
        response.delete_cookie("session")
        response.delete_cookie("driver_session")
        response.delete_cookie("agent_session")
        response.set_cookie("superadmin_session", make_superadmin_token(SUPERADMIN_USERNAME), **cookie_options(60 * 60 * 24 * 7))
        return {"ok": True, "role": "superadmin", "redirect_url": "/admin"}

    # 1) Account azienda / amministratore
    user = db.query(User).filter(
        or_(
            func.lower(User.username) == identifier_norm,
            func.lower(User.email) == identifier_norm,
        )
    ).first()
    if user and verify_password(password, user.password_hash):
        _set_login_cookie_for_role(response, "admin", user)
        return {
            "ok": True,
            "role": "admin",
            "redirect_url": _redirect_for_role("admin"),
            "username": user.username,
            "email": user.email,
            "company_name": user.company_name,
            "company_logo_url": user.company_logo_url,
            "company_email": user.company_email,
            "company_phone": user.company_phone,
            "company_vat": user.company_vat,
            "company_address": user.company_address,
            "company_city": user.company_city,
            "company_zip": user.company_zip,
            "company_country": user.company_country,
            "company_sector": getattr(user, "company_sector", None) or "",
            "company_activity_type": getattr(user, "company_activity_type", None) or "",
            "sector_config": get_sector_config(getattr(user, "company_sector", None)),
            "sector_options": public_sector_options(),
            "onboarding_completed": user.onboarding_completed,
            "onboarding_dismissed": user.onboarding_dismissed,
            "workspace_operational": _workspace_operational_for_user(user),
            "is_admin": is_admin_user(user),
            **user_plan_info(user),
        }

    # 2) Account autista
    driver_account = db.query(DriverAccount).filter(func.lower(DriverAccount.email) == identifier_norm).first()
    if driver_account and verify_password(password, driver_account.password_hash):
        if not driver_account.is_active:
            raise HTTPException(403, "Account autista disabilitato")
        if password_needs_rehash(driver_account.password_hash):
            driver_account.password_hash = hash_password(password)
        driver_account.last_login = datetime.utcnow()
        db.commit()
        _set_login_cookie_for_role(response, "driver", driver_account)
        driver = db.get(Driver, driver_account.driver_id)
        driver_name = f"{driver.nome} {driver.cognome or ''}".strip() if driver else driver_account.email
        return {
            "ok": True,
            "role": "driver",
            "redirect_url": _redirect_for_role("driver"),
            "email": driver_account.email,
            "driver_name": driver_name,
        }

    # 3) Account agente
    agent_account = db.query(AgentAccount).filter(func.lower(AgentAccount.email) == identifier_norm).first()
    if agent_account and verify_password(password, agent_account.password_hash):
        agent = db.get(Agent, agent_account.agent_id)
        require_agents_enabled(db.get(User, agent.user_id) if agent else None)
        if not agent_account.is_active:
            raise HTTPException(403, "Account agente disabilitato")
        if password_needs_rehash(agent_account.password_hash):
            agent_account.password_hash = hash_password(password)
        agent_account.last_login = datetime.utcnow()
        db.commit()
        _set_login_cookie_for_role(response, "agent", agent_account)
        agent = db.get(Agent, agent_account.agent_id)
        agent_name = f"{agent.nome} {agent.cognome or ''}".strip() if agent else agent_account.email
        return {
            "ok": True,
            "role": "agent",
            "redirect_url": _redirect_for_role("agent"),
            "email": agent_account.email,
            "agent_name": agent_name,
        }

    raise HTTPException(401, "Email o password non corretti")


@router.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session")
    response.delete_cookie("driver_session")
    response.delete_cookie("agent_session")
    return {"ok": True}


def _read_driver_session(raw: str | None, db: Session) -> DriverAccount | None:
    if not raw:
        return None
    try:
        raw_id, token_hash = raw.split(":", 1)
        account = db.get(DriverAccount, int(raw_id))
    except Exception:
        return None
    if not account or not account.is_active:
        return None
    expected = hashlib.sha256(f"driver-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    return account if token_hash == expected else None


def _read_agent_session(raw: str | None, db: Session) -> AgentAccount | None:
    if not raw:
        return None
    try:
        raw_id, token_hash = raw.split(":", 1)
        account = db.get(AgentAccount, int(raw_id))
    except Exception:
        return None
    if not account or not account.is_active:
        return None
    expected = hashlib.sha256(f"agent-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    return account if token_hash == expected else None


@router.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)):
    user_id = verify_token(request.cookies.get("session"))
    user = db.get(User, user_id) if user_id else None
    if user:
        return {
            "authenticated": True,
            "role": "admin",
            "redirect_url": _redirect_for_role("admin"),
            "username": user.username,
            "email": user.email,
            "company_name": user.company_name,
            "company_logo_url": user.company_logo_url,
            "company_email": user.company_email,
            "company_phone": user.company_phone,
            "company_vat": user.company_vat,
            "company_address": user.company_address,
            "company_city": user.company_city,
            "company_zip": user.company_zip,
            "company_country": user.company_country,
            "company_sector": getattr(user, "company_sector", None) or "",
            "company_activity_type": getattr(user, "company_activity_type", None) or "",
            "sector_config": get_sector_config(getattr(user, "company_sector", None)),
            "sector_options": public_sector_options(),
            "onboarding_completed": user.onboarding_completed,
            "onboarding_dismissed": user.onboarding_dismissed,
            "workspace_operational": _workspace_operational_for_user(user),
            "is_admin": is_admin_user(user),
            **user_plan_info(user),
        }

    driver_account = _read_driver_session(request.cookies.get("driver_session"), db)
    if driver_account:
        driver = db.get(Driver, driver_account.driver_id)
        return {
            "authenticated": True,
            "role": "driver",
            "redirect_url": _redirect_for_role("driver"),
            "email": driver_account.email,
            "driver_name": f"{driver.nome} {driver.cognome or ''}".strip() if driver else driver_account.email,
            "is_admin": False,
        }

    agent_account = _read_agent_session(request.cookies.get("agent_session"), db)
    if agent_account:
        agent = db.get(Agent, agent_account.agent_id)
        require_agents_enabled(db.get(User, agent.user_id) if agent else None)
        return {
            "authenticated": True,
            "role": "agent",
            "redirect_url": _redirect_for_role("agent"),
            "email": agent_account.email,
            "agent_name": f"{agent.nome} {agent.cognome or ''}".strip() if agent else agent_account.email,
            "is_admin": False,
        }

    return {"authenticated": False, "role": None, "is_admin": False}



PASSWORD_RESET_SAFE_MESSAGE = "Se l'email è associata a un account GiroFacile, riceverai un link per reimpostare la password."


def _driver_hash_password(password: str) -> str:
    # Compatibilità residua: il nuovo sistema usa hash_password/verify_password.
    return hashlib.sha256(password.encode()).hexdigest()


def _driver_session_token(account: DriverAccount) -> str:
    token_hash = hashlib.sha256(f"driver-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    return f"{account.id}:{token_hash}"


def _agent_session_token(account: AgentAccount) -> str:
    token_hash = hashlib.sha256(f"agent-session-{account.id}-{account.password_hash}".encode()).hexdigest()
    return f"{account.id}:{token_hash}"


def _set_login_cookie_for_role(response: Response, role: str, account) -> None:
    # Cancella sempre le altre sessioni per evitare confusione tra ruoli.
    response.delete_cookie("session")
    response.delete_cookie("driver_session")
    response.delete_cookie("agent_session")
    if role == "admin":
        response.set_cookie("session", make_token(account.id), **cookie_options(60 * 60 * 24 * 7))
    elif role == "driver":
        response.set_cookie("driver_session", _driver_session_token(account), **cookie_options(60 * 60 * 24 * 30))
    elif role == "agent":
        response.set_cookie("agent_session", _agent_session_token(account), **cookie_options(60 * 60 * 24 * 30))


def _redirect_for_role(role: str) -> str:
    if role == "driver":
        return "/driver"
    if role == "agent":
        return "/agent"
    return "/dashboard"


def _reset_display_for_account(account_type: str, account, db: Session) -> tuple[str, str]:
    if account_type == "user":
        return (account.company_name or account.username or "Account azienda", "Account azienda")
    if account_type == "driver":
        driver = db.get(Driver, account.driver_id)
        name = f"{driver.nome} {driver.cognome or ''}".strip() if driver else account.email
        return (name or "Autista", "Portale autista")
    if account_type == "agent":
        agent = db.get(Agent, account.agent_id)
        name = f"{agent.nome} {agent.cognome or ''}".strip() if agent else account.email
        return (name or "Agente", "Portale agente")
    return (account.email, "Account GiroFacile")


def _create_reset_token(db: Session, account_type: str, account_id: int, email: str) -> PasswordResetToken:
    token = secrets.token_urlsafe(48)
    prt = PasswordResetToken(
        account_type=account_type,
        account_id=account_id,
        email=email.strip().lower(),
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        used_at=None,
    )
    db.add(prt)
    return prt


def _find_reset_accounts(email: str, db: Session):
    email_norm = email.strip().lower()
    accounts = []
    user = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if user:
        accounts.append(("user", user))
    driver_account = db.query(DriverAccount).filter(func.lower(DriverAccount.email) == email_norm).first()
    if driver_account:
        accounts.append(("driver", driver_account))
    agent_account = db.query(AgentAccount).filter(func.lower(AgentAccount.email) == email_norm).first()
    if agent_account:
        accounts.append(("agent", agent_account))
    return accounts


@router.post("/api/password-reset/request")
def request_password_reset(payload: dict, db: Session = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "Inserisci una email valida")

    accounts = _find_reset_accounts(email, db)
    if accounts:
        from ..services.email import send_password_reset
        for account_type, account in accounts:
            prt = _create_reset_token(db, account_type, account.id, email)
            display_name, account_label = _reset_display_for_account(account_type, account, db)
            reset_url = f"{APP_BASE_URL}/reset-password/{prt.token}"
            try:
                send_password_reset(email, display_name, reset_url, account_label=account_label)
            except Exception as exc:
                print(f"[PASSWORD_RESET] Errore invio email a {email}: {exc}")
        db.commit()

    # Messaggio sempre uguale: non rivela se l'email esiste o meno.
    return {"ok": True, "message": PASSWORD_RESET_SAFE_MESSAGE}


# Compatibilità con la vecchia rotta: ora NON crea più ticket per l'admin.
@router.post("/api/support/password-reset-request")
def legacy_password_reset_request(payload: dict, db: Session = Depends(get_db)):
    return request_password_reset(payload, db)


@router.get("/api/password-reset/{token}")
def get_password_reset_info(token: str, db: Session = Depends(get_db)):
    prt = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if not prt or prt.used_at or datetime.utcnow() > prt.expires_at:
        raise HTTPException(404, "Link non valido o scaduto")
    return {"ok": True, "email": prt.email, "account_type": prt.account_type}


@router.post("/api/password-reset/confirm")
def confirm_password_reset(payload: dict, db: Session = Depends(get_db)):
    token = (payload.get("token") or "").strip()
    password = (payload.get("password") or "").strip()
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    prt = db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()
    if not prt or prt.used_at or datetime.utcnow() > prt.expires_at:
        raise HTTPException(400, "Link non valido o scaduto")

    if prt.account_type == "user":
        account = db.get(User, prt.account_id)
        if not account:
            raise HTTPException(404, "Account non trovato")
        account.password_hash = hash_password(password)
    elif prt.account_type == "driver":
        account = db.get(DriverAccount, prt.account_id)
        if not account:
            raise HTTPException(404, "Account autista non trovato")
        account.password_hash = hash_password(password)
        account.is_active = True
    elif prt.account_type == "agent":
        account = db.get(AgentAccount, prt.account_id)
        if not account:
            raise HTTPException(404, "Account agente non trovato")
        account.password_hash = hash_password(password)
        account.is_active = True
    else:
        raise HTTPException(400, "Tipo account non supportato")

    prt.used_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Password aggiornata correttamente. Ora puoi accedere con la nuova password."}


# -----------------------------------------------------------------------
# Profilo azienda + onboarding iniziale
# -----------------------------------------------------------------------
def _company_payload(user: User) -> dict:
    return {
        "company_name": user.company_name or user.username,
        "company_logo_url": user.company_logo_url or "",
        "company_email": user.company_email or user.email or "",
        "company_phone": user.company_phone or "",
        "company_vat": user.company_vat or "",
        "company_fiscal_code": getattr(user, "company_fiscal_code", None) or "",
        "company_pec": getattr(user, "company_pec", None) or "",
        "company_sdi": getattr(user, "company_sdi", None) or "",
        "company_address": user.company_address or "",
        "company_city": user.company_city or "",
        "company_zip": user.company_zip or "",
        "company_country": user.company_country or "Italia",
        "company_legal_address": getattr(user, "company_legal_address", None) or "",
        "company_billing_address": getattr(user, "company_billing_address", None) or "",
        "company_sector": getattr(user, "company_sector", None) or "",
        "sector_config": get_sector_config(getattr(user, "company_sector", None)),
        "sector_options": public_sector_options(),
        "company_activity_type": getattr(user, "company_activity_type", None) or "",
        "company_size": getattr(user, "company_size", None) or "",
        "daily_deliveries": getattr(user, "daily_deliveries", None) or "",
        "has_time_windows": bool(getattr(user, "has_time_windows", True)),
        "needs_signature": bool(getattr(user, "needs_signature", False)),
        "needs_photo_proof": bool(getattr(user, "needs_photo_proof", False)),
        "has_refrigerated_goods": bool(getattr(user, "has_refrigerated_goods", False)),
        "has_ztl": bool(getattr(user, "has_ztl", False)),
        "needs_tail_lift": bool(getattr(user, "needs_tail_lift", False)),
        "account_email": user.email or "",
        "plan": user.plan,
        "plan_status": user.plan_status,
    }


@router.get("/api/account-profile")
def get_account_profile(user: User = Depends(current_user)):
    """Restituisce i dati reali dell'account salvati nel database.

    Il profilo account non deve dipendere dal localStorage del browser: email,
    nome utente e password sono informazioni condivise tra tutti i dispositivi.
    """
    return {
        "username": user.username or "",
        "email": user.email or "",
        "role": "Amministratore",
    }


@router.put("/api/account-profile")
def update_account_profile(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    username = (payload.get("username") or user.username or "").strip()
    email = (payload.get("email") or "").strip().lower() or None
    new_password = (payload.get("new_password") or "").strip()

    if len(username) < 3:
        raise HTTPException(400, "Il nome account deve contenere almeno 3 caratteri")

    duplicate_username = db.query(User).filter(
        func.lower(User.username) == username.lower(),
        User.id != user.id,
    ).first()
    if duplicate_username:
        raise HTTPException(400, "Nome account già utilizzato")

    if email:
        duplicate_user = db.query(User).filter(
            func.lower(User.email) == email,
            User.id != user.id,
        ).first()
        duplicate_driver = db.query(DriverAccount).filter(func.lower(DriverAccount.email) == email).first()
        duplicate_agent = db.query(AgentAccount).filter(func.lower(AgentAccount.email) == email).first()
        if duplicate_user or duplicate_driver or duplicate_agent:
            raise HTTPException(400, "Email già associata a un altro account")

    if new_password:
        try:
            validate_password_strength(new_password)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        user.password_hash = hash_password(new_password)

    user.username = username
    user.email = email
    db.commit()
    db.refresh(user)
    return {
        "ok": True,
        "account": {
            "username": user.username or "",
            "email": user.email or "",
            "role": "Amministratore",
        },
    }


@router.get("/api/sector-config")
def get_sector_configuration(user: User = Depends(current_user)):
    return {
        "current": get_sector_config(getattr(user, "company_sector", None)),
        "options": public_sector_options(),
    }


@router.get("/api/company-profile")
def get_company_profile(user: User = Depends(current_user)):
    return _company_payload(user)


@router.put("/api/company-profile")
def update_company_profile(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {
        "company_name", "company_logo_url", "company_email", "company_phone",
        "company_vat", "company_fiscal_code", "company_pec", "company_sdi",
        "company_address", "company_city", "company_zip", "company_country",
        "company_legal_address", "company_billing_address", "company_sector",
        "company_activity_type", "company_size", "daily_deliveries",
        "has_time_windows", "needs_signature", "needs_photo_proof",
        "has_refrigerated_goods", "has_ztl", "needs_tail_lift"
    }
    for key in allowed:
        if key in payload:
            value = payload.get(key)
            if isinstance(value, str):
                value = value.strip()
            if key == "company_sector":
                value = normalize_sector_key(value)
            # I booleani devono restare True/False: `value or None` trasformava
            # False in NULL e causava il 500 sulle colonne NOT NULL.
            if key in {"has_time_windows", "needs_signature", "needs_photo_proof", "has_refrigerated_goods", "has_ztl", "needs_tail_lift"}:
                setattr(user, key, bool(value))
            else:
                setattr(user, key, value or None)
    if not user.company_country:
        user.company_country = "Italia"
    db.commit()
    db.refresh(user)
    return {"ok": True, "company": _company_payload(user)}


def _count_for_user(db: Session, model, user_id: int) -> int:
    return db.query(model).filter(model.user_id == user_id).count()


@router.get("/api/onboarding/status")
def onboarding_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stato configurazione iniziale azienda.

    v49: per i nuovi account l'area operativa resta volutamente pulita.
    Clienti, autisti, mezzi, pianificazione, storico e report vengono sbloccati
    solo quando l'azienda segna la configurazione come completata.
    """
    counts = {
        "deposits": _count_for_user(db, Deposit, user.id),
        "vehicles": _count_for_user(db, Vehicle, user.id),
        "drivers": _count_for_user(db, Driver, user.id),
        "customers": _count_for_user(db, Customer, user.id),
        "routes": _count_for_user(db, RoutePlan, user.id),
    }
    company_ready = bool((user.company_name or "").strip())
    settings_ready = True
    steps = [
        {"key": "company", "label": "Completa il profilo azienda", "done": company_ready, "tab": "company"},
        {"key": "settings", "label": "Configura le funzionalità utili", "done": settings_ready, "tab": "settings"},
    ]
    progress = sum(1 for s in steps if s["done"])
    return {
        "ok": True,
        "counts": counts,
        "steps": steps,
        "progress": progress,
        "total": len(steps),
        "percent": round(progress / len(steps) * 100),
        "completed": bool(user.onboarding_completed),
        "workspace_operational": _workspace_operational_for_user(user),
        "dismissed": bool(user.onboarding_dismissed),
    }


@router.post("/api/onboarding/complete")
def complete_onboarding(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.onboarding_completed = True
    user.onboarding_completed_at = datetime.utcnow()
    user.onboarding_dismissed = True
    db.commit()
    return {"ok": True}


@router.post("/api/onboarding/dismiss")
def dismiss_onboarding(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.onboarding_dismissed = True
    db.commit()
    return {"ok": True}
