"""Daily reminder worker. Explicit --send is required by the CLI."""
from datetime import datetime, timedelta
from html import escape
from ..core.config import APP_BASE_URL
from ..models import User, BillingNotice
from .email import _send, _base_template


def due_notice(user, now):
    if user.plan_status == "trial" and user.trial_ends_at:
        if user.trial_ends_at <= now:
            return f"trial-ended:{user.trial_ends_at.date()}", "Prova gratuita terminata", "Puoi consultare ed esportare i dati e terminare i giri già avviati. Nessun addebito è stato effettuato."
        if user.trial_ends_at <= now + timedelta(days=3):
            return f"trial-ending:{user.trial_ends_at.date()}", "La prova gratuita sta per terminare", "La prova termina entro tre giorni. Non è previsto alcun addebito automatico."
    if user.plan_status == "past_due" and user.billing_grace_until:
        return f"payment:{user.billing_grace_until.isoformat()}", "Pagamento da completare", f"Aggiorna il metodo di pagamento. La tolleranza termina il {user.billing_grace_until:%d/%m/%Y}."
    if user.billing_cancel_at_period_end and user.plan_expires_at:
        return f"cancel:{user.plan_expires_at.isoformat()}", "Disdetta registrata", f"Il piano rimane disponibile fino al {user.plan_expires_at:%d/%m/%Y}."
    return None


def send_due_notices(db, send=False):
    now, result = datetime.utcnow(), {"due": 0, "sent": 0, "failed": 0}
    for user in db.query(User).order_by(User.id).with_for_update().all():
        notice = due_notice(user, now)
        if not notice:
            continue
        key, subject, message = notice
        if db.query(BillingNotice).filter_by(user_id=user.id, notice_key=key).first():
            continue
        result["due"] += 1
        if not send:
            continue
        prefix = "[PROVA] " if user.billing_source == "stripe_test" else ""
        address = user.company_email or user.email
        body = f'<p>{escape(message)}</p><p><a href="{escape(APP_BASE_URL, quote=True)}/dashboard">Apri GiroFacile</a></p>'
        if address and _send(address, prefix + subject, _base_template(body)):
            db.add(BillingNotice(user_id=user.id, notice_key=key))
            db.flush()
            result["sent"] += 1
        else:
            result["failed"] += 1
    db.commit()
    return result
