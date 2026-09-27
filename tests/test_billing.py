"""Billing and operational quota regression tests; no external API or real DB."""
from datetime import datetime, timedelta, date, time
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from test_agents_feature import env


@pytest.fixture
def billing_env(env):
    from app.routers.billing import router
    env[0].app.include_router(router)
    return env


def test_catalog_matches_approved_offer(billing_env):
    client, db, user, *_ = billing_env
    plans = client.get('/api/billing/plans').json()
    assert [p['price_eur'] for p in plans] == [29, 59, 99]
    assert [p['limits']['max_customers'] for p in plans] == [150, 500, 5000]
    assert [p['limits']['max_drivers'] for p in plans] == [3, 10, 50]
    assert [p['limits']['max_deposits'] for p in plans] == [1, 3, 20]
    assert [p['limits']['max_routes_per_month'] for p in plans] == [100, 400, 1500]
    assert [p['limits']['max_deliveries_per_month'] for p in plans] == [2000, 10000, 30000]
    assert [p['limits']['has_ai'] for p in plans] == [False, False, True]
    assert all(p['limits']['has_export'] for p in plans)


def test_old_plan_endpoint_cannot_activate_or_extend_trial(billing_env):
    client, db, user, *_ = billing_env
    user.plan_status = 'expired'; db.commit()
    before = (user.plan, user.plan_status, user.trial_ends_at)
    assert client.post('/api/billing/select-plan', json={'plan':'pro'}).status_code == 410
    assert (user.plan, user.plan_status, user.trial_ends_at) == before


@pytest.mark.parametrize('mode,key', [('disabled','sk_test_x'), ('live','sk_live_x'), ('test','sk_live_x'), ('test','')])
def test_real_payments_fail_closed(monkeypatch, mode, key):
    from app.core import config
    from app.services.billing import stripe_client
    monkeypatch.setattr(config,'BILLING_MODE',mode)
    monkeypatch.setattr(config,'STRIPE_SECRET_KEY',key)
    with pytest.raises(HTTPException): stripe_client()


def test_sandbox_is_not_available_to_customer_accounts(monkeypatch):
    from app.core import config
    from app.services.billing import stripe_client
    monkeypatch.setattr(config,'BILLING_MODE','test')
    monkeypatch.setattr(config,'BILLING_TEST_USER_IDS',{1})
    with pytest.raises(HTTPException) as exc: stripe_client(SimpleNamespace(id=2))
    assert exc.value.status_code == 403


def subscription(user, status='active', price='price_pro', paid=True):
    end = int((datetime.now() + timedelta(days=30)).timestamp())
    return {'id':'sub_test', 'customer':user.stripe_customer_id, 'livemode':False,
            'status':status, 'collection_method':'charge_automatically', 'cancel_at_period_end':False,
            'items':{'data':[{'id':'si_test','quantity':1,'price':{'id':price},'current_period_end':end}]},
            'latest_invoice':{'status':'paid' if paid else 'open', 'created':int(datetime.now().timestamp())}}


def configure_prices(monkeypatch):
    from app.services.plan_catalog import PLAN_PRICES
    for key in PLAN_PRICES:
        monkeypatch.setitem(PLAN_PRICES[key], 'stripe_price_id', 'price_' + key)


def test_payment_sync_and_grace_cannot_be_extended_by_retries(billing_env, monkeypatch):
    from app.services.billing import sync_subscription
    from app.services.plans import get_user_plan_status
    _, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    user.stripe_customer_id='cus_test'
    sync_subscription(db, user, subscription(user))
    assert user.plan == 'pro' and user.billing_source == 'stripe_test'
    sync_subscription(db, user, subscription(user, 'past_due'))
    grace = user.billing_grace_until
    assert get_user_plan_status(user) == 'past_due'
    sync_subscription(db, user, subscription(user, 'past_due'))
    assert user.billing_grace_until == grace
    user.billing_grace_until=datetime.utcnow()-timedelta(seconds=1)
    assert get_user_plan_status(user) == 'expired'
    sync_subscription(db, user, subscription(user))
    assert user.billing_grace_until is None and user.plan_status == 'active'


