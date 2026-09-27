"""Sandbox-only billing. Stripe is the authority; redirects never grant access."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func

from ..core import config
from ..models import User, BillingInvoice, BillingPayment, Customer, Driver, Vehicle, Deposit
from .plan_catalog import PLAN_PRICES, PLAN_LIMITS, GRACE_DAYS


def utc(timestamp):
    return datetime.fromtimestamp(int(timestamp), timezone.utc).replace(tzinfo=None) if timestamp else None


def object_id(value):
    return value.get("id") if isinstance(value, dict) else value


def stripe_client(user=None):
    # Live mode intentionally cannot be enabled in this release, even by a live key.
    if config.BILLING_MODE != "test":
        raise HTTPException(503, "Acquisti non disponibili: incassi reali disabilitati")
    if user is not None and user.id not in config.BILLING_TEST_USER_IDS:
        raise HTTPException(403, "Checkout di prova riservato agli account di collaudo")
    if not config.STRIPE_SECRET_KEY.startswith(("sk_test_", "rk_test_")):
        raise HTTPException(503, "Configurare una chiave Stripe sandbox")
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    stripe.api_version = config.STRIPE_API_VERSION
    stripe.max_network_retries = 2
    return stripe


def stripe_dict(obj):
    """Normalize SDK 15 resources, including nested expanded objects."""
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def assert_test(obj):
    obj = stripe_dict(obj)
    if obj.get("livemode") is not False:
        raise HTTPException(400, "Oggetto Stripe non appartenente alla sandbox")
    return obj


def price_for(stripe, plan):
    if not isinstance(plan, str) or plan not in PLAN_PRICES:
        raise HTTPException(400, "Piano non valido")
    info = PLAN_PRICES[plan]
    if not info["stripe_price_id"]:
        raise HTTPException(503, "Prezzo sandbox non configurato per il piano")
    price = assert_test(stripe.Price.retrieve(info["stripe_price_id"]))
    recurring = price.get("recurring") or {}
    if (not price.get("active") or price.get("currency") != "eur"
            or price.get("unit_amount") != info["price_cents"]
            or recurring.get("interval") != "month" or recurring.get("interval_count") != 1):
        raise HTTPException(503, "Il prezzo Stripe non corrisponde al listino mensile GiroFacile")
    return price["id"]


def lock_user(db, user):
    return db.query(User).filter(User.id == user.id).with_for_update().populate_existing().one()


def retrieve_subscription(stripe, user):
    if not user.stripe_subscription_id or user.billing_source != "stripe_test":
        raise HTTPException(400, "Nessun abbonamento di prova collegato")
    sub = assert_test(stripe.Subscription.retrieve(user.stripe_subscription_id, expand=["latest_invoice"]))
    if object_id(sub.get("customer")) != user.stripe_customer_id:
        raise HTTPException(409, "Abbonamento non associato all'azienda")
    return sub


def subscription_plan(sub):
    items = sub.get("items", {}).get("data", [])
    if len(items) != 1 or items[0].get("quantity", 1) != 1:
        raise HTTPException(409, "Struttura abbonamento non riconosciuta")
    price_id = object_id(items[0].get("price"))
    for key, info in PLAN_PRICES.items():
        if info["stripe_price_id"] and price_id == info["stripe_price_id"]:
            return key
    raise HTTPException(409, "Prezzo abbonamento non presente nel catalogo")


def sync_subscription(db, user, sub):
    sub = assert_test(sub)
    if object_id(sub.get("customer")) != user.stripe_customer_id:
        raise HTTPException(409, "Cliente Stripe non corrispondente")
    plan = subscription_plan(sub)
    status = sub.get("status")
    item = sub["items"]["data"][0]
    end = utc(item.get("current_period_end") or sub.get("current_period_end"))
    user.stripe_subscription_id = sub["id"]
    user.billing_source = "stripe_test"
    user.billing_cancel_at_period_end = bool(sub.get("cancel_at_period_end"))
    user.plan_expires_at = end
    if status == "active":
        invoice = sub.get("latest_invoice")
        if sub.get("pending_update"):
            # The previous paid plan stays usable while the upgrade is unpaid.
            return user
        # Never activate an unpaid upgrade or an invoice-based subscription.
        if sub.get("collection_method") != "charge_automatically" or not isinstance(invoice, dict) or invoice.get("status") != "paid":
            user.plan_status = "incomplete"
        else:
            user.plan = plan
            user.plan_status = "active"
            user.billing_grace_until = None
            if user.billing_pending_plan == plan:
                user.billing_pending_plan = None
    elif status in ("past_due", "unpaid"):
        # Only customers with a previously paid subscription receive grace.
        if user.plan_status in ("active", "past_due"):
            if user.billing_grace_until is None:
                invoice = sub.get("latest_invoice") or {}
                failed_at = utc(invoice.get("created")) if isinstance(invoice, dict) else None
                user.billing_grace_until = (failed_at or datetime.utcnow()) + timedelta(days=GRACE_DAYS)
            user.plan_status = "past_due"
        else:
            user.plan_status = "incomplete"
    else:
        user.plan_status = {"canceled": "cancelled", "unpaid": "expired", "incomplete_expired": "expired"}.get(status, "incomplete")
        user.billing_grace_until = None
    return user


def sync_invoice(db, user, invoice):
    invoice = assert_test(invoice)
    if object_id(invoice.get("customer")) != user.stripe_customer_id:
        raise HTTPException(409, "Documento non associato all'azienda")
    row = db.query(BillingInvoice).filter_by(stripe_invoice_id=invoice["id"]).first()
    if not row:
        row = BillingInvoice(user_id=user.id, stripe_invoice_id=invoice["id"], invoice_number=invoice.get("number") or invoice["id"])
        db.add(row)
    row.invoice_number = invoice.get("number") or invoice["id"]
    row.invoice_date = utc(invoice.get("created")) or datetime.utcnow()
    row.period_start, row.period_end = utc(invoice.get("period_start")), utc(invoice.get("period_end"))
    row.plan_name = PLAN_LIMITS[user.plan]["name"]
    row.subtotal, row.total = (invoice.get("subtotal") or 0) / 100, (invoice.get("total") or 0) / 100
    row.vat_amount = sum(t.get("amount", 0) for t in (invoice.get("total_taxes") or invoice.get("total_tax_amounts") or [])) / 100
    row.currency, row.status, row.pdf_path, row.is_test = invoice.get("currency", "eur").upper(), invoice.get("status", "open"), invoice.get("invoice_pdf"), True
    db.flush()
    payment = db.query(BillingPayment).filter_by(user_id=user.id, transaction_id=invoice["id"]).first()
    if invoice.get("status") == "paid" or invoice.get("attempted"):
        if not payment:
            payment = BillingPayment(user_id=user.id, invoice_id=row.id, transaction_id=invoice["id"])
            db.add(payment)
        payment.amount = (invoice.get("amount_paid") or 0) / 100
        payment.currency, payment.payment_method, payment.is_test = row.currency, "Stripe sandbox", True
        payment.payment_status = "paid" if invoice.get("status") == "paid" else "failed"
        payment.paid_at = utc((invoice.get("status_transitions") or {}).get("paid_at"))


def reconcile(db, user, stripe=None):
    stripe = stripe or stripe_client(user)
    sub = retrieve_subscription(stripe, user)
    sync_subscription(db, user, sub)
    invoices = stripe.Invoice.list(customer=user.stripe_customer_id, subscription=sub["id"], limit=100)
    for invoice in invoices.auto_paging_iter():
        sync_invoice(db, user, invoice)
    return sub


def select_current_subscription(stripe, user):
    """Find the current subscription, including repurchases after cancellation."""
    if not user.stripe_customer_id or user.billing_source != "stripe_test":
        return
    subscriptions = stripe.Subscription.list(customer=user.stripe_customer_id, status="all", limit=100)
    candidates = (assert_test(s) for s in subscriptions.auto_paging_iter())
    active = [s for s in candidates if s.get("status") not in ("canceled", "incomplete_expired")]
    if len(active) > 1:
        raise HTTPException(409, "Più abbonamenti rilevati: contattare l'assistenza")
    if active:
        user.stripe_subscription_id = active[0]["id"]


def checkout(db, user, plan):
    stripe = stripe_client(user)
    user = lock_user(db, user)
    price = price_for(stripe, plan)
    if user.stripe_customer_id and user.billing_source != "stripe_test":
        raise HTTPException(409, "Account storico: collegare un account dedicato al collaudo")
    if not user.stripe_customer_id:
        customer = assert_test(stripe.Customer.create(email=user.company_email or user.email,
            name=user.company_name or user.username, metadata={"user_id": str(user.id)},
            idempotency_key=f"gf-test-customer-{user.id}"))
        user.stripe_customer_id, user.billing_source = customer["id"], "stripe_test"
        db.commit()
        user = lock_user(db, user)
    subs = stripe.Subscription.list(customer=user.stripe_customer_id, status="all", limit=100)
    for sub in subs.auto_paging_iter():
        sub = stripe_dict(sub)
        if sub.get("status") not in ("canceled", "incomplete_expired"):
            user.stripe_subscription_id = sub["id"]
            db.commit()
            raise HTTPException(409, "Abbonamento già presente: aggiorna lo stato o gestisci il piano")
    if user.billing_checkout_id and not user.billing_checkout_id.startswith("pending_") and user.billing_checkout_expires and user.billing_checkout_expires > datetime.utcnow():
        session = assert_test(stripe.checkout.Session.retrieve(user.billing_checkout_id))
        if session.get("status") == "open":
            if (session.get("metadata") or {}).get("plan") == plan:
                return {"checkout_url": session["url"], "mode": "test"}
            raise HTTPException(409, "Checkout già aperto per un altro piano. Annullalo prima di cambiare")
        if session.get("status") == "complete":
            raise HTTPException(409, "Checkout completato: aggiorna lo stato prima di un nuovo acquisto")
    # Persist operation key before HTTP: retry after a crash cannot create two sessions.
    if not user.billing_checkout_expires or user.billing_checkout_expires <= datetime.utcnow():
        user.billing_checkout_id = "pending_" + uuid4().hex
        user.billing_checkout_plan = plan
        user.billing_checkout_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        user = lock_user(db, user)
    key = user.billing_checkout_id
    if key.startswith("pending_") and user.billing_checkout_plan != plan:
        raise HTTPException(409, "Checkout in preparazione per un altro piano: annullalo prima di cambiare")
    if not key.startswith("pending_"):
        user.billing_checkout_expires = None
        db.commit()
        return checkout(db, user, plan)
    base = config.APP_BASE_URL.rstrip("/")
    session = assert_test(stripe.checkout.Session.create(customer=user.stripe_customer_id,
        mode="subscription", payment_method_types=["card"], line_items=[{"price": price, "quantity": 1}],
        metadata={"user_id": str(user.id), "plan": plan}, subscription_data={"metadata": {"user_id": str(user.id)}},
        success_url=base + "/dashboard?checkout=success", cancel_url=base + "/dashboard?checkout=cancelled",
        expires_at=int(user.billing_checkout_expires.replace(tzinfo=timezone.utc).timestamp()), idempotency_key=key))
    user.billing_checkout_id, user.billing_checkout_url = session["id"], session["url"]
    user.billing_checkout_expires = utc(session["expires_at"])
    db.commit()
    return {"checkout_url": session["url"], "mode": "test"}


def downgrade_excess(db, user, plan):
    result = []
    for model, key, label in ((Customer, "max_customers", "clienti"), (Vehicle, "max_vehicles", "mezzi"),
                              (Driver, "max_drivers", "autisti"), (Deposit, "max_deposits", "depositi")):
        count = db.query(model).filter(model.user_id == user.id, model.deleted_at.is_(None)).count()
        if count > PLAN_LIMITS[plan][key]:
            result.append(f"{label}: {count}/{PLAN_LIMITS[plan][key]}")
    return result


def change_preview(db, user, plan):
    stripe = stripe_client(user)
    price = price_for(stripe, plan)
    sub = retrieve_subscription(stripe, user)
    current = subscription_plan(sub)
    if sub.get("status") != "active" or sub.get("pending_update") or sub.get("schedule"):
        raise HTTPException(409, "Completa o annulla prima il pagamento/cambio piano pendente")
    if plan == current:
        raise HTTPException(400, "Questo piano è già attivo")
    item = sub["items"]["data"][0]
    if PLAN_PRICES[plan]["price_cents"] < PLAN_PRICES[current]["price_cents"]:
        excess = downgrade_excess(db, user, plan)
        if excess:
            raise HTTPException(409, "Riduci prima le risorse: " + "; ".join(excess))
        return {"direction": "downgrade", "amount_due_cents": 0, "effective_at": item.get("current_period_end"), "subscription": sub}
    timestamp = int(datetime.now(timezone.utc).timestamp())
    invoice = stripe.Invoice.create_preview(customer=user.stripe_customer_id, subscription=sub["id"],
        subscription_details={"items": [{"id": item["id"], "price": price}], "proration_date": timestamp, "proration_behavior": "always_invoice"})
    return {"direction": "upgrade", "amount_due_cents": invoice["amount_due"], "proration_date": timestamp, "subscription": sub}


def change_plan(db, user, plan, preview):
    stripe = stripe_client(user)
    user = lock_user(db, user)
    price = price_for(stripe, plan)
    sub = retrieve_subscription(stripe, user)
    if sub.get("status") != "active" or sub.get("pending_update") or (sub.get("schedule") and user.billing_pending_plan != plan):
        raise HTTPException(409, "Abbonamento non modificabile: aggiorna lo stato")
    item = sub["items"]["data"][0]
    current = subscription_plan(sub)
    if current == plan:
        raise HTTPException(409, "Piano già attivo")
    if PLAN_PRICES[plan]["price_cents"] < PLAN_PRICES[current]["price_cents"]:
        if downgrade_excess(db, user, plan):
            raise HTTPException(409, "Le risorse superano i limiti del piano richiesto")
        if user.billing_pending_plan != plan or not user.billing_change_key:
            user.billing_change_key = uuid4().hex
        user.billing_pending_plan = plan
        db.commit()
        user = lock_user(db, user)
        sub = retrieve_subscription(stripe, user)
        schedule = (stripe.SubscriptionSchedule.retrieve(object_id(sub["schedule"])) if sub.get("schedule") else
                    stripe.SubscriptionSchedule.create(from_subscription=sub["id"], idempotency_key=f"gf-schedule-{sub['id']}-{user.billing_change_key}"))
        stripe.SubscriptionSchedule.modify(schedule["id"], end_behavior="release", phases=[
            {"start_date": schedule["current_phase"]["start_date"], "end_date": item["current_period_end"], "items": [{"price": object_id(item["price"]), "quantity": 1}]},
            {"items": [{"price": price, "quantity": 1}], "iterations": 1, "proration_behavior": "none"}],
            idempotency_key=f"gf-downgrade-{schedule['id']}-{plan}")
        user.billing_pending_plan = plan
        db.commit()
        return {"message": "Passaggio al piano inferiore programmato al rinnovo"}
    try:
        stamp = int(preview.get("proration_date") or 0)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, "Data del preventivo non valida")
    if not 0 <= int(datetime.now(timezone.utc).timestamp()) - stamp <= 300:
        raise HTTPException(409, "Preventivo scaduto: richiedi un nuovo riepilogo")
    invoice = stripe.Invoice.create_preview(customer=user.stripe_customer_id, subscription=sub["id"],
        subscription_details={"items": [{"id": item["id"], "price": price}], "proration_date": stamp, "proration_behavior": "always_invoice"})
    if invoice["amount_due"] != preview.get("amount_due_cents"):
        raise HTTPException(409, "Importo aggiornato: conferma un nuovo riepilogo")
    updated = stripe.Subscription.modify(sub["id"], items=[{"id": item["id"], "price": price}],
        payment_behavior="pending_if_incomplete", proration_behavior="always_invoice", proration_date=stamp,
        expand=["latest_invoice"], idempotency_key=f"gf-upgrade-{sub['id']}-{plan}-{stamp}")
    sync_subscription(db, user, updated)
    db.commit()
    latest = stripe_dict(updated).get("latest_invoice") or {}
    return {"message": "Cambio richiesto: il nuovo piano si attiva dopo il pagamento", "payment_url": latest.get("hosted_invoice_url")}


def cancel_or_resume(db, user, cancel):
    stripe = stripe_client(user)
    user = lock_user(db, user)
    sub = retrieve_subscription(stripe, user)
    if sub.get("schedule"):
        stripe.SubscriptionSchedule.release(object_id(sub["schedule"]))
    updated = stripe.Subscription.modify(sub["id"], cancel_at_period_end=cancel, expand=["latest_invoice"])
    user.billing_pending_plan = None
    user.billing_change_key = None
    sync_subscription(db, user, updated)
    db.commit()
    return {"message": "Disdetta a fine periodo registrata" if cancel else "Rinnovo automatico ripristinato"}
