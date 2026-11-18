"""Promemoria di prova e abbonamento: chi li riceve, quando e con quale testo."""
from datetime import timedelta

import pytest

from app.core.clock import utc_now
from test_agents_feature import env  # noqa: F401


@pytest.fixture
def notices(env, monkeypatch):
    from app.services import billing_notices
    _, db, user, other, *_ = env
    sent = []
    monkeypatch.setattr(billing_notices, '_send', lambda to, subject, body: sent.append((to, subject, body)) or True)
    for company, mail in ((user, 'titolare@example.test'), (other, 'altra@example.test')):
        company.email = mail
        company.plan_status = 'active'
    db.commit()
    return billing_notices, db, user, other, sent


def test_trial_ended_long_ago_is_not_notified_at_first_activation(notices):
    billing_notices, db, user, other, sent = notices
    user.plan_status = other.plan_status = 'trial'
    user.trial_ends_at = utc_now() - timedelta(days=2)
    other.trial_ends_at = utc_now() - timedelta(days=40)
    db.commit()
    assert billing_notices.send_due_notices(db, send=False) == {'due': 1, 'sent': 0, 'failed': 0}
    assert not sent
    assert billing_notices.send_due_notices(db, send=True)['sent'] == 1
    assert [(to, subject) for to, subject, _ in sent] == [('titolare@example.test', 'Prova gratuita terminata')]
    assert billing_notices.send_due_notices(db, send=True)['due'] == 0


@pytest.mark.parametrize('mode,hint', [('live', True), ('disabled', False), ('test', False)])
def test_purchase_hint_only_when_real_payments_are_on(notices, monkeypatch, mode, hint):
    from app.core import config
    billing_notices, db, user, other, sent = notices
    monkeypatch.setattr(config, 'BILLING_MODE', mode)
    user.plan_status = 'trial'
    user.trial_ends_at = utc_now() + timedelta(days=2)
    db.commit()
    billing_notices.send_due_notices(db, send=True)
    assert [subject for _, subject, _ in sent] == ['La prova gratuita sta per terminare']
    assert ('acquista il piano dalla pagina Piani' in sent[0][2]) is hint
    assert 'IVA' not in sent[0][2]


def test_suspended_companies_and_admin_receive_nothing(notices, monkeypatch):
    from app.core import dependencies
    billing_notices, db, user, other, sent = notices
    for company in (user, other):
        company.plan_status = 'trial'
        company.trial_ends_at = utc_now() + timedelta(days=1)
    user.billing_suspended = True
    monkeypatch.setattr(dependencies, 'APP_USER', other.username)
    db.commit()
    assert billing_notices.send_due_notices(db, send=True) == {'due': 0, 'sent': 0, 'failed': 0}
    assert not sent


def test_failed_send_is_retried_next_day(notices, monkeypatch):
    billing_notices, db, user, other, sent = notices
    user.plan_status = 'trial'
    user.trial_ends_at = utc_now() + timedelta(days=1)
    db.commit()
    monkeypatch.setattr(billing_notices, '_send', lambda *a: False)
    assert billing_notices.send_due_notices(db, send=True)['failed'] == 1
    monkeypatch.setattr(billing_notices, '_send', lambda to, subject, body: sent.append(to) or True)
    assert billing_notices.send_due_notices(db, send=True)['sent'] == 1
    assert sent == ['titolare@example.test']
