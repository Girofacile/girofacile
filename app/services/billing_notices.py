"""Promemoria giornalieri su prova e abbonamento. Lo script invia solo con --send."""
from datetime import datetime, timedelta
from ..core.clock import utc_now
from html import escape
from ..core import config
from ..core.config import APP_BASE_URL
from ..core.links import base_url as _links_base_url
from ..core.dependencies import is_admin_user
from ..models import User, BillingNotice
from .email import _send, _base_template


# Un avviso di fine prova arriva solo se la prova è finita da poco: alla prima attivazione
# dei promemoria non si scrive ad aziende la cui prova è scaduta settimane fa.
TRIAL_ENDED_NOTICE_DAYS = 7


def _buy_hint():
    return " Per continuare acquista il piano dalla pagina Piani." if config.BILLING_MODE == "live" else ""


def due_notice(user, now):
    if user.plan_status == "trial" and user.trial_ends_at:
        if user.trial_ends_at <= now:
            if now - user.trial_ends_at > timedelta(days=TRIAL_ENDED_NOTICE_DAYS):
                return None
            return (f"trial-ended:{user.trial_ends_at.date()}", "Prova gratuita terminata",
                    "Puoi consultare ed esportare i dati e terminare i giri già avviati. Nessun addebito è stato effettuato." + _buy_hint())
        if user.trial_ends_at <= now + timedelta(days=3):
            return (f"trial-ending:{user.trial_ends_at.date()}", "La prova gratuita sta per terminare",
                    "La prova termina entro tre giorni. Non è previsto alcun addebito automatico." + _buy_hint())
    if user.plan_status == "past_due" and user.billing_grace_until:
        return f"payment:{user.billing_grace_until.isoformat()}", "Pagamento da completare", f"Aggiorna il metodo di pagamento. La tolleranza termina il {user.billing_grace_until:%d/%m/%Y}."
    if user.billing_cancel_at_period_end and user.plan_expires_at:
        return f"cancel:{user.plan_expires_at.isoformat()}", "Disdetta registrata", f"Il piano rimane disponibile fino al {user.plan_expires_at:%d/%m/%Y}."
    return None


def send_due_notices(db, send=False):
    now, result = utc_now(), {"due": 0, "sent": 0, "failed": 0}
    ids = [row[0] for row in db.query(User.id).order_by(User.id).all()]
    for user_id in ids:
        # Un'azienda alla volta: il blocco dura il tempo del suo invio, non di tutto il giro.
        user = db.query(User).filter(User.id == user_id).with_for_update().populate_existing().first()
        notice = None if not user or user.billing_suspended or is_admin_user(user) else due_notice(user, now)
        if not notice or db.query(BillingNotice).filter_by(user_id=user.id, notice_key=notice[0]).first():
            db.rollback()
            continue
        key, subject, message = notice
        result["due"] += 1
        if not send:
            db.rollback()
            continue
        prefix = "[PROVA] " if user.billing_source == "stripe_test" else ""
        address = user.company_email or user.email
        body = f'<p>{escape(message)}</p><p><a href="{escape(_links_base_url(APP_BASE_URL, "app"), quote=True)}/dashboard">Apri GiroFacile</a></p>'
        if address and _send(address, prefix + subject, _base_template(body)):
            db.add(BillingNotice(user_id=user.id, notice_key=key))
            result["sent"] += 1
        else:
            result["failed"] += 1
        db.commit()
    return result
