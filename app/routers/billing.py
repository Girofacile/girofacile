"""
Router billing - gestione piani e abbonamenti Stripe.
La struttura è pronta; l'integrazione Stripe completa
va attivata inserendo STRIPE_SECRET_KEY nel .env.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..core.config import PLAN_PRICES, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from ..core.dependencies import current_user
from ..database import get_db
from ..models import User, BillingInvoice, BillingPayment
from ..services.plans import PLAN_LIMITS, get_user_plan_status, user_plan_info

router = APIRouter(prefix="/api/billing", tags=["billing"])


def _plan_display_name(plan: str | None) -> str:
    return {"starter": "Starter", "business": "Business", "pro": "Pro"}.get((plan or "starter").lower(), plan or "Starter")


def _plan_monthly_price(plan: str | None) -> float:
    info = PLAN_PRICES.get((plan or "starter").lower(), {})
    try:
        return float(info.get("price_eur", 0) or 0)
    except Exception:
        return 0.0


def _date_iso(dt):
    return dt.isoformat() if dt else None


def _billing_company_payload(user: User) -> dict:
    return {
        "company_name": user.company_name or user.username,
        "company_email": user.company_email or user.email or "",
        "company_vat": user.company_vat or "",
        "company_fiscal_code": getattr(user, "company_fiscal_code", None) or "",
        "company_pec": getattr(user, "company_pec", None) or "",
        "company_sdi": getattr(user, "company_sdi", None) or "",
        "company_legal_address": getattr(user, "company_legal_address", None) or user.company_address or "",
        "company_billing_address": getattr(user, "company_billing_address", None) or getattr(user, "company_legal_address", None) or user.company_address or "",
        "billing_email": user.company_email or user.email or "",
    }


@router.get("/overview")
def billing_overview(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Area fatturazione utente: piano, dati fiscali, fatture e pagamenti."""
    plan = (user.plan or "starter").lower()
    status = user.plan_status or "trial"
    price = _plan_monthly_price(plan)
    now = datetime.utcnow()
    next_charge = user.plan_expires_at or user.trial_ends_at
    if not next_charge and status == "active":
        next_charge = now + timedelta(days=30)

    invoices = db.query(BillingInvoice).filter(BillingInvoice.user_id == user.id).order_by(BillingInvoice.invoice_date.desc()).limit(24).all()
    payments = db.query(BillingPayment).filter(BillingPayment.user_id == user.id).order_by(BillingPayment.created_at.desc()).limit(24).all()

    return {
        "plan": {
            "key": plan,
            "name": _plan_display_name(plan),
            "status": status,
            "monthly_price": price,
            "currency": "EUR",
            "trial_ends_at": _date_iso(user.trial_ends_at),
            "plan_expires_at": _date_iso(user.plan_expires_at),
            "next_charge_at": _date_iso(next_charge),
            "next_charge_amount": price if status in ("active", "trial") else 0,
        },
        "company": _billing_company_payload(user),
        "payment_method": {
            "configured": bool(getattr(user, "stripe_customer_id", None)),
            "label": "Metodo di pagamento non ancora configurato" if not getattr(user, "stripe_customer_id", None) else "Metodo collegato",
            "provider": "Stripe" if getattr(user, "stripe_customer_id", None) else "",
            "last4": "",
        },
        "invoices": [
            {
                "id": inv.id,
                "number": inv.invoice_number,
                "date": _date_iso(inv.invoice_date),
                "period_start": _date_iso(inv.period_start),
                "period_end": _date_iso(inv.period_end),
                "plan_name": inv.plan_name or _plan_display_name(plan),
                "subtotal": inv.subtotal,
                "vat_amount": inv.vat_amount,
                "total": inv.total,
                "currency": inv.currency or "EUR",
                "status": inv.status,
                "pdf_available": bool(inv.pdf_path),
            }
            for inv in invoices
        ],
        "payments": [
            {
                "id": pay.id,
                "invoice_id": pay.invoice_id,
                "amount": pay.amount,
                "currency": pay.currency or "EUR",
                "method": pay.payment_method or "—",
                "status": pay.payment_status,
                "transaction_id": pay.transaction_id or "",
                "paid_at": _date_iso(pay.paid_at),
                "created_at": _date_iso(pay.created_at),
            }
            for pay in payments
        ],
    }


