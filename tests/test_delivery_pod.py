import base64
import hashlib
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from test_agents_feature import env
from test_stability import seed_route
from pod_fake import FakeStorage


def image_data(fmt='PNG', size=(40, 30)):
    out = io.BytesIO()
    Image.new('RGB', size, 'black').save(out, format=fmt)
    mime = {'PNG': 'png', 'JPEG': 'jpeg', 'WEBP': 'webp'}[fmt]
    return f'data:image/{mime};base64,' + base64.b64encode(out.getvalue()).decode()


@pytest.fixture
def storage(monkeypatch):
    from app.services import object_storage
    fake = FakeStorage()
    monkeypatch.setattr(object_storage, 'get_storage', lambda: fake)
    monkeypatch.setenv('OBJECT_STORAGE_ENABLED', 'true')
    return fake


def setup_portals(env):
    from app.routers import driver, operator, routes
    client, db, owner, *_ = env
    route, delivery, account = seed_route(env)
    for module in (driver, operator, routes):
        client.app.include_router(module.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    return client, db, owner, route, delivery, account


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_complete_signature_photo_pdf_no_blobs_and_retry(env, storage, portal):
    from app.models import DeliveryStatus
    client, db, owner, route, delivery, _ = setup_portals(env)
    owner.needs_photo_proof = True
    db.commit()
    prefix = '/api/driver' if portal == 'driver' else '/api/operator/test-route'
    path = f'{prefix}/delivery/{delivery.id}/complete'
    payload = {'signature_data': image_data(), 'signed_by_name': 'Mario',
               'signature_note': 'Ricevuto', 'delivery_photo_data': image_data('JPEG', (2400, 1800))}
    assert client.post(path, json=payload).status_code == 200
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    assert state.signature_data is None and state.status == 'completata'
    assert state.pod_created_at and state.signed_at
    for kind in ('signature', 'delivery_photo', 'pod'):
        key = getattr(state, kind + '_object_key')
        raw = storage.objects[key]
        assert getattr(state, kind + '_size') == len(raw)
        assert getattr(state, kind + '_sha256') == hashlib.sha256(raw).hexdigest()
        response = client.get(f'{prefix}/delivery/{delivery.id}/evidence/{kind}')
        assert response.status_code == 200 and response.json()['expires_in'] == 900
        assert response.headers['cache-control'] == 'no-store'
    assert storage.objects[state.pod_object_key].startswith(b'%PDF')
    with Image.open(io.BytesIO(storage.objects[state.delivery_photo_object_key])) as photo:
        assert max(photo.size) == 1600 and not photo.getexif()
    assert client.post(path, json=payload).status_code == 200
    assert storage.uploads == 3
    details = client.get(f'/api/driver/routes/{route.id}').json()['consegne'][0]
    assert all(details[f'has_{k}'] for k in ('signature', 'delivery_photo', 'pod'))
    assert 'signature_data' not in details
    from app.routers.routes import serialize_route
    assert 'signature_data' not in serialize_route(route)['consegne'][0]


@pytest.mark.parametrize('failure', [1, 2, 3])
def test_upload_failure_rolls_back_and_cleans_even_uncertain_put(env, storage, failure):
    from app.models import DeliveryStatus
    client, db, _, route, delivery, _ = setup_portals(env)
    storage.fail_at = failure
    response = client.post(f'/api/driver/delivery/{delivery.id}/complete', json={
        'signature_data': image_data(), 'signed_by_name': 'Mario', 'delivery_photo_data': image_data('JPEG')})
    assert response.status_code == 503
    assert not storage.objects
    assert db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).first() is None
    assert route.status == 'in_corso'


def test_commit_failure_cleans_new_objects(env, storage, monkeypatch):
    from app.services.route_execution import apply_delivery_update
    from app.services.delivery_pod import commit_delivery_update
    _, db, _, _, delivery, _ = setup_portals(env)
    apply_delivery_update(db, delivery, {'signature_data': image_data(), 'signed_by_name': 'Mario'}, 'complete')
    assert len(storage.objects) == 2
    def fail():
        raise RuntimeError('simulated commit failure')
    monkeypatch.setattr(db, 'commit', fail)
    with pytest.raises(RuntimeError):
        commit_delivery_update(db)
    assert not storage.objects