def test_unpaid_initial_and_pending_upgrade_do_not_grant_new_plan(billing_env, monkeypatch):
    from app.services.billing import sync_subscription
    _, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    user.stripe_customer_id='cus_test'; user.plan='starter'; user.plan_status='trial'
    sync_subscription(db, user, subscription(user, paid=False))
    assert user.plan == 'starter' and user.plan_status == 'incomplete'
    user.plan_status='active'
    sub = subscription(user, price='price_starter', paid=False); sub['pending_update']={'expires_at':1}
    sync_subscription(db, user, sub)
    assert user.plan=='starter' and user.plan_status=='active'


def make_route(db, user, deliveries=1, status='bozza'):
    from app.models import RoutePlan, Delivery
    route=RoutePlan(user_id=user.id,nome='Quota',data_giro=date.today(),orario_partenza=time(8),status=status)
    db.add(route);db.flush()
    for _ in range(deliveries):
        db.add(Delivery(route_plan_id=route.id,cliente_nome='Test',indirizzo='Test'))
    db.commit();db.refresh(route)
    return route


def test_monthly_quota_counts_first_start_only_and_survives_deletion(billing_env, monkeypatch):
    from app.services.usage_limits import start_route_usage, usage_summary
    from app.services.plan_catalog import PLAN_LIMITS
    _, db, user, *_ = billing_env
    monkeypatch.setitem(PLAN_LIMITS['business'],'max_routes_per_month',1)
    route=make_route(db,user)
    assert usage_summary(db,user)['routes']['used']==0
    start_route_usage(db,route);db.commit()
    start_route_usage(db,route);db.commit()
    assert usage_summary(db,user)['routes']['used']==1
    route.status='annullato';db.commit();db.delete(route);db.commit()
    assert usage_summary(db,user)['routes']['used']==1
    # SQLite may reuse IDs, so choose a distinct ID as PostgreSQL sequences do.
    next_route=make_route(db,user);next_route.id=500;db.commit()
    with pytest.raises(HTTPException): start_route_usage(db,next_route)


def test_delivery_quota_and_expiry_preserve_in_progress_routes(billing_env, monkeypatch):
    from app.services.usage_limits import start_route_usage
    from app.services.plan_catalog import PLAN_LIMITS
    _, db, user, *_ = billing_env
    monkeypatch.setitem(PLAN_LIMITS['business'],'max_deliveries_per_month',1)
    route=make_route(db,user,2)
    with pytest.raises(HTTPException): start_route_usage(db,route)
    db.rollback()
    user.plan_status='expired';db.commit()
    with pytest.raises(HTTPException): start_route_usage(db,route)
    db.rollback()
    legacy=make_route(db,user,status='in_corso')
    start_route_usage(db,legacy);db.commit()
    assert legacy.started_at is not None


def test_ai_only_pro_without_monthly_cap(billing_env, monkeypatch):
    from app.services import ai_assistant
    _, db, user, *_ = billing_env
    monkeypatch.setattr(ai_assistant,'ai_enabled',lambda db:True)
    for plan in ('starter','business'):
        user.plan=plan
        with pytest.raises(HTTPException): ai_assistant.ensure_company_ai_allowed(user,db)
    user.plan='pro'
    ai_assistant.ensure_company_ai_allowed(user,db)


def test_expired_company_is_read_only_but_can_export(billing_env):
    from app.services.usage_limits import guard_company_write
    from app.services.plans import require_feature
    _, db, user, *_=billing_env
    user.plan='starter';user.plan_status='expired'
    request=lambda method,path:SimpleNamespace(method=method,url=SimpleNamespace(path=path))
    guard_company_write(request('GET','/api/customers'),user)
    guard_company_write(request('POST','/api/billing/create-checkout-session'),user)
    require_feature(user,'has_export')
    with pytest.raises(HTTPException):guard_company_write(request('POST','/api/customers'),user)


def test_downgrade_checks_existing_resources(billing_env, monkeypatch):
    from app.services.billing import downgrade_excess
    from app.services.plan_catalog import PLAN_LIMITS
    _, db, user, *_=billing_env
    monkeypatch.setitem(PLAN_LIMITS['starter'],'max_customers',0)
    assert downgrade_excess(db,user,'starter')==['clienti: 1/0']


def test_invoice_sync_is_idempotent_and_test_receipts_are_marked(billing_env):
    from app.services.billing import sync_invoice
    from app.models import BillingInvoice, BillingPayment
    _,db,user,*_=billing_env
    user.stripe_customer_id='cus_test'
    invoice={'id':'in_test','customer':'cus_test','livemode':False,'status':'paid','total':9900,'subtotal':9900,'amount_paid':9900,'currency':'eur','created':100,'status_transitions':{'paid_at':100}}
    sync_invoice(db,user,invoice);db.commit();sync_invoice(db,user,invoice);db.commit()
    assert db.query(BillingInvoice).count()==1
    payment=db.query(BillingPayment).one()
    assert payment.is_test and payment.amount==99