@router.put("/billing-details")
def update_billing_details(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Aggiorna i dati fiscali mostrati nell'area fatturazione."""
    allowed = {
        "company_name", "company_email", "company_vat", "company_fiscal_code",
        "company_pec", "company_sdi", "company_legal_address", "company_billing_address"
    }
    for key in allowed:
        if key in payload:
            value = payload.get(key)
            if isinstance(value, str):
                value = value.strip()
            setattr(user, key, value or None)
    db.commit()
    db.refresh(user)
    return {"ok": True, "company": _billing_company_payload(user)}


@router.get("/plans")
def list_plans():
    """Ritorna i piani disponibili con prezzi e limiti (endpoint pubblico)."""
    result = []
    for plan_key, limits in PLAN_LIMITS.items():
        price_info = PLAN_PRICES.get(plan_key, {})
        result.append({
            "id": plan_key,
            "name": limits["name"],
            "price_eur": price_info.get("price_eur", 0),
            "trial_days": 14,
            "limits": {
                "clienti": limits["max_customers"] or "Illimitati",
                "giri_al_giorno": limits["max_routes_per_day"] or "Illimitati",
                "depositi": limits["max_deposits"] or "Illimitati",
                "mezzi": limits["max_vehicles"] or "Illimitati",
                "autisti": limits["max_drivers"] or "Illimitati",
            },
            "features": {
                "agenti": limits["has_agents"],
                "report": limits["has_reports"],
                "export_csv": limits["has_export"],
                "geocodifica": limits["has_geocoding"],
                "interfaccia_mobile": limits["has_mobile"],
            },
        })
    return result


@router.get("/my-plan")
def my_plan(user: User = Depends(current_user)):
    """Ritorna le info del piano dell'utente corrente."""
    return user_plan_info(user)


@router.post("/select-plan")
def select_plan(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Cambia il piano dell'utente (modalità test senza pagamento).
    Quando Stripe sarà attivo, questo endpoint verrà sostituito dal checkout.
    """
    plan_key = (payload.get("plan") or "").strip().lower()
    if plan_key not in ("starter", "business", "pro"):
        raise HTTPException(400, "Piano non valido")

    user.plan = plan_key
    # Se era in trial o expired, lo attiviamo
    if user.plan_status in ("trial", "expired", "cancelled"):
        user.plan_status = "active"
    db.commit()
    return {
        "ok": True,
        "plan": user.plan,
        "plan_status": user.plan_status,
        **user_plan_info(user),
    }


@router.post("/create-checkout-session")
async def create_checkout_session(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """
    Crea una sessione Stripe Checkout per l'acquisto/upgrade del piano.
    Richiede STRIPE_SECRET_KEY nel .env.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Pagamenti non ancora configurati. Contatta l'amministratore.")

    plan_key = (payload.get("plan") or "").strip().lower()
    if plan_key not in PLAN_PRICES:
        raise HTTPException(400, "Piano non valido")

    price_info = PLAN_PRICES[plan_key]
    stripe_price_id = price_info.get("stripe_price_id", "")
    if not stripe_price_id:
        raise HTTPException(503, f"Prezzo Stripe non configurato per il piano {plan_key}")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        # Crea o recupera il customer Stripe
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email or "",
                name=user.company_name or user.username,
                metadata={"user_id": str(user.id), "username": user.username},
            )
            user.stripe_customer_id = customer.id
            db.commit()

        base_url = str(request.base_url).rstrip("/")
        session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=f"{base_url}/dashboard?checkout=success&plan={plan_key}",
            cancel_url=f"{base_url}/dashboard?checkout=cancelled",
            metadata={"user_id": str(user.id), "plan": plan_key},
        )
        return {"checkout_url": session.url}

    except ImportError:
        raise HTTPException(503, "Libreria Stripe non installata. Aggiungi 'stripe' ai requirements.")
    except Exception as e:
        raise HTTPException(500, f"Errore creazione sessione pagamento: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Webhook Stripe per aggiornare automaticamente lo stato degli abbonamenti.
    Configura l'URL https://app.girofacile.it/api/billing/webhook nel pannello Stripe.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Stripe non configurato")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ImportError:
        raise HTTPException(503, "Libreria Stripe non installata")
    except Exception:
        raise HTTPException(400, "Webhook non valido")

    event_type = event["type"]
    data = event["data"]["object"]

    # Abbonamento attivato / rinnovato
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        stripe_customer_id = data.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == stripe_customer_id).first()
        if user:
            plan_key = data.get("metadata", {}).get("plan") or _stripe_plan_from_subscription(data)
            status = data.get("status")
            if status == "active":
                user.plan = plan_key or user.plan
                user.plan_status = "active"
                # Imposta scadenza dal periodo corrente Stripe
                period_end = data.get("current_period_end")
                if period_end:
                    from datetime import datetime
                    user.plan_expires_at = datetime.utcfromtimestamp(period_end)
                user.stripe_subscription_id = data.get("id")
            db.commit()

    # Abbonamento cancellato / scaduto
    elif event_type == "customer.subscription.deleted":
        stripe_customer_id = data.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == stripe_customer_id).first()
        if user:
            user.plan_status = "cancelled"
            db.commit()

    return {"ok": True}


def _stripe_plan_from_subscription(subscription_data: dict) -> str:
    """Tenta di ricavare il piano dal price_id Stripe."""
    try:
        price_id = subscription_data["items"]["data"][0]["price"]["id"]
        for plan_key, info in PLAN_PRICES.items():
            if info.get("stripe_price_id") == price_id:
                return plan_key
    except Exception:
        pass
    return "starter"
