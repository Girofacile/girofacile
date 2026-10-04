"""Tracking capabilities, public allowlist and operational ETA integration."""
from datetime import datetime, time, timedelta

import pytest

from test_agents_feature import env
from test_stability import seed_route
from test_routing_architecture import routing_env, payload, saved_route


@pytest.fixture
def tracking_env(env, monkeypatch):
    from app.routers import tracking, driver
    from app.models import Delivery
    from app.services import object_storage
    from pod_fake import FakeStorage
    client, db, owner, *_ = env
    plan, first, account = seed_route(env)
    owner.delivery_signature_enabled = False
    plan.status = 'programmato'
    first.ordine, first.arrivo_stimato, first.partenza_stimata = 1, time(9), time(9, 10)
    second = Delivery(route_plan_id=plan.id, cliente_nome='SEGRETO cliente', indirizzo='SEGRETO indirizzo',
                      ordine=2, arrivo_stimato=time(10), partenza_stimata=time(10, 10), note='SEGRETO nota')
    db.add(second); db.commit()
    client.app.include_router(tracking.router)
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    monkeypatch.setattr(object_storage, 'get_storage', lambda: FakeStorage())
    tracking._requests.clear()
    return client, db, owner, plan, first, second, env[3]


def issue(client, delivery):
    response = client.post(f'/api/deliveries/{delivery.id}/tracking')
    assert response.status_code == 200, response.text
    url = response.json()['url']
    assert '/tracking#' in url and '?' not in url
    return url.split('#')[1]


def read(client, token):
    return client.get('/api/public/tracking', headers={'X-Tracking-Token': token})


def test_same_link_can_be_reopened_and_other_delivery_has_different_capability(tracking_env):
    client, db, _, plan, first, second, _ = tracking_env
    from app.models import DeliveryTrackingLink
    token = issue(client, first)
    assert issue(client, first) == token
    assert issue(client, second) != token
    assert db.query(DeliveryTrackingLink).count() == 2
    row = db.query(DeliveryTrackingLink).filter_by(delivery_id=first.id).one()
    assert token != row.selector and len(row.selector) == 64
    body = read(client, token).json()
    assert body['eta']['at'][11:16] == '09:00'
    assert read(client, issue(client, second)).json()['eta']['at'][11:16] == '10:00'


def test_public_response_contains_only_customer_allowlist(tracking_env):
    client, db, _, plan, first, second, _ = tracking_env
    token = issue(client, second)
    response = read(client, token)
    assert response.status_code == 200
    assert set(response.json()) == {'status', 'scheduled_date', 'timezone', 'eta', 'stops_before', 'completed_at', 'refresh_after_seconds'}
    assert set(response.json()['eta']) == {'at', 'source', 'updated_at'}
    assert 'SEGRETO' not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert response.json()['stops_before'] is None
    assert response.json()['eta']['source'] == 'planned'
    assert response.json()['eta']['updated_at'] is None
    assert client.post('/api/public/tracking', headers={'X-Tracking-Token': token}).status_code == 405
    from app.models import DeliveryStatus
    assert db.query(DeliveryStatus).count() == 0


@pytest.mark.parametrize('bad', ['', '1', '../routes/1', 'f'*64+'.'+'0'*64, 'x'*10000], ids=['empty','numeric','path','unknown','oversized'])
def test_invalid_links_are_generic_404(tracking_env, bad):
    response = read(tracking_env[0], bad)
    assert response.status_code == 404
    assert response.json()['detail'] == 'Link non disponibile o scaduto'


def test_tampering_revocation_and_expiry(tracking_env):
    client, db, _, plan, first, second, _ = tracking_env
    from app.models import DeliveryTrackingLink
    from app.services.delivery_tracking import utcnow
    token = issue(client, first)
    signature = ('0' if token[-1] != '0' else '1')
    assert read(client, token[:-1] + signature).status_code == 404
    other = issue(client, second)
    assert read(client, token.split('.')[0] + '.' + other.split('.')[1]).status_code == 404
    assert client.delete(f'/api/deliveries/{first.id}/tracking').status_code == 200
    assert read(client, token).status_code == 404
    replacement = issue(client, first)
    assert replacement != token
    row = db.query(DeliveryTrackingLink).filter_by(delivery_id=first.id).one()
    row.expires_at = utcnow() - timedelta(seconds=1); db.commit()
    assert read(client, replacement).status_code == 404
    assert read(client, other).status_code == 200


def test_company_isolation_and_anonymous_management_denied(tracking_env):
    client, db, owner, plan, first, second, other = tracking_env
    from app.core.dependencies import current_user
    token = issue(client, first)
    client.app.dependency_overrides[current_user] = lambda: other
    assert client.post(f'/api/deliveries/{first.id}/tracking').status_code == 404
    assert client.delete(f'/api/deliveries/{first.id}/tracking').status_code == 404
    assert read(client, token).status_code == 200  # possession grants this one read, independent of cookies
    del client.app.dependency_overrides[current_user]
    assert client.post(f'/api/deliveries/{first.id}/tracking').status_code == 401
    assert client.delete(f'/api/deliveries/{first.id}/tracking').status_code == 401


def test_draft_and_past_deliveries_cannot_issue_links(tracking_env):
    client, db, _, plan, first, *_ = tracking_env
    plan.status = 'bozza'; db.commit()
    assert client.post(f'/api/deliveries/{first.id}/tracking').status_code == 409
    plan.status = 'programmato'; plan.data_giro -= timedelta(days=20); db.commit()
    assert client.post(f'/api/deliveries/{first.id}/tracking').status_code == 409