def test_invoice_download_is_tenant_scoped(billing_env):
    from app.models import BillingInvoice
    client,db,user,other,*_=billing_env
    invoice=BillingInvoice(user_id=other.id,invoice_number='other',stripe_invoice_id='in_other')
    db.add(invoice);db.commit()
    assert client.get(f'/api/billing/invoices/{invoice.id}/download').status_code==404


def test_notifications_are_deduplicated(billing_env, monkeypatch):
    from app.services import billing_notices
    _,db,user,*_=billing_env
    user.plan_status='trial';user.trial_ends_at=datetime.utcnow()+timedelta(days=2);user.email='test@example.test';db.commit()
    sent=[];monkeypatch.setattr(billing_notices,'_send',lambda *args:sent.append(args) or True)
    assert billing_notices.send_due_notices(db,send=False)['sent']==0
    assert not sent
    billing_notices.send_due_notices(db,send=True)
    billing_notices.send_due_notices(db,send=True)
    assert len(sent)==1


def test_webhook_rejects_bad_signature_and_live_events(billing_env, monkeypatch):
    from app.services import billing
    from app.core import config
    client,*_=billing_env
    monkeypatch.setattr(config,'STRIPE_WEBHOOK_SECRET','whsec_test')
    def invalid(*args): raise ValueError('bad signature')
    fake=SimpleNamespace(Webhook=SimpleNamespace(construct_event=invalid))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake)
    assert client.post('/api/billing/webhook',content=b'x').status_code==400
    fake.Webhook.construct_event=lambda *a:{'livemode':True}
    assert client.post('/api/billing/webhook',content=b'x').status_code==400


def test_webhook_duplicates_and_stale_events_use_current_state(billing_env, monkeypatch):
    from app.services import billing
    from app.core import config
    from app.models import BillingEvent
    client,db,user,*_=billing_env
    user.billing_source='stripe_test';user.stripe_customer_id='cus_test';user.stripe_subscription_id='sub_test';db.commit()
    monkeypatch.setattr(config,'BILLING_TEST_USER_IDS',{user.id});monkeypatch.setattr(config,'STRIPE_WEBHOOK_SECRET','whsec_test')
    event={'id':'evt_old','livemode':False,'type':'customer.subscription.updated','data':{'object':{'id':'sub_test','customer':'cus_test','status':'active'}}}
    fake=SimpleNamespace(Webhook=SimpleNamespace(construct_event=lambda *a:event),
        Subscription=SimpleNamespace(list=lambda **k:SimpleNamespace(auto_paging_iter=lambda:iter([]))))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake)
    calls=[]
    def reconcile(db,user,stripe):calls.append(1);user.plan_status='cancelled'
    monkeypatch.setattr(billing,'reconcile',reconcile)
    assert client.post('/api/billing/webhook',content=b'x').status_code==200
    assert client.post('/api/billing/webhook',content=b'x').json()['duplicate']
    assert user.plan_status=='cancelled' and len(calls)==1
    assert db.query(BillingEvent).count()==1


def test_checkout_is_reused_and_redirect_does_not_activate(billing_env, monkeypatch):
    from app.services import billing
    client,db,user,*_=billing_env
    user.plan_status='trial';user.stripe_customer_id='cus_test';user.billing_source='stripe_test';db.commit()
    configure_prices(monkeypatch)
    sessions={};calls=[]
    def create_session(**kwargs):
        calls.append(kwargs)
        session={'id':'cs_test','livemode':False,'status':'open','url':'https://checkout.stripe.com/test',
                 'metadata':kwargs['metadata'],'expires_at':kwargs['expires_at']}
        sessions['cs_test']=session
        return session
    fake=SimpleNamespace(Price=SimpleNamespace(retrieve=lambda id:{'id':id,'livemode':False,'active':True,'currency':'eur','unit_amount':9900,'recurring':{'interval':'month','interval_count':1}}),
        Subscription=SimpleNamespace(list=lambda **k:SimpleNamespace(auto_paging_iter=lambda:iter([]))),
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create_session,retrieve=lambda id:sessions[id])))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake)
    first=client.post('/api/billing/create-checkout-session',json={'plan':'pro'})
    assert first.status_code==200,first.text
    assert client.post('/api/billing/create-checkout-session',json={'plan':'pro'}).json()==first.json()
    assert len(calls)==1 and user.plan_status=='trial' and user.plan=='business'