def test_missing_config_and_required_photo_fail_closed(env, monkeypatch):
    from app.services import object_storage
    client, db, owner, _, delivery, _ = setup_portals(env)
    monkeypatch.setenv('OBJECT_STORAGE_ENABLED', 'false')
    path = f'/api/driver/delivery/{delivery.id}/complete'
    payload = {'signature_data': image_data(), 'signed_by_name': 'Mario'}
    assert client.post(path, json=payload).status_code == 503
    owner.needs_photo_proof = True
    db.commit()
    assert client.post(path, json=payload).status_code == 400
    owner.needs_photo_proof = owner.delivery_signature_enabled = False
    db.commit()
    assert client.post(path, json={}).status_code == 200


def test_optional_completion_ignores_incomplete_storage_configuration(env, monkeypatch):
    from app.models import DeliveryStatus
    from app.services import object_storage
    client, db, owner, _, delivery, _ = setup_portals(env)
    owner.delivery_signature_enabled = False
    owner.needs_photo_proof = False
    db.commit()
    monkeypatch.setenv('OBJECT_STORAGE_ENABLED', 'true')
    for name in ('ENDPOINT', 'REGION', 'BUCKET', 'ACCESS_KEY', 'SECRET_KEY'):
        monkeypatch.delenv('OBJECT_STORAGE_' + name, raising=False)

    assert object_storage.enabled() is True
    assert object_storage.configured() is False
    response = client.post(f'/api/driver/delivery/{delivery.id}/complete', json={})
    assert response.status_code == 200
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    assert state.status == 'completata'
    assert state.pod_object_key is None


def test_legacy_signature_read_without_storage_and_unchanged(env, monkeypatch):
    from app.models import DeliveryStatus
    client, db, _, route, delivery, _ = setup_portals(env)
    legacy = image_data()
    state = DeliveryStatus(route_plan_id=route.id, delivery_id=delivery.id,
                           signature_data=legacy, signed_by_name='Legacy', status='completata')
    db.add(state); db.commit()
    monkeypatch.setenv('OBJECT_STORAGE_ENABLED', 'false')
    response = client.get(f'/api/deliveries/{delivery.id}/evidence/signature')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    assert state.signature_data == legacy


def test_tenant_driver_token_and_corrupt_key_isolation(env, storage):
    from app.core.dependencies import current_user
    from app.models import Driver, DriverAccount, RoutePlan, Delivery, DeliveryStatus, RouteToken
    client, db, _, route, delivery, _ = setup_portals(env)
    other = env[3]
    foreign_driver = Driver(user_id=other.id, nome='Altro')
    foreign_route = RoutePlan(user_id=other.id, nome='Altro', data_giro=route.data_giro, orario_partenza=route.orario_partenza)
    db.add_all([foreign_driver, foreign_route]); db.flush()
    foreign = Delivery(route_plan_id=foreign_route.id, cliente_nome='Altro', indirizzo='Altro')
    db.add(foreign); db.commit()
    for prefix in ('/api/driver/delivery', '/api/operator/test-route/delivery', '/api/deliveries'):
        assert client.get(f'{prefix}/{foreign.id}/evidence/pod').status_code == 404
    assert client.post(f'/api/driver/delivery/{delivery.id}/complete', json={
        'signature_data': image_data(), 'signed_by_name': 'Mario'}).status_code == 200
    client.app.dependency_overrides[current_user] = lambda: other
    assert client.get(f'/api/deliveries/{delivery.id}/evidence/pod').status_code == 404
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    state.pod_object_key = state.pod_object_key.replace(f'companies/{route.user_id}/', f'companies/{other.id}/')
    db.commit()
    assert client.get(f'/api/driver/delivery/{delivery.id}/evidence/pod').status_code == 404
    token = db.query(RouteToken).filter_by(token='test-route').one()
    from datetime import datetime, timedelta
    token.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get(f'/api/operator/test-route/delivery/{delivery.id}/evidence/signature').status_code == 410


@pytest.mark.parametrize('value', ['data:text/html;base64,PHNjcmlwdD4=',
    'data:image/jpeg;base64,' + base64.b64encode(b'<html>bad</html>').decode(),
    'data:image/png;base64,AA==', 'data:image/jpeg;base64,' + 'A' * 16000004], ids=['html','fake-jpeg','bad-png','oversize'])