def test_delay_from_start_and_previous_stop_is_shared_with_dashboard(tracking_env):
    client, db, _, plan, first, second, _ = tracking_env
    from app.models import DeliveryStatus
    from app.services.route_schedule import live_route_schedule
    token = issue(client, second)
    plan.status = 'in_corso'
    plan.started_at = datetime.combine(plan.data_giro, time(8, 25)); db.commit()
    result = read(client, token).json()
    assert result['eta']['at'][11:16] == '10:25'
    assert result['eta']['source'] == 'execution'
    assert result['stops_before'] == 1
    state = DeliveryStatus(route_plan_id=plan.id, delivery_id=first.id, status='mancata',
                           completata_il=datetime.combine(plan.data_giro, time(9, 50)))
    db.add(state); db.commit()
    result = read(client, token).json()
    assert result['eta']['at'][11:16] == '10:40'
    assert result['stops_before'] == 0
    assert live_route_schedule(plan, {first.id:state})['delivery_times'][second.id] == '10:40'


@pytest.mark.parametrize('action,status', [('complete','completata'), ('missed','mancata')])
def test_driver_updates_are_visible_without_copying_state(tracking_env, action, status):
    client, db, _, plan, first, second, _ = tracking_env
    token = issue(client, first)
    # Use the real driver mutation endpoint, with storage replaced by a test fake.
    response = client.post(f'/api/driver/delivery/{first.id}/{action}', json={})
    assert response.status_code == 200, response.text
    result = read(client, token).json()
    assert result['status'] == status and result['completed_at']
    assert result['eta']['at'] is None and result['stops_before'] is None
    assert result['refresh_after_seconds'] == 0


def test_cancelled_and_closed_routes_do_not_advertise_an_eta(tracking_env):
    client, db, _, plan, first, *_ = tracking_env
    token = issue(client, first)
    for state, expected in [('annullato','annullata'), ('completato','non_disponibile')]:
        plan.status = state; db.commit()
        data = read(client, token).json()
        assert data['status'] == expected and data['eta']['at'] is None
        assert data['stops_before'] is None


def test_missing_and_stale_eta_are_not_fabricated(tracking_env):
    client, db, _, plan, first, second, _ = tracking_env
    from app.services.delivery_tracking import public_projection, LOCAL
    first.arrivo_stimato = None
    token = issue(client, first)
    assert read(client, token).json()['eta']['at'] is None
    later = datetime.combine(plan.data_giro, time(12), LOCAL)
    result = public_projection(db, second, plan, now=later)
    assert result['eta']['at'] is None


def test_schedule_rolls_over_midnight_and_keeps_date(tracking_env):
    _, db, _, plan, first, second, _ = tracking_env
    from app.services.route_schedule import route_schedule_datetimes, live_route_schedule
    plan.orario_partenza = time(23)
    first.arrivo_stimato, first.partenza_stimata = time(23, 50), time(0, 10)
    second.arrivo_stimato, second.partenza_stimata = time(0, 40), time(0, 50)
    plan.orario_rientro_stimato = time(1)
    data = route_schedule_datetimes(plan)['deliveries']
    assert data[first.id]['arrival'].date() == plan.data_giro
    assert data[second.id]['arrival'].date() == plan.data_giro + timedelta(days=1)
    assert live_route_schedule(plan)['delivery_times'][second.id] == '00:40'


def test_page_has_no_external_assets_and_safe_headers(tracking_env):
    response = tracking_env[0].get('/tracking')
    assert response.status_code == 200
    assert 'frame-ancestors' in response.headers['content-security-policy']
    assert response.headers['cache-control'] == 'no-store'
    assert 'noindex' in response.headers['x-robots-tag']
    assert 'name="viewport"' in response.text
    assert 'src="https://' not in response.text


def test_throttling_happens_before_token_resolution(tracking_env):
    client = tracking_env[0]
    for _ in range(120):
        assert read(client, '').status_code == 404
    response = read(client, '')
    assert response.status_code == 429 and response.headers['retry-after'] == '60'


def test_recalculation_revokes_link_even_if_database_reuses_delivery_id(routing_env):
    from app.routers import tracking
    from app.models import Delivery, DeliveryTrackingLink, RoutePlan
    client, db, *_ = routing_env
    tracking._requests.clear()
    client.app.include_router(tracking.router)
    created = saved_route(routing_env)
    plan = db.get(RoutePlan, created['id'])
    plan.status = 'programmato'; db.commit()
    first = db.query(Delivery).filter_by(route_plan_id=plan.id).one()
    token = issue(client, first)
    data = payload(routing_env)
    data['route_id'] = plan.id
    response = client.post('/api/routes/recalculate-manual', json=data)
    assert response.status_code == 200, response.text
    assert db.query(DeliveryTrackingLink).count() == 0
    assert read(client, token).status_code == 404
    db.expire_all()
    new = db.query(Delivery).filter_by(route_plan_id=plan.id).one()
    assert issue(client, new) != token


def test_recalculation_failure_keeps_existing_link(routing_env):
    from app.routers import tracking
    from app.models import RoutePlan, Delivery
    client, db, *_ = routing_env
    tracking._requests.clear()
    client.app.include_router(tracking.router)
    created = saved_route(routing_env)
    plan = db.get(RoutePlan, created['id'])
    plan.status = 'programmato'; db.commit()
    first = db.query(Delivery).filter_by(route_plan_id=plan.id).one()
    token = issue(client, first)
    data = payload(routing_env)
    data.update(route_id=plan.id, deposit_id=999999)
    assert client.post('/api/routes/recalculate-manual', json=data).status_code == 400
    assert read(client, token).status_code == 200
