"""Subscription gates on isolated databases; no provider or storage calls."""
import pytest

from test_agents_feature import env
from test_delivery_pod import image_data, setup_portals
from test_order_ingestion import api_source, setup as setup_source
from test_delivery_tracking import tracking_env, issue, read


@pytest.mark.parametrize('plan,expected', [('starter', 403), ('business', 200), ('pro', 200)])
def test_signature_setting_requires_current_plan(env, plan, expected):
    client, db, owner, *_ = env
    owner.plan = plan
    db.commit()
    response = client.put('/api/settings', json={'delivery_signature_enabled': True})
    assert response.status_code == expected, response.text
    assert bool(owner.delivery_signature_enabled) is (expected == 200)
    assert client.put('/api/settings', json={'delivery_signature_enabled': False}).status_code == 200


@pytest.mark.parametrize('plan,expected', [('starter', 403), ('business', 200), ('pro', 200)])
def test_advanced_report_export_requires_report_entitlement(env, plan, expected):
    client, db, owner, *_ = env
    owner.plan = plan
    db.commit()
    for path in ('/api/reports/summary', '/api/reports/export'):
        response = client.get(path)
        assert response.status_code == expected, response.text


@pytest.mark.parametrize('portal', ['driver', 'operator'])
@pytest.mark.parametrize('evidence', ['signature', 'photo'])
def test_starter_cannot_upload_premium_evidence(env, monkeypatch, portal, evidence):
    from app.models import DeliveryStatus
    from app.services import object_storage
    client, db, owner, _, delivery, _ = setup_portals(env)
    owner.plan = 'starter'
    owner.needs_photo_proof = True
    db.commit()
    monkeypatch.setattr(object_storage, 'get_storage', lambda: pytest.fail('Starter accessed POD storage'))
    payload = {'signature_data': image_data(), 'signed_by_name': 'Mario'} if evidence == 'signature' else {
        'delivery_photo_data': image_data('JPEG')}
    prefix = '/api/driver' if portal == 'driver' else '/api/operator/test-route'
    response = client.post(f'{prefix}/delivery/{delivery.id}/complete', json=payload)
    assert response.status_code == 403, response.text
    assert db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).first() is None


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_downgrade_stale_requirements_allow_normal_completion_without_storage(env, monkeypatch, portal):
    from app.models import DeliveryStatus
    from app.services import object_storage
    client, db, owner, route, delivery, _ = setup_portals(env)
    owner.plan = 'starter'
    owner.needs_photo_proof = True
    # seed_route leaves the previously enabled signature preference in place.
    assert owner.delivery_signature_enabled
    db.commit()
    monkeypatch.setattr(object_storage, 'configured', lambda: True)
    monkeypatch.setattr(object_storage, 'get_storage', lambda: pytest.fail('Starter accessed POD storage'))
    prefix = '/api/driver' if portal == 'driver' else '/api/operator/test-route'
    details = client.get(f'/api/driver/routes/{route.id}' if portal == 'driver' else '/api/operator/test-route').json()
    settings = details['settings'] if portal == 'driver' else details
    assert settings['delivery_signature_enabled'] is False
    assert settings['delivery_photo_required'] is False
    response = client.post(f'{prefix}/delivery/{delivery.id}/complete', json={'note': 'Ricevuto', 'tempo_scarico': 12})
    assert response.status_code == 200, response.text
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    assert state.status == 'completata' and state.note_operatore == 'Ricevuto'
    assert not any((state.signature_object_key, state.delivery_photo_object_key, state.pod_object_key))
    assert owner.delivery_signature_enabled and owner.needs_photo_proof


def test_downgrade_revokes_evidence_access_without_deleting_documents(env, monkeypatch):
    from app.models import DeliveryStatus
    from app.services import object_storage
    from pod_fake import FakeStorage
    client, db, owner, _, delivery, _ = setup_portals(env)
    storage = FakeStorage()
    monkeypatch.setattr(object_storage, 'get_storage', lambda: storage)
    response = client.post(f'/api/driver/delivery/{delivery.id}/complete', json={
        'signature_data': image_data(), 'signed_by_name': 'Mario', 'delivery_photo_data': image_data('JPEG')})
    assert response.status_code == 200, response.text
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    saved_keys = (state.signature_object_key, state.delivery_photo_object_key, state.pod_object_key)
    assert len(storage.objects) == 3
    owner.plan = 'starter'
    db.commit()
    for prefix in ('/api/driver/delivery', '/api/operator/test-route/delivery', '/api/deliveries'):
        for kind in ('signature', 'delivery_photo', 'pod'):
            response = client.get(f'{prefix}/{delivery.id}/evidence/{kind}')
            assert response.status_code == 403, response.text
    assert saved_keys == (state.signature_object_key, state.delivery_photo_object_key, state.pod_object_key)
    assert len(storage.objects) == 3 and not storage.deleted


def test_tracking_links_stop_working_after_downgrade_and_data_is_preserved(tracking_env):
    from app.models import DeliveryTrackingLink
    client, db, owner, _, delivery, *_ = tracking_env
    token = issue(client, delivery)
    assert read(client, token).status_code == 200
    owner.plan = 'starter'
    db.commit()
    assert client.post(f'/api/deliveries/{delivery.id}/tracking').status_code == 403
    response = read(client, token)
    assert response.status_code == 404
    assert response.json()['detail'] == 'Link non disponibile o scaduto'
    assert response.headers['cache-control'] == 'no-store'
    assert db.query(DeliveryTrackingLink).filter_by(delivery_id=delivery.id).count() == 1
    owner.plan = 'business'
    db.commit()
    assert read(client, token).status_code == 200