def test_invalid_images(value):
    from app.services.delivery_pod import normalize_image
    with pytest.raises(HTTPException) as exc:
        normalize_image(value, 'delivery_photo')
    assert exc.value.status_code == 400


def test_mime_mismatch_and_signature_dimensions():
    from app.services.delivery_pod import normalize_image
    with pytest.raises(HTTPException):
        normalize_image(image_data('JPEG').replace('image/jpeg', 'image/png'), 'signature')
    with pytest.raises(HTTPException):
        normalize_image(image_data(size=(6000, 5000)), 'signature')


def test_real_s3_adapter_uses_private_acl_and_temporary_get(monkeypatch):
    from app.services.object_storage import ObjectStorage, object_key
    from botocore.stub import Stubber
    for name, value in {'ENABLED':'true','ENDPOINT':'https://fsn1.your-objectstorage.com',
        'REGION':'fsn1','BUCKET':'test-pod','ACCESS_KEY':'test','SECRET_KEY':'test','SIGNED_URL_SECONDS':'900'}.items():
        monkeypatch.setenv('OBJECT_STORAGE_' + name, value)
    storage = ObjectStorage()
    key = object_key(1, 2, 3, 'signature')
    raw = b'test'
    with Stubber(storage.client) as stub:
        stub.add_response('get_bucket_acl', {'Grants': []}, {'Bucket':'test-pod'})
        stub.add_client_error('get_bucket_policy', service_error_code='NoSuchBucketPolicy', expected_params={'Bucket':'test-pod'})
        stub.add_response('put_object', {}, {'Bucket':'test-pod','Key':key,'Body':raw,
            'ContentType':'image/png','ACL':'private','Metadata':{'sha256':hashlib.sha256(raw).hexdigest()}})
        storage.upload(key, raw, 'image/png')
    url = storage.signed_url(key, 'image/png')
    assert 'X-Amz-Expires=900' in url and 'X-Amz-Signature=' in url


def test_migration_adds_metadata_idempotently_preserves_legacy(env):
    from sqlalchemy import create_engine, text, inspect
    from app.migrations import run_migrations, LATEST
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE delivery_statuses (id INTEGER PRIMARY KEY, delivery_id INTEGER, route_plan_id INTEGER, signature_data TEXT, signature_note TEXT)'))
        conn.execute(text("INSERT INTO delivery_statuses VALUES (1,1,1,'legacy','nota')"))
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01','20261004_02'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v':version})
    run_migrations(engine); run_migrations(engine)
    assert 'pod_sha256' in {c['name'] for c in inspect(engine).get_columns('delivery_statuses')}
    with engine.connect() as conn:
        assert conn.execute(text('SELECT signature_data FROM delivery_statuses')).scalar() == 'legacy'
        assert conn.execute(text('SELECT COUNT(*) FROM schema_migrations WHERE version=:v'), {'v':LATEST}).scalar() == 1


def test_pdf_text_and_long_notes(env, storage):
    from app.services.delivery_pod import generate_pod
    from types import SimpleNamespace
    PdfReader = pytest.importorskip("pypdf").PdfReader
    _, db, owner, route, delivery, _ = setup_portals(env)
    from datetime import datetime
    state = SimpleNamespace(completata_il=datetime(2026,10,4,10,30), signed_by_name='Mario Rossi',
        signed_at=datetime(2026,10,4,10,29), note_operatore='merce ricevuta', signature_note='<script> & ' + 'Nota lunga ' * 150)
    raw = generate_pod(route, delivery, state, owner, base64.b64decode(image_data().split(',')[1]),
                       base64.b64decode(image_data('JPEG').split(',')[1]))
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
    assert 'Consegna completata' in text and 'Mario Rossi' in text and 'merce ricevuta' in text
    assert 'certificazione legale' in text


