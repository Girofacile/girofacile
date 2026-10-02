"""
Router billing - gestione piani e abbonamenti Stripe.
Acquisti sandbox riservati agli account di collaudo; incassi reali bloccati.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..core.config import PLAN_PRICES, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from ..core.dependencies import current_user
from ..database import get_db
from ..models import User, BillingInvoice, BillingPayment, BillingEvent, BillingNotice, SuperAdminProfile
from ..services.plans import PLAN_LIMITS, get_user_plan_status, user_plan_info

router = APIRouter(prefix="/api/billing", tags=["billing"])


def billing_state(user):
    from ..core import config
    return {"mode": config.BILLING_MODE, "live_enabled": False,
            "checkout_enabled": config.BILLING_MODE == "test" and user.id in config.BILLING_TEST_USER_IDS,
            "source": user.billing_source or "legacy", "subscription": bool(user.stripe_subscription_id),
            "cancel_at_period_end": bool(user.billing_cancel_at_period_end),
            "pending_plan": user.billing_pending_plan,
            "grace_until": _date_iso(user.billing_grace_until)}


@router.get("/catalog.js", include_in_schema=False)
def public_catalog_script():
    import json
    from fastapi.responses import Response
    catalog = {key: {**limits, "price_eur": PLAN_PRICES[key]["price_eur"]} for key, limits in PLAN_LIMITS.items()}
    return Response("window.GF_PLANS = " + json.dumps(catalog) + ";", media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


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
    status = get_user_plan_status(user)
    price = _plan_monthly_price(plan)
    now = datetime.utcnow()
    next_charge = user.plan_expires_at if user.stripe_subscription_id and not user.billing_cancel_at_period_end else None

    invoices = db.query(BillingInvoice).filter(BillingInvoice.user_id == user.id).order_by(BillingInvoice.invoice_date.desc()).limit(24).all()
    payments = db.query(BillingPayment).filter(BillingPayment.user_id == user.id).order_by(BillingPayment.created_at.desc()).limit(24).all()

    from ..services.usage_limits import usage_summary
    return {
        "billing": billing_state(user),
        "usage": usage_summary(db, user),
        "plan": {
            "key": plan,
            "name": _plan_display_name(plan),
            "status": status,
            "monthly_price": price,
            "currency": "EUR",
            "trial_ends_at": _date_iso(user.trial_ends_at),
            "plan_expires_at": _date_iso(user.plan_expires_at),
            "next_charge_at": _date_iso(next_charge),
            "next_charge_amount": price if next_charge else 0,
        },
        "company": _billing_company_payload(user),
        "payment_method": {
            "configured": False,
            "label": "Verifica o aggiorna il metodo nel portale Stripe" if user.stripe_customer_id else "Nessun metodo collegato",
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
                "pdf_available": bool(inv.stripe_invoice_id),
                "is_test": bool(inv.is_test),
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
                "is_test": bool(pay.is_test),
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
    return [{"id": key, "name": info["name"], "price_eur": PLAN_PRICES[key]["price_eur"],
             "trial_days": 14, "limits": info, "features": info} for key, info in PLAN_LIMITS.items()]


@router.get("/my-plan")
def my_plan(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.usage_limits import usage_summary
    return {**user_plan_info(user), "billing": billing_state(user), "usage": usage_summary(db, user)}


@router.get("/data-export")
def export_company_data(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Customer-owned operational data remain portable on every plan and after expiry."""
    import csv
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from ..models import Customer, Vehicle, Driver, Deposit, RoutePlan, Delivery
    tables = [
        (Customer, ("id", "nome", "indirizzo", "email", "telefono", "codice_cliente")),
        (Vehicle, ("id", "nome", "targa", "capacita_kg", "capacita_colli")),
        (Driver, ("id", "nome", "cognome", "email", "telefono")),
        (Deposit, ("id", "nome", "indirizzo")),
        (RoutePlan, ("id", "nome", "data_giro", "status", "driver_id", "vehicle_id", "deposit_id")),
        (Delivery, ("id", "route_plan_id", "customer_id", "cliente_nome", "indirizzo", "ordine")),
    ]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for model, fields in tables:
            query = db.query(model)
            if model is Delivery:
                query = query.join(RoutePlan, Delivery.route_plan_id == RoutePlan.id).filter(RoutePlan.user_id == user.id)
            else:
                query = query.filter(model.user_id == user.id)
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(fields)
            for row in query.all():
                values = [getattr(row, key, "") for key in fields]
                # Neutralize spreadsheet formulas in user-entered cells.
                writer.writerow(["'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in values])
            z.writestr(model.__tablename__ + ".csv", output.getvalue().encode("utf-8-sig"))
    archive.seek(0)
    return StreamingResponse(archive, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="dati_girofacile.zip"'})


@router.post("/select-plan")
def select_plan(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    raise HTTPException(410, "Attivazione diretta rimossa: usa il checkout o il cambio piano verificato")


@router.post("/create-checkout-session")
def create_checkout_session(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import checkout
    return checkout(db, user, payload.get("plan"))


@router.post("/cancel-checkout")
def cancel_checkout(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import stripe_client, assert_test, lock_user, checkout
    stripe = stripe_client(user)
    user = lock_user(db, user)
    if user.billing_checkout_id and user.billing_checkout_id.startswith("pending_") and user.billing_checkout_expires and user.billing_checkout_expires > datetime.utcnow():
        # Recover an API response lost after creation before cancelling the session.
        checkout(db, user, user.billing_checkout_plan)
        user = lock_user(db, user)
    if user.billing_checkout_id and not user.billing_checkout_id.startswith("pending_"):
        session = assert_test(stripe.checkout.Session.retrieve(user.billing_checkout_id))
        if session.get("status") == "open":
            stripe.checkout.Session.expire(session["id"])
    user.billing_checkout_id = user.billing_checkout_url = user.billing_checkout_expires = user.billing_checkout_plan = None
    db.commit()
    return {"ok": True}


@router.post("/sync")
def sync_billing(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import reconcile, stripe_client, lock_user, select_current_subscription
    stripe = stripe_client(user)
    user = lock_user(db, user)
    select_current_subscription(stripe, user)
    if user.stripe_subscription_id:
        reconcile(db, user, stripe)
    db.commit()
    return {"ok": True, **user_plan_info(user)}


@router.post("/change-preview")
def preview_change(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import change_preview
    result = change_preview(db, user, payload.get("plan"))
    result.pop("subscription")
    return result


@router.post("/change-plan")
def update_subscription(payload: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import change_plan
    return change_plan(db, user, payload.get("plan"), payload)


@router.post("/cancel")
def cancel_subscription(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import cancel_or_resume
    return cancel_or_resume(db, user, True)


@router.post("/resume")
def resume_subscription(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import cancel_or_resume
    return cancel_or_resume(db, user, False)


@router.post("/portal")
def billing_portal(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from ..services.billing import stripe_client, retrieve_subscription
    from ..core.config import APP_BASE_URL
    stripe = stripe_client(user)
    retrieve_subscription(stripe, user)
    # Isolated portal configuration prevents unmanaged plan changes/cancellation.
    configuration = stripe.billing_portal.Configuration.create(
        business_profile={"headline": "GiroFacile - pagamenti di prova"},
        features={"customer_update": {"enabled": True, "allowed_updates": ["email", "address", "tax_id"]},
                  "invoice_history": {"enabled": True}, "payment_method_update": {"enabled": True},
                  "subscription_cancel": {"enabled": False}, "subscription_update": {"enabled": False}},
        idempotency_key="gf-sandbox-portal-v1")
    session = stripe.billing_portal.Session.create(customer=user.stripe_customer_id,
        configuration=configuration["id"], return_url=APP_BASE_URL.rstrip("/") + "/dashboard")
    return {"url": session["url"]}


@router.get("/invoices/{invoice_id}/download")
def invoice_download(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from fastapi.responses import RedirectResponse
    from ..services.billing import stripe_client, assert_test, object_id
    row = db.query(BillingInvoice).filter_by(id=invoice_id, user_id=user.id).first()
    if not row or not row.stripe_invoice_id:
        raise HTTPException(404, "Documento non disponibile")
    stripe = stripe_client(user)
    invoice = assert_test(stripe.Invoice.retrieve(row.stripe_invoice_id))
    if object_id(invoice.get("customer")) != user.stripe_customer_id:
        raise HTTPException(404, "Documento non disponibile")
    url = invoice.get("invoice_pdf")
    if not url or not url.startswith("https://"):
        raise HTTPException(404, "PDF non disponibile")
    return RedirectResponse(url)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    from ..services.billing import stripe_client, assert_test, object_id, reconcile, sync_invoice, select_current_subscription
    from ..core import config
    from sqlalchemy.exc import IntegrityError
    stripe = stripe_client()
    if not config.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhook sandbox non configurato")
    try:
        event = stripe.Webhook.construct_event(await request.body(), request.headers.get("stripe-signature", ""), config.STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(400, "Firma webhook non valida")
    event = assert_test(event)
    if db.get(BillingEvent, event["id"]):
        return {"ok": True, "duplicate": True}
    data = event["data"]["object"]
    customer = object_id(data.get("customer"))
    user = db.query(User).filter(User.stripe_customer_id == customer, User.billing_source == "stripe_test").with_for_update().populate_existing().first() if customer else None
    if not user or user.id not in config.BILLING_TEST_USER_IDS:
        return {"ok": True, "ignored": True}
    if db.get(BillingEvent, event["id"]):
        return {"ok": True, "duplicate": True}
    event_type = event["type"]
    # Read current Stripe state, never overwrite it with an older event snapshot.
    select_current_subscription(stripe, user)
    if event_type.startswith("customer.subscription."):
        if user.stripe_subscription_id and user.stripe_subscription_id != data["id"]:
            return {"ok": True, "ignored": True}
        user.stripe_subscription_id = data["id"]
    elif event_type == "checkout.session.completed":
        sub_id = object_id(data.get("subscription"))
        if sub_id and (not user.stripe_subscription_id or user.stripe_subscription_id == sub_id):
            user.stripe_subscription_id = sub_id
            user.billing_checkout_expires = None
    if user.stripe_subscription_id:
        reconcile(db, user, stripe)

    paid_invoice = None
    if event_type.startswith("invoice."):
        paid_invoice = assert_test(stripe.Invoice.retrieve(data["id"]))
        sync_invoice(db, user, paid_invoice)

    # La notifica commerciale è legata al primo invoice realmente pagato.
    # BillingNotice rende l'evento unico anche se Stripe invia più webhook
    # o se reconcile ha già sincronizzato la stessa fattura.
    first_payment_notice = None
    if paid_invoice and paid_invoice.get("status") == "paid" and (paid_invoice.get("amount_paid") or 0) > 0:
        notice_key = "superadmin_first_payment"
        first_payment_notice = db.query(BillingNotice).filter_by(user_id=user.id, notice_key=notice_key).first()
        if not first_payment_notice:
            first_payment_notice = BillingNotice(user_id=user.id, notice_key=notice_key)
            db.add(first_payment_notice)

    db.add(BillingEvent(event_id=event["id"], event_type=event_type))
    should_notify_first_payment = bool(first_payment_notice and first_payment_notice.id is None)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not db.get(BillingEvent, event["id"]):
            raise
        should_notify_first_payment = False

    if should_notify_first_payment:
        profile = db.query(SuperAdminProfile).filter(SuperAdminProfile.username == (config.SUPERADMIN_USERNAME or "admin")).first()
        notify_enabled = bool(profile.notify_new_payments) if profile else True
        admin_email = ((profile.email if profile else None) or config.ERROR_NOTIFICATIONS_EMAIL or "").strip()
        if notify_enabled and admin_email:
            from ..services.email import send_new_paying_customer
            send_new_paying_customer(
                to_email=admin_email,
                customer_code=f"{user.customer_number:04d}" if user.customer_number is not None else str(user.id),
                company_name=user.company_name or user.username,
                account_email=user.company_email or user.email or "",
                plan=user.plan or "starter",
                amount=(paid_invoice.get("amount_paid") or 0) / 100,
                currency=(paid_invoice.get("currency") or "eur").upper(),
                is_test=True,
            )
    return {"ok": True}