def include_sources(client):
    from app.routers.order_sources import router
    from app.services.order_source_security import _attempts
    _attempts.clear()
    client.app.include_router(router)


def test_starter_keeps_file_import_but_cannot_create_api_sources(env):
    from app.order_models import Order
    client, db, owner, *_ = env
    include_sources(client)
    owner.plan = 'starter'
    db.commit()
    response = client.post('/api/order-sources', json={'name': 'API', 'kind': 'api'})
    assert response.status_code == 403, response.text
    source, run_id = setup_source(env, 'file')
    response = client.post(f"/api/order-sources/{source['id']}/runs/{run_id}/commit", json={'confirm': True})
    assert response.status_code == 200, response.text
    assert db.query(Order).count() == 1


@pytest.mark.parametrize('plan', ['business', 'pro'])
def test_valid_api_credentials_are_blocked_after_downgrade(env, plan):
    from app.order_models import Order, OrderSource, OrderImportRun
    client, db, owner, *_ = env
    include_sources(client)
    owner.plan = plan
    db.commit()
    source, headers = api_source(env)
    first = {'external_id': 'FIRST', 'number': 'FIRST', 'recipient_name': 'Recipient', 'delivery_address': 'Via Roma 1'}
    response = client.post('/api/order-ingestion', headers=headers, json={'batch_id': 'first', 'orders': [first]})
    assert response.status_code == 200, response.text
    assert db.query(Order).count() == 1
    runs_before = db.query(OrderImportRun).count()
    owner.plan = 'starter'
    db.commit()
    second = {**first, 'external_id': 'SECOND', 'number': 'SECOND'}
    response = client.post('/api/order-ingestion', headers=headers, json={'batch_id': 'second', 'orders': [second]})
    assert response.status_code == 403, response.text
    assert db.query(Order).count() == 1
    assert db.query(OrderImportRun).count() == runs_before
    existing = db.get(OrderSource, source['id'])
    assert existing.status == 'active' and existing.credential_hash
    # Keeping the source record must not allow reactivation or key rotation.
    for action in ('resume', 'rotate'):
        response = client.post(f"/api/order-sources/{source['id']}/action", json={'version': existing.version, 'action': action})
        assert response.status_code == 403, response.text


@pytest.mark.parametrize('provider', ['shopify', 'woocommerce'])
def test_existing_signed_connectors_stop_importing_after_downgrade(env, monkeypatch, provider):
    from cryptography.fernet import Fernet
    from app.order_models import Order, OrderSource, OrderImportRun
    from test_order_connectors import create, deliver, order_body
    client, db, owner, *_ = env
    include_sources(client)
    monkeypatch.setenv('ORDER_CONNECTOR_KEY', Fernet.generate_key().decode())
    source = create(env, provider)
    response = deliver(env, source, order_body(provider))
    assert response.status_code == 200, response.text
    assert db.query(Order).count() == 1
    runs_before = db.query(OrderImportRun).count()
    owner.plan = 'starter'
    db.commit()
    body = {**order_body(provider), 'id': 456}
    response = deliver(env, source, body, event='after-downgrade')
    assert response.status_code == 403, response.text
    assert db.query(Order).count() == 1
    assert db.query(OrderImportRun).count() == runs_before
    assert db.get(OrderSource, source['id']).configuration['connector_secret']


def test_webhook_quota_failure_is_clear_atomic_and_idempotent(env, monkeypatch):
    from cryptography.fernet import Fernet
    from app.order_models import Order, OrderImportRun, OrderMonthlyUsage
    from app.services.plans import get_plan_limits, order_quota_period
    from test_order_connectors import create, deliver, order_body, SECRET
    client, db, owner, *_ = env
    include_sources(client)
    monkeypatch.setenv('ORDER_CONNECTOR_KEY', Fernet.generate_key().decode())
    source = create(env)
    month = order_quota_period()[0]
    maximum = get_plan_limits(owner.plan)['max_orders_per_month']
    counter = OrderMonthlyUsage(user_id=owner.id, month=month, used=maximum)
    db.add(counter)
    db.commit()

    response = deliver(env, source, order_body(), event='quota-full')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'failed'
    run = db.get(OrderImportRun, response.json()['run_id'])
    assert run.report['error'].startswith('Quota mensile ordini raggiunta:')
    assert f'{maximum}/{maximum}' in run.report['error']
    assert SECRET not in str(run.report)
    assert db.query(Order).count() == 0
    assert counter.used == maximum

    retry = deliver(env, source, order_body(), event='quota-full')
    assert retry.status_code == 200 and retry.json() == response.json()
    assert db.query(OrderImportRun).count() == 1
    assert db.query(Order).count() == 0 and counter.used == maximum


@pytest.mark.parametrize('plan,expected', [('starter', 403), ('business', 200), ('pro', 200)])
def test_fleet_gate_runs_before_optimization(env, monkeypatch, plan, expected):
    from app.routers import fleet_planning
    client, db, owner, *_ = env
    client.app.include_router(fleet_planning.router)
    owner.plan = plan
    db.commit()
    called = []
    def create(*args):
        called.append(True)
        return {'id': 1}
    monkeypatch.setattr(fleet_planning.service, 'create_preview', create)
    monkeypatch.setattr(fleet_planning.service, 'public', lambda value: value)
    response = client.post('/api/fleet-planning/preview', json={
        'data_giro': '2099-01-15', 'deposit_id': 1,
        'resources': [{'vehicle_id': 1, 'driver_id': 1}, {'vehicle_id': 2, 'driver_id': 2}],
        'consegne': [{'cliente_nome': 'Cliente', 'indirizzo': 'Via Roma 1'}],
    })
    assert response.status_code == expected, response.text
    assert bool(called) is (expected == 200)