def test_signature_replacement_cleans_only_after_commit_and_retains_legacy(env, storage):
    from app.models import DeliveryStatus
    from app.services.route_execution import apply_delivery_update
    from app.services.delivery_pod import commit_delivery_update
    _, db, _, route, delivery, _ = setup_portals(env)
    state = DeliveryStatus(route_plan_id=route.id, delivery_id=delivery.id,
                           signature_data=image_data(), signed_by_name='Legacy', status='in_attesa')
    db.add(state); db.commit()
    payload = {'signature_data':image_data(), 'signed_by_name':'Mario'}
    apply_delivery_update(db, delivery, payload, 'signature'); commit_delivery_update(db)
    old_key = state.signature_object_key
    apply_delivery_update(db, delivery, payload, 'signature')
    assert old_key in storage.objects and len(storage.objects) == 2
    db.rollback()
    assert list(storage.objects) == [old_key] and state.signature_data
    apply_delivery_update(db, delivery, payload, 'complete'); commit_delivery_update(db)
    assert old_key not in storage.objects and state.signature_data


@pytest.mark.parametrize('public_policy', [False, True])
def test_public_bucket_rejected(monkeypatch, public_policy):
    from app.services.object_storage import ObjectStorage
    from botocore.stub import Stubber
    for name, value in {'ENABLED':'true','ENDPOINT':'https://fsn1.your-objectstorage.com',
        'REGION':'fsn1','BUCKET':'test-pod','ACCESS_KEY':'test','SECRET_KEY':'test'}.items():
        monkeypatch.setenv('OBJECT_STORAGE_' + name, value)
    storage = ObjectStorage()
    with Stubber(storage.client) as stub:
        grants = [] if public_policy else [{'Grantee':{'Type':'Group','URI':'http://acs.amazonaws.com/groups/global/AllUsers'},'Permission':'READ'}]
        stub.add_response('get_bucket_acl', {'Grants':grants}, {'Bucket':'test-pod'})
        if public_policy:
            import json
            stub.add_response('get_bucket_policy', {'Policy':json.dumps({'Statement':[{'Effect':'Allow','Principal':'*'}]})}, {'Bucket':'test-pod'})
        with pytest.raises(HTTPException) as exc:
            storage.verify_configuration()
        assert exc.value.status_code == 503


def test_pod_failure_is_registered_in_existing_monitor(env, monkeypatch):
    from app.main import pod_storage_error
    from app.services.object_storage import unavailable
    from app.services import error_monitor
    from fastapi import Request
    import asyncio
    calls=[]
    monkeypatch.setattr(error_monitor, 'log_exception', lambda request, exc, severity: calls.append((exc.status_code, severity)) or 42)
    request = Request({'type':'http','method':'POST','path':'/api/driver/delivery/1/complete','headers':[]})
    response = asyncio.run(pod_storage_error(request, unavailable()))
    assert response.status_code == 503 and calls == [(503, 'high')]
    assert b'42' in response.body


def test_reconciliation_preserves_referenced_recent_and_unrelated_objects(env, storage, capsys):
    from app.services.route_execution import apply_delivery_update
    from app.services.delivery_pod import commit_delivery_update
    from app.services.object_storage import object_key
    from scripts.reconcile_pod_storage import reconcile
    from types import SimpleNamespace
    from datetime import datetime, timedelta, timezone
    _, db, _, route, delivery, _ = setup_portals(env)
    state = apply_delivery_update(db, delivery, {'signature_data':image_data(), 'signed_by_name':'Mario'}, 'complete')
    commit_delivery_update(db)
    referenced = state.signature_object_key
    orphan = object_key(route.user_id, route.id, delivery.id, 'signature')
    recent = object_key(route.user_id, route.id, delivery.id, 'signature')
    storage.objects.update({orphan:b'old', recent:b'recent', 'unrelated.txt':b'unrelated'})
    now = datetime.now(timezone.utc)
    items = [{'Key':key, 'LastModified':now - timedelta(hours=1 if key == recent else 72)} for key in storage.objects]
    storage.bucket = 'test'
    storage.client = SimpleNamespace(get_paginator=lambda name: SimpleNamespace(paginate=lambda **kwargs:[{'Contents':items}]))
    reconcile(storage, db, now=now)
    assert orphan in capsys.readouterr().out and orphan in storage.objects
    reconcile(storage, db, delete=True, now=now)
    assert orphan not in storage.objects
    assert referenced in storage.objects and recent in storage.objects and 'unrelated.txt' in storage.objects
