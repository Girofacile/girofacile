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


def test_sandbox_subscription_does_not_block_live_purchase(billing_env, live, monkeypatch):
    """Account usato per il collaudo: abbonamento sandbox attivo, poi si passa ai pagamenti reali."""
    from app.services import billing
    client, db, user, *_ = billing_env
    user.plan, user.plan_status = 'pro', 'active'
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_source = 'cus_sandbox', 'sub_sandbox', 'stripe_test'
    db.commit()
    state = client.get('/api/billing/my-plan').json()['billing']
    # La pagina non tenta un cambio piano su un abbonamento che su Stripe reale non esiste.
    assert state['subscription'] is False and state['checkout_enabled'] is True
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: webhook_stripe({}))
    monkeypatch.setattr(billing, 'reconcile', lambda *a: pytest.fail('nessuna lettura dell\'abbonamento sandbox'))
    synced = client.post('/api/billing/sync', json={})
    assert synced.status_code == 200, synced.text
    configure_prices(monkeypatch)
    calls, sessions = [], {}
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: live_stripe(calls, sessions))
    bought = client.post('/api/billing/create-checkout-session', json={'plan': 'starter'})
    assert bought.status_code == 200 and bought.json()['mode'] == 'live'
    db.refresh(user)
    assert (user.stripe_customer_id, user.billing_source) == ('cus_live', 'stripe_live')


def pending_subscription(user, state):
    from datetime import datetime, timedelta
    end = int((datetime.now() + timedelta(days=30)).timestamp())
    sub = {'id': 'sub_live', 'customer': user.stripe_customer_id, 'livemode': True, 'status': 'active',
           'collection_method': 'charge_automatically', 'cancel_at_period_end': True,
           'items': {'data': [{'id': 'si_live', 'quantity': 1, 'price': {'id': 'price_starter'}, 'current_period_end': end}]},
           'latest_invoice': {'id': 'in_change', 'status': state['invoice'], 'amount_due': 2999,
                              'billing_reason': 'subscription_update', 'hosted_invoice_url': 'https://invoice.stripe.com/i/change'}}
    if state['pending']:
        sub['pending_update'] = {'expires_at': 1795122331, 'subscription_items': [{'id': 'si_live', 'price': {'id': 'price_business'}}]}
    return sub


def test_closed_payment_page_of_a_plan_change_can_be_resumed_or_cancelled(billing_env, live, monkeypatch):
    """Cambio a Business avviato, pagina di pagamento chiusa: prima il portale restava bloccato."""
    from app.services import billing
    client, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    user.plan, user.plan_status = 'starter', 'active'
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_source = 'cus_live', 'sub_live', 'stripe_live'
    db.commit()
    state, voided = {'pending': True, 'invoice': 'open', 'void_discards': True}, []

    def void_invoice(invoice_id):
        voided.append(invoice_id)
        state['invoice'] = 'void'
        state['pending'] = not state['void_discards']

    fake = SimpleNamespace(
        Subscription=SimpleNamespace(retrieve=lambda *a, **k: pending_subscription(user, state)),
        Invoice=SimpleNamespace(void_invoice=void_invoice),
        checkout=SimpleNamespace(Session=SimpleNamespace(retrieve=lambda id: {}, expire=lambda id: None)))
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: fake)
    monkeypatch.setattr(billing, 'price_for', lambda stripe, plan: 'price_' + plan)

    preview = client.post('/api/billing/change-preview', json={'plan': 'business'})
    assert preview.status_code == 200, preview.text
    assert preview.json() | {} == {'direction': 'pending', 'plan': 'business', 'plan_name': 'Business',
                                   'payment_url': 'https://invoice.stripe.com/i/change', 'amount_due_cents': 2999,
                                   'invoice_id': 'in_change', 'expires_at': 1795122331}
    db.refresh(user)
    assert user.plan == 'starter'  # il cambio non pagato non dà il nuovo piano

    cancelled = client.post('/api/billing/cancel-checkout', json={})
    assert cancelled.status_code == 200 and cancelled.json()['message'] == 'Cambio piano in attesa annullato'
    assert voided == ['in_change']
    assert client.post('/api/billing/cancel-checkout', json={}).json()['message'] == 'Nessun pagamento in sospeso'

    # Se Stripe non scarta il cambio, si dice chiaramente invece di far credere che sia annullato.
    state.update(pending=True, invoice='open', void_discards=False)
    stuck = client.post('/api/billing/cancel-checkout', json={})
    assert stuck.status_code == 409 and 'non si è annullato' in stuck.json()['detail']


