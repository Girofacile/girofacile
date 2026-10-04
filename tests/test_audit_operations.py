from datetime import datetime, timedelta, date, time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response

from test_agents_feature import env
from test_stability import seed_route


def setup_route(env):
    from app.routers import driver, operator, routes
    client, db, owner, *_ = env
    route, delivery, account = seed_route(env)
    owner.delivery_signature_enabled = False
    db.commit()
    for module in (driver, operator, routes):
        client.app.include_router(module.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    return client, db, route, delivery


@pytest.mark.parametrize('portal', ['operator', 'driver'])
def test_last_missed_closes_route_and_retry_is_idempotent(env, portal):
    client, db, route, delivery = setup_route(env)
    prefix = '/api/operator/test-route' if portal == 'operator' else '/api/driver'
    path = f'{prefix}/delivery/{delivery.id}/missed'
    assert client.post(path, json={'motivo': 'chiuso'}).status_code == 200
    assert route.status == 'completato'
    completed = route.completed_at_utc
    assert client.post(path, json={'motivo': 'chiuso'}).status_code == 200
    assert route.completed_at_utc == completed


def test_cancelled_started_route_cannot_be_changed(env):
    client, db, route, delivery = setup_route(env)
    assert client.post(f'/api/driver/routes/{route.id}/start').status_code == 200
    assert client.post(f'/api/routes/{route.id}/cancel').status_code == 200
    for action in ('complete', 'missed', 'note', 'signature'):
        assert client.post(f'/api/driver/delivery/{delivery.id}/{action}', json={}).status_code == 409
    assert route.status == 'annullato'


def test_delivery_retry_does_not_change_observations_or_evidence(env):
    client, db, route, delivery = setup_route(env)
    path = f'/api/driver/delivery/{delivery.id}/complete'
    assert client.post(path, json={'tempo_scarico': 20}).status_code == 200
    from app.models import DeliveryStatus
    row = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    when = row.completata_il
    assert client.post(path, json={'tempo_scarico': 60}).status_code == 200
    assert delivery.customer.tempo_scarico_rilevazioni == 1
    assert delivery.customer.tempo_scarico_min == 20
    assert row.completata_il == when and row.tempo_scarico_effettivo == 20


def test_future_start_rejected_and_get_does_not_create_states(env):
    client, db, route, delivery = setup_route(env)
    from app.models import DeliveryStatus
    route.status = 'programmato'; db.commit()
    assert client.post(f'/api/driver/routes/{route.id}/start').status_code == 409
    assert client.get(f'/api/driver/routes/{route.id}').status_code == 200
    assert client.get('/api/operator/test-route').status_code == 200
    assert db.query(DeliveryStatus).count() == 0


def test_duration_uses_utc_and_preserves_ambiguous_history():
    from app.routers.reports import _actual_route_minutes
    route = SimpleNamespace(started_at=datetime(2026, 10, 4, 10), completed_at=datetime(2026, 10, 4, 11),
                            started_at_utc=datetime(2026, 10, 4, 8), completed_at_utc=datetime(2026, 10, 4, 11), totale_minuti=99)
    assert _actual_route_minutes(route) == 180
    route.started_at_utc = None
    assert _actual_route_minutes(route) == 99
    assert route.started_at == datetime(2026, 10, 4, 10)


@pytest.mark.parametrize('portal', ['operator', 'driver'])
def test_invalid_delivery_payload_does_not_create_usage(env, portal):
    client, db, route, delivery = setup_route(env)
    from app.models import RouteUsage, DeliveryStatus
    prefix = '/api/operator/test-route' if portal == 'operator' else '/api/driver'
    assert client.post(f'{prefix}/delivery/{delivery.id}/complete', json={'tempo_scarico': -5}).status_code == 422
    assert client.post(f'{prefix}/delivery/{delivery.id}/missed', json={'motivo': '<invalid>'}).status_code == 422
    assert db.query(RouteUsage).count() == 0 and db.query(DeliveryStatus).count() == 0


def test_notifications_tenant_filter_and_repeated_unread_count(env):
    from app.models import Driver, ChatMessage, Notification
    from app.routers.notifications import sync_operational_notifications
    _, db, owner, other, *_ = env
    mine, theirs = Driver(user_id=owner.id, nome='Mine'), Driver(user_id=other.id, nome='Other')
    db.add_all([mine, theirs]); db.flush()
    first = ChatMessage(driver_id=mine.id, sender_type='driver', sender_name='Audit', message='one', created_at=datetime(2026,1,1))
    db.add(first)
    db.add_all([ChatMessage(driver_id=theirs.id, sender_type='driver', sender_name='Audit', message='other', created_at=datetime(2026,1,2)) for _ in range(200)])
    db.commit()
    sync_operational_notifications(db, owner)
    notification = db.query(Notification).filter_by(user_id=owner.id, type='chat').one()
    notification.is_read = True
    first.read_at = datetime.utcnow()
    db.add(ChatMessage(driver_id=mine.id, sender_type='driver', sender_name='Audit', message='two'))
    db.commit()
    sync_operational_notifications(db, owner)
    assert db.query(Notification).filter_by(user_id=owner.id, type='chat', is_read=False).count() == 1


def test_report_homonyms_and_allocations_are_consistent(env):
    from app.models import Driver, RoutePlan, Delivery, Customer, Agent
    from app.routers.reports import build_report_data
    _, db, owner, _, seller, _, first, *_ = env
    owner.agents_enabled = True
    second_agent = Agent(user_id=owner.id, nome=seller.nome)
    db.add(second_agent); db.flush()
    second = Customer(user_id=owner.id, nome=first.nome, indirizzo='Via Test', agent_id=second_agent.id)
    db.add(second); db.flush()
    for _ in range(2):
        driver = Driver(user_id=owner.id, nome='Mario', cognome='Rossi')
        db.add(driver); db.flush()
        route = RoutePlan(user_id=owner.id, driver_id=driver.id, nome='Audit', data_giro=date.today(), orario_partenza=time(8), status='completato', totale_km=100)
        db.add(route); db.flush()
        for customer in (first, second):
            db.add(Delivery(route_plan_id=route.id, customer_id=customer.id, cliente_nome=customer.nome, indirizzo=customer.indirizzo))
    db.commit()
    data = build_report_data(db, owner)
    assert len(data['tables']['autisti']) == 2
    assert len(data['tables']['clienti']) == 2
    assert len(data['tables']['agenti']) == 2
    assert sum(x['km'] for x in data['tables']['agenti']) == data['metrics']['km_totali'] == 200
    assert data['metrics']['consegne_totali'] == data['metrics']['in_attesa'] == 4
    filtered = build_report_data(db, owner, customer_id=str(first.id))
    assert filtered['metrics']['km_totali'] == 100 and filtered['metrics']['consegne_totali'] == 2


def test_registration_policy_and_trial_catalog(env, monkeypatch):
    from app.services.platform_settings import set_platform_setting
    from app.routers.auth import signup
    from app.routers import auth
    from app.routers.billing import list_plans
    from app.schemas import SignupIn
    _, db, *_ = env
    monkeypatch.setattr(auth, 'ERROR_NOTIFICATIONS_EMAIL', '')
    set_platform_setting(db, 'registrations_enabled', 'false'); db.commit()
    with pytest.raises(HTTPException) as error:
        signup(SignupIn(username='audit-new', password='Audit-password-2026'), Response(), db)
    assert error.value.status_code == 503
    set_platform_setting(db, 'registrations_enabled', 'true')
    set_platform_setting(db, 'trial_days', '7')
    set_platform_setting(db, 'default_plan', 'business'); db.commit()
    result = signup(SignupIn(username='audit-new', password='Audit-password-2026'), Response(), db)
    from app.models import User
    created = db.query(User).filter_by(username='audit-new').one()
    assert created.plan == 'business'
    assert 6 <= (created.trial_ends_at - datetime.utcnow()).days <= 7
    assert all(x['trial_days'] == 7 for x in list_plans(db))


def test_global_login_email_checked_before_invitation(env):
    from app.services.identity import ensure_login_email_available
    _, db, owner, other, seller, *_ = env
    with pytest.raises(HTTPException) as error:
        ensure_login_email_available(db, seller.email, 'driver')
    assert error.value.status_code == 409
    ensure_login_email_available(db, seller.email, 'agent', seller.id)


def test_maintenance_blocks_operations_but_keeps_admin_and_recovery(env, monkeypatch):
    import asyncio
    from contextlib import nullcontext
    from starlette.requests import Request
    import app.database as database
    from app.main import platform_maintenance
    from app.services.platform_settings import set_platform_setting
    _, db, *_ = env
    monkeypatch.setattr(database, 'SessionLocal', lambda: nullcontext(db))
    set_platform_setting(db, 'maintenance_mode', 'true'); db.commit()
    async def next_handler(request):
        return Response(status_code=204)
    def request(path):
        return asyncio.run(platform_maintenance(Request({'type': 'http', 'path': path, 'headers': []}), next_handler))
    assert request('/api/routes').status_code == 503
    for path in ('/api/admin/login', '/api/password-reset/request', '/api/logout', '/dashboard'):
        assert request(path).status_code == 204
    set_platform_setting(db, 'maintenance_mode', 'false'); db.commit()
    assert request('/api/routes').status_code == 204
