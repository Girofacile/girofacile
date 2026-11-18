"""Pagamenti reali (BILLING_MODE=live): aperti a ogni azienda, mai mescolati con la sandbox."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_billing import billing_env, configure_prices  # noqa: F401
from test_agents_feature import env  # noqa: F401


@pytest.fixture
def live(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config, 'BILLING_MODE', 'live')
    monkeypatch.setattr(config, 'STRIPE_SECRET_KEY', 'sk_live_x')
    monkeypatch.setattr(config, 'STRIPE_WEBHOOK_SECRET', 'whsec_live')
    monkeypatch.setattr(config, 'BILLING_TEST_USER_IDS', set())
    return config


def test_live_mode_opens_purchases_to_every_company(live):
    from app.services.billing import stripe_client, billing_available, billing_source
    stripe = stripe_client(SimpleNamespace(id=999))
    assert stripe.api_key == 'sk_live_x'
    assert billing_available(SimpleNamespace(id=999)) and billing_source() == 'stripe_live'


def test_live_mode_accepts_only_live_objects(live):
    from app.services.billing import assert_test
    assert assert_test({'livemode': True})['livemode'] is True
    for obj in ({'livemode': False}, {}):
        with pytest.raises(HTTPException):
            assert_test(obj)


def test_billing_state_offers_checkout_in_live(billing_env, live):
    client, db, user, *_ = billing_env
    state = client.get('/api/billing/my-plan').json()['billing']
    assert state['checkout_enabled'] is True and state['live_enabled'] is True and state['mode'] == 'live'


def live_stripe(calls, sessions):
    def create_customer(**kwargs):
        calls.append(('customer', kwargs))
        return {'id': 'cus_live', 'livemode': True}

    def create_session(**kwargs):
        calls.append(('session', kwargs))
        session = {'id': 'cs_live', 'livemode': True, 'status': 'open', 'url': 'https://checkout.stripe.com/live',
                   'metadata': kwargs['metadata'], 'expires_at': kwargs['expires_at']}
        sessions['cs_live'] = session
        return session

    return SimpleNamespace(
        Price=SimpleNamespace(retrieve=lambda id: {'id': id, 'livemode': True, 'active': True, 'currency': 'eur',
                                                   'unit_amount': 2900, 'recurring': {'interval': 'month', 'interval_count': 1}}),
        Customer=SimpleNamespace(create=create_customer),
        Subscription=SimpleNamespace(list=lambda **k: SimpleNamespace(auto_paging_iter=lambda: iter([]))),
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create_session, retrieve=lambda id: sessions[id])))


def test_live_checkout_replaces_sandbox_customer_and_collects_invoice_data(billing_env, live, monkeypatch):
    from app.services import billing
    client, db, user, *_ = billing_env
    user.plan_status = 'trial'
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_source = 'cus_sandbox', 'sub_sandbox', 'stripe_test'
    db.commit()
    configure_prices(monkeypatch)
    calls, sessions = [], {}
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: live_stripe(calls, sessions))
    response = client.post('/api/billing/create-checkout-session', json={'plan': 'starter'})
    assert response.status_code == 200, response.text
    assert response.json() == {'checkout_url': 'https://checkout.stripe.com/live', 'mode': 'live'}
    db.refresh(user)
    assert (user.stripe_customer_id, user.stripe_subscription_id, user.billing_source) == ('cus_live', None, 'stripe_live')
    assert user.plan_status == 'trial'  # il ritorno dal checkout non attiva nulla
    session = [kwargs for kind, kwargs in calls if kind == 'session'][0]
    assert session['billing_address_collection'] == 'required'
    assert session['tax_id_collection'] == {'enabled': True}
    assert session['customer_update'] == {'name': 'auto', 'address': 'auto'}
    customer = [kwargs for kind, kwargs in calls if kind == 'customer'][0]
    assert customer['idempotency_key'] == f'gf-live-customer-{user.id}'


def test_live_checkout_refuses_sandbox_prices(billing_env, live, monkeypatch):
    from app.services import billing
    client, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    fake = live_stripe([], {})
    fake.Price.retrieve = lambda id: {'id': id, 'livemode': False, 'active': True, 'currency': 'eur', 'unit_amount': 2900,
                                      'recurring': {'interval': 'month', 'interval_count': 1}}
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: fake)
    assert client.post('/api/billing/create-checkout-session', json={'plan': 'starter'}).status_code == 400


def test_live_invoice_counts_as_real_receipt(billing_env, live):
    from app.services.billing import sync_invoice
    from app.models import BillingInvoice, BillingPayment
    _, db, user, *_ = billing_env
    user.stripe_customer_id = 'cus_live'
    sync_invoice(db, user, {'id': 'in_live', 'customer': 'cus_live', 'livemode': True, 'status': 'paid', 'total': 2900,
                            'subtotal': 2900, 'amount_paid': 2900, 'currency': 'eur', 'created': 100,
                            'status_transitions': {'paid_at': 100}})
    db.commit()
    payment = db.query(BillingPayment).one()
    assert not payment.is_test and payment.payment_method == 'Stripe' and payment.amount == 29
    assert not db.query(BillingInvoice).one().is_test


def webhook_stripe(event):
    return SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda *a: event),
                           Subscription=SimpleNamespace(list=lambda **k: SimpleNamespace(auto_paging_iter=lambda: iter([]))))


def test_live_webhook_serves_every_live_company_and_ignores_sandbox_ones(billing_env, live, monkeypatch):
    from app.services import billing
    client, db, user, other, *_ = billing_env
    user.billing_source, user.stripe_customer_id, user.stripe_subscription_id = 'stripe_live', 'cus_live', 'sub_live'
    other.billing_source, other.stripe_customer_id, other.stripe_subscription_id = 'stripe_test', 'cus_sandbox', 'sub_sandbox'
    db.commit()
    synced = []
    monkeypatch.setattr(billing, 'reconcile', lambda db, u, stripe: synced.append(u.id))
    event = {'id': 'evt_live', 'livemode': True, 'type': 'customer.subscription.updated',
             'data': {'object': {'id': 'sub_live', 'customer': 'cus_live', 'status': 'active'}}}
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: webhook_stripe(event))
    assert client.post('/api/billing/webhook', content=b'x').json() == {'ok': True}
    assert synced == [user.id]
    sandbox = {'id': 'evt_sandbox', 'livemode': True, 'type': 'customer.subscription.updated',
               'data': {'object': {'id': 'sub_sandbox', 'customer': 'cus_sandbox', 'status': 'active'}}}
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: webhook_stripe(sandbox))
    assert client.post('/api/billing/webhook', content=b'x').json()['ignored']
    sandbox_event = dict(event, id='evt_test', livemode=False)
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: webhook_stripe(sandbox_event))
    assert client.post('/api/billing/webhook', content=b'x').status_code == 400
    assert synced == [user.id]


LIVE_ENV = {'APP_ENV': 'production', 'BILLING_MODE': 'live', 'STRIPE_SECRET_KEY': 'sk_live_x',
            'STRIPE_WEBHOOK_SECRET': 'whsec_x', 'STRIPE_PRICE_STARTER': 'price_s',
            'STRIPE_PRICE_BUSINESS': 'price_b', 'STRIPE_PRICE_PRO': 'price_p'}


@pytest.mark.parametrize('changes,message', [
    ({}, None),
    ({'BILLING_MODE': 'disabled', 'STRIPE_SECRET_KEY': 'sk_test_x'}, None),
    ({'BILLING_MODE': 'reale'}, 'BILLING_MODE non valido'),
    ({'STRIPE_SECRET_KEY': 'sk_test_x'}, 'sk_live_'),
    ({'STRIPE_WEBHOOK_SECRET': ''}, 'STRIPE_WEBHOOK_SECRET'),
    ({'STRIPE_PRICE_PRO': ' '}, 'STRIPE_PRICE_PRO'),
    ({'BILLING_MODE': 'test'}, 'sk_test_'),
])
def test_billing_configuration_is_checked_at_startup(changes, message):
    from app.core.environment import invalid_settings
    problems = invalid_settings({**LIVE_ENV, **changes})
    if message is None:
        assert problems == []
    else:
        assert any(message in p for p in problems), problems