def test_discarded_plan_change_keeps_the_paid_plan_active(billing_env, live, monkeypatch):
    """Dopo l'annullamento di un cambio piano la fattura annullata non blocca il piano già pagato."""
    from app.services.billing import sync_subscription
    client, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    user.plan, user.plan_status = 'starter', 'active'
    user.stripe_customer_id, user.stripe_subscription_id, user.billing_source = 'cus_live', 'sub_live', 'stripe_live'
    sync_subscription(db, user, pending_subscription(user, {'pending': False, 'invoice': 'void'}))
    assert (user.plan, user.plan_status) == ('starter', 'active')
    # Anche chi era già stato segnato «incompleto» per errore torna attivo alla sincronizzazione.
    user.plan_status = 'incomplete'
    sync_subscription(db, user, pending_subscription(user, {'pending': False, 'invoice': 'void'}))
    assert user.plan_status == 'active'
    # Un conguaglio ancora da pagare, invece, non attiva nulla.
    user.plan_status = 'incomplete'
    sync_subscription(db, user, pending_subscription(user, {'pending': False, 'invoice': 'open'}))
    assert user.plan_status == 'incomplete'


def _admin(env):
    from app.core.dependencies import require_superadmin
    from app.routers.admin_users import router
    client = env[0]
    client.app.include_router(router)
    client.app.dependency_overrides[require_superadmin] = lambda: {
        "username": "test-admin", "role": "superadmin", "permissions": {"all": True}}


def _pages(items):
    return SimpleNamespace(auto_paging_iter=lambda: iter(items))


@pytest.mark.parametrize('case', ['open_checkout', 'paid_meanwhile', 'live_subscription', 'open_invoice', 'draft_invoice'])
def test_free_access_closes_open_stripe_payments_first(billing_env, live, monkeypatch, case):
    """Accesso gratuito con un checkout ancora aperto: la pagina Stripe si chiude prima di scollegare."""
    from app.services import billing
    client, db, user, *_ = billing_env
    _admin(billing_env)
    user.plan, user.plan_status = 'starter', 'trial'
    user.stripe_customer_id, user.billing_source = 'cus_live', 'stripe_live'
    user.billing_checkout_id = 'cs_live'
    db.commit()
    expired = []

    def expire(session_id):
        if case == 'paid_meanwhile':
            raise RuntimeError('session already complete')
        expired.append(session_id)

    subs = [{'id': 'sub_x', 'livemode': True, 'status': 'active', 'cancel_at_period_end': False}] if case == 'live_subscription' else []
    fake = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(
            list=lambda **k: _pages([{'id': 'cs_live', 'livemode': True, 'status': 'open'}]), expire=expire)),
        Subscription=SimpleNamespace(list=lambda **k: _pages(subs)),
        # Rinnovo in ritardo con disdetta programmata: la fattura resta pagabile.
        Invoice=SimpleNamespace(list=lambda **k: _pages(
            [{'id': 'in_late', 'number': 'GF-7', 'livemode': True, 'status': k['status']}] if case == k['status'] + '_invoice' else [])))
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: fake)
    response = client.put(f'/api/admin/users/{user.id}/plan', json={'plan': 'pro', 'complimentary': True})
    db.refresh(user)
    if case == 'open_checkout':
        assert response.status_code == 200, response.text
        assert expired == ['cs_live']
        assert (user.billing_source, user.stripe_customer_id, user.billing_checkout_id) == ('complimentary', None, None)
    else:
        assert response.status_code == 409
        assert (user.billing_source, user.stripe_customer_id) == ('stripe_live', 'cus_live')
        if case.endswith('_invoice'):
            assert 'GF-7' in response.json()['detail']


def test_old_invoices_stay_downloadable_after_free_access(billing_env, live, monkeypatch):
    from app.models import BillingInvoice
    from app.services import billing
    client, db, user, *_ = billing_env
    user.stripe_customer_id, user.billing_source = None, 'complimentary'
    row = BillingInvoice(user_id=user.id, invoice_number='GF-1', stripe_invoice_id='in_old', is_test=False)
    sandbox = BillingInvoice(user_id=user.id, invoice_number='GF-T', stripe_invoice_id='in_sandbox', is_test=True)
    db.add_all([row, sandbox]); db.commit()
    fake = SimpleNamespace(Invoice=SimpleNamespace(retrieve=lambda id: {
        'id': id, 'livemode': True, 'customer': 'cus_old', 'invoice_pdf': 'https://pay.stripe.com/invoice/old/pdf'}))
    monkeypatch.setattr(billing, 'stripe_client', lambda *a: fake)
    response = client.get(f'/api/billing/invoices/{row.id}/download', follow_redirects=False)
    assert response.status_code in (302, 307) and response.headers['location'].endswith('/pdf')
    assert client.get(f'/api/billing/invoices/{sandbox.id}/download', follow_redirects=False).status_code == 404