def test_checkout_blocks_existing_subscription(billing_env,monkeypatch):
    from app.services import billing
    client,db,user,*_=billing_env
    user.billing_source='stripe_test';user.stripe_customer_id='cus_test';db.commit()
    monkeypatch.setattr(billing,'price_for',lambda *a:'price_pro')
    fake=SimpleNamespace(Subscription=SimpleNamespace(list=lambda **k:SimpleNamespace(auto_paging_iter=lambda:iter([{'id':'sub_test','status':'active'}]))))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake)
    assert client.post('/api/billing/create-checkout-session',json={'plan':'pro'}).status_code==409


def test_upgrade_requires_matching_quote_and_uses_pending_payment(billing_env,monkeypatch):
    from app.services import billing
    client,db,user,*_=billing_env
    configure_prices(monkeypatch)
    user.billing_source='stripe_test';user.stripe_customer_id='cus_test';user.stripe_subscription_id='sub_test';db.commit()
    current=subscription(user,price='price_business')
    calls=[]
    def modify(id,**kwargs):
        calls.append(kwargs)
        result=dict(current);result['pending_update']={'expires_at':1};result['latest_invoice']={'status':'open','hosted_invoice_url':'https://invoice.stripe.com/test'}
        return result
    fake=SimpleNamespace(Subscription=SimpleNamespace(retrieve=lambda *a,**k:current,modify=modify),Invoice=SimpleNamespace(create_preview=lambda **k:{'amount_due':2000}))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake);monkeypatch.setattr(billing,'price_for',lambda *a:'price_pro')
    preview=client.post('/api/billing/change-preview',json={'plan':'pro'}).json()
    result=client.post('/api/billing/change-plan',json={**preview,'plan':'pro','amount_due_cents':1})
    assert result.status_code==409 and not calls
    assert client.post('/api/billing/change-plan',json={**preview,'plan':'pro'}).status_code==200
    assert calls[0]['payment_behavior']=='pending_if_incomplete'
    assert calls[0]['proration_behavior']=='always_invoice'
    assert user.plan=='business' and user.plan_status=='active'


def test_downgrade_is_scheduled_without_changing_current_entitlement(billing_env,monkeypatch):
    from app.services import billing
    client,db,user,*_=billing_env
    configure_prices(monkeypatch)
    user.billing_source='stripe_test';user.stripe_customer_id='cus_test';user.stripe_subscription_id='sub_test';db.commit()
    current=subscription(user,price='price_business')
    calls=[]
    fake=SimpleNamespace(Subscription=SimpleNamespace(retrieve=lambda *a,**k:current),
        SubscriptionSchedule=SimpleNamespace(create=lambda **k:{'id':'sched_test','current_phase':{'start_date':100}},modify=lambda id,**k:calls.append(k)))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake);monkeypatch.setattr(billing,'price_for',lambda *a:'price_starter')
    assert client.post('/api/billing/change-plan',json={'plan':'starter'}).status_code==200
    assert user.plan=='business' and user.billing_pending_plan=='starter'
    assert calls[0]['phases'][0]['end_date']==current['items']['data'][0]['current_period_end']
    assert calls[0]['phases'][1]['items'][0]['price']=='price_starter'


def test_cancel_resume_and_suspension(billing_env,monkeypatch):
    from app.services import billing
    from app.services.plans import get_user_plan_status
    client,db,user,*_=billing_env
    configure_prices(monkeypatch)
    user.billing_source='stripe_test';user.stripe_customer_id='cus_test';user.stripe_subscription_id='sub_test';db.commit()
    current=subscription(user,price='price_business')
    def modify(id,**kwargs):current['cancel_at_period_end']=kwargs['cancel_at_period_end'];return current
    fake=SimpleNamespace(Subscription=SimpleNamespace(retrieve=lambda *a,**k:current,modify=modify))
    monkeypatch.setattr(billing,'stripe_client',lambda *a:fake)
    assert client.post('/api/billing/cancel').status_code==200
    assert user.billing_cancel_at_period_end and get_user_plan_status(user)=='active'
    assert client.post('/api/billing/resume').status_code==200
    assert not user.billing_cancel_at_period_end
    user.billing_suspended=True
    billing.sync_subscription(db,user,current)
    assert get_user_plan_status(user)=='cancelled'


def test_export_includes_only_own_data_after_expiry(billing_env):
    import io,zipfile
    from app.models import Customer
    client,db,user,other,*_=billing_env
    db.add(Customer(user_id=other.id,nome='PRIVATE_OTHER_COMPANY',indirizzo='PRIVATE'))
    user.plan_status='expired';db.commit()
    result=client.get('/api/billing/data-export')
    assert result.status_code==200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        customers=archive.read('customers.csv').decode('utf-8-sig')
        assert 'Esistente' in customers and 'PRIVATE_OTHER_COMPANY' not in customers


def test_started_route_backfill_preserves_dates_and_is_idempotent(billing_env):
    from app.services.usage_limits import backfill_started_routes
    from app.models import RouteUsage
    _,db,user,*_=billing_env
    route=make_route(db,user,status='in_corso')
    before=(user.plan,user.plan_status,user.trial_ends_at)
    backfill_started_routes(db);backfill_started_routes(db)
    assert db.query(RouteUsage).count()==1
    assert route.status=='in_corso' and (user.plan,user.plan_status,user.trial_ends_at)==before


def test_existing_database_adds_billing_columns_without_changing_accounts(billing_env):
    import ast
    from pathlib import Path
    import sqlalchemy
    from app.database import Base
    from app.models import User
    _,db,user,*_=billing_env
    user.plan_status='trial';user.trial_ends_at=datetime(2027,1,15);db.commit()
    user_id=user.id
    engine=db.get_bind();db.close()
    with engine.begin() as conn:
        for column in ('billing_source','billing_suspended','billing_grace_until','billing_cancel_at_period_end','billing_pending_plan','billing_checkout_plan','billing_change_key','billing_checkout_id','billing_checkout_url','billing_checkout_expires'):
            conn.execute(sqlalchemy.text(f'ALTER TABLE users DROP COLUMN {column}'))
        conn.execute(sqlalchemy.text('ALTER TABLE billing_invoices DROP COLUMN is_test'))
        conn.execute(sqlalchemy.text('ALTER TABLE billing_payments DROP COLUMN is_test'))
    tree=ast.parse(Path('app/main.py').read_text(encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='migrate_database')
    namespace={**vars(sqlalchemy),'Base':Base,'engine':engine}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'app/main.py','exec'),namespace)
    namespace['migrate_database']();namespace['migrate_database']()
    restored=db.get(User,user_id)
    assert restored.plan=='business' and restored.plan_status=='trial'
    assert restored.trial_ends_at==datetime(2027,1,15) and restored.billing_source is None
    assert not restored.billing_suspended


def test_repurchase_selects_new_subscription_after_cancellation(billing_env):
    from app.services.billing import select_current_subscription
    _,db,user,*_=billing_env
    user.stripe_customer_id='cus_test';user.billing_source='stripe_test';user.stripe_subscription_id='sub_old'
    fake=SimpleNamespace(Subscription=SimpleNamespace(list=lambda **k:SimpleNamespace(auto_paging_iter=lambda:iter([
        {'id':'sub_old','status':'canceled','livemode':False}, {'id':'sub_new','status':'active','livemode':False}]))))
    select_current_subscription(fake,user)
    assert user.stripe_subscription_id=='sub_new'


def test_sdk_resources_are_normalized_recursively(billing_env, monkeypatch):
    import stripe
    from app.services.billing import assert_test, sync_subscription, sync_invoice
    _, db, user, *_ = billing_env
    configure_prices(monkeypatch)
    user.stripe_customer_id = 'cus_sdk'
    obj = stripe.StripeObject.construct_from(subscription(user), 'sk_test_fake')
    normalized = assert_test(obj)
    assert isinstance(normalized, dict)
    assert isinstance(normalized['latest_invoice'], dict)
    sync_subscription(db, user, obj)
    assert user.plan == 'pro' and user.plan_status == 'active'
    invoice = stripe.StripeObject.construct_from({'id': 'in_sdk', 'customer': 'cus_sdk',
        'livemode': False, 'status': 'paid', 'amount_paid': 9900, 'total': 9900,
        'total_taxes': None, 'status_transitions': {'paid_at': 1700000000}}, 'sk_test_fake')
    sync_invoice(db, user, invoice)
    db.flush()
