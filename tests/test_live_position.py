"""GPS lifecycle, tenant boundaries, cost bounds and shared ETA projection."""
from datetime import datetime, timedelta, timezone, time

import pytest

from test_agents_feature import env
from test_stability import seed_route


@pytest.fixture
def gps(env, monkeypatch):
    from app.routers import driver, operator, routes, tracking
    from app.services import live_position
    from app.core.utils import local_today
    client, db, owner, other, *_ = env
    plan, delivery, account = seed_route(env)
    plan.data_giro = local_today()
    delivery.customer.lat, delivery.customer.lon = 45.46, 9.19
    owner.delivery_signature_enabled = False
    db.commit()
    for module in (driver, operator, routes, tracking):
        client.app.include_router(module.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    calls = []
    def osrm(*args, **kwargs):
        calls.append((args, kwargs))
        return {(0, 1): {'min': 15, 'km': 8}}
    monkeypatch.setattr(live_position, 'osrm_table', osrm)
    return client, db, plan, delivery, account, owner, other, calls


def sample(**kwargs):
    return {'latitude':45.45, 'longitude':9.18, 'accuracy':20,
            'captured_at':datetime.now(timezone.utc).isoformat(), **kwargs}


def upload(gps, **kwargs):
    return gps[0].post(f'/api/driver/routes/{gps[2].id}/position', json=sample(**kwargs))


def test_snapshot_replaces_and_uploads_are_throttled_without_billing(gps, monkeypatch):
    from app.models import RoutePosition, RouteUsage
    from app.services import live_position
    client, db, plan, _, _, _, _, calls = gps
    assert upload(gps).json()['accepted']
    assert not upload(gps).json()['accepted']
    row = db.get(RoutePosition, plan.id)
    now = row.received_at + timedelta(seconds=31)
    monkeypatch.setattr(live_position, 'utcnow', lambda: now)
    assert upload(gps, longitude=9.20, captured_at=now.replace(tzinfo=timezone.utc).isoformat()).json()['accepted']
    assert db.query(RoutePosition).count() == 1
    assert db.get(RoutePosition, plan.id).longitude == 9.20
    assert len(calls) == 1
    assert db.query(RouteUsage).count() == 0
    for _ in range(4):
        result = client.get(f'/api/routes/{plan.id}/position')
        assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert len(calls) == 1  # Readers never recalculate ETA.


@pytest.mark.parametrize('state', ['bozza', 'programmato', 'completato', 'annullato'])
def test_no_upload_outside_active_route(gps, state):
    from app.models import RoutePosition
    gps[2].status = state; gps[1].commit()
    assert upload(gps).status_code == 409
    assert gps[1].query(RoutePosition).count() == 0


@pytest.mark.parametrize('fields', [
    {'latitude':91}, {'longitude':181}, {'accuracy':-1}, {'driver_id':1},
    {'captured_at':'2026-10-05T10:00:00'}, {'latitude':None},
])
def test_invalid_payload(gps, fields):
    assert upload(gps, **fields).status_code == 422


@pytest.mark.parametrize('fields', [
    {'accuracy':500},
    {'captured_at':(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()},
    {'captured_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()},
])
def test_unusable_samples_never_replace_last_good_fix(gps, fields):
    from app.models import RoutePosition
    assert upload(gps).json()['accepted']
    before = gps[1].get(RoutePosition,gps[2].id).captured_at
    assert upload(gps, **fields).json()['reason'] == 'unusable'
    assert gps[1].get(RoutePosition,gps[2].id).captured_at == before


def test_tenant_driver_anonymous_and_operator_boundaries(gps):
    from app.core.dependencies import current_user
    from app.models import Driver
    from app.routers import driver
    client, db, plan, _, account, owner, other, _ = gps
    assert upload(gps).status_code == 200
    client.app.dependency_overrides[current_user] = lambda: other
    assert client.get(f'/api/routes/{plan.id}/position').status_code == 404
    # Even an invalid cross-tenant assignment must not authorize a driver.
    plan.user_id = other.id; db.commit()
    assert upload(gps).status_code == 404
    plan.user_id = owner.id
    db.get(Driver, account.driver_id).is_active = False; db.commit()
    assert upload(gps).status_code == 404
    del client.app.dependency_overrides[driver.get_current_driver]
    del client.app.dependency_overrides[current_user]
    assert upload(gps).status_code == 401
    assert client.get(f'/api/routes/{plan.id}/position').status_code == 401
    assert client.post('/api/operator/bad-token/position',json=sample()).status_code == 404


def test_operator_start_and_gps_require_explicit_active_route(gps):
    client, db, plan, *_ = gps
    plan.status = 'programmato'; db.commit()
    assert client.get('/api/operator/test-route/position').json() == {'active':False}
    assert client.post('/api/operator/test-route/position',json=sample()).status_code == 409
    assert client.post('/api/operator/test-route/start').status_code == 200
    state = client.get(f'/api/driver/routes/{plan.id}/position')
    assert state.json() == {'active':True} and state.headers['cache-control'] == 'no-store'
    assert client.get('/api/operator/test-route').json()['route']['status'] == 'in_corso'
    assert client.post('/api/operator/test-route/position',json=sample()).json()['accepted']


def test_operator_cannot_write_position_for_foreign_driver_assignment(gps):
    from app.models import Driver, RoutePosition
    client, db, plan, _, _, _, other, _ = gps
    foreign = Driver(user_id=other.id,nome='Foreign')
    db.add(foreign);db.flush()
    plan.driver_id=foreign.id;db.commit()
    assert client.post('/api/operator/test-route/position',json=sample()).status_code == 404
    assert db.query(RoutePosition).count() == 0


@pytest.mark.parametrize('action', ['complete', 'cancel', 'last_stop'])
def test_terminal_events_clear_coordinates_and_reject_delayed_upload(gps, action):
    from app.models import RoutePosition
    client, db, plan, delivery, *_ = gps
    assert upload(gps).json()['accepted']
    path = f'/api/routes/{plan.id}/{action}' if action != 'last_stop' else f'/api/driver/delivery/{delivery.id}/missed'
    result = client.post(path, json={})
    assert result.status_code == 200, result.text
    assert db.query(RoutePosition).count() == 0
    assert upload(gps).status_code == 409
    assert client.get(f'/api/routes/{plan.id}/position').json()['position'] is None


def test_eta_is_shared_private_and_falls_back_when_stale(gps):
    from app.services.route_schedule import route_schedule_datetimes, LOCAL
    from app.services.delivery_tracking import public_projection
    from app.models import RoutePosition
    client, db, plan, delivery, *_ = gps
    delivery.arrivo_stimato = time(23,50); db.commit()
    assert upload(gps).json()['accepted']
    now = datetime.now(LOCAL)
    schedule = route_schedule_datetimes(plan, now=now)
    public = public_projection(db, delivery, plan, now=now)
    assert public['eta']['source'] == 'gps'
    assert public['eta']['at'] == schedule['deliveries'][delivery.id]['arrival'].isoformat()
    assert set(public) == {'status','scheduled_date','timezone','eta','stops_before','completed_at','refresh_after_seconds'}
    row = db.get(RoutePosition,plan.id)
    row.captured_at -= timedelta(seconds=100); db.commit()
    assert client.get(f'/api/routes/{plan.id}/position').json()['state'] == 'stale'
    assert route_schedule_datetimes(plan,now=now)['deliveries'][delivery.id]['source'] == 'planned'


def test_osrm_failure_and_missing_coordinates_do_not_use_paid_fallback(gps, monkeypatch):
    from app.services import live_position
    from app.models import RoutePosition
    monkeypatch.setattr(live_position,'osrm_table',lambda *a,**k: {})
    assert upload(gps).json()['accepted']
    assert gps[1].get(RoutePosition,gps[2].id).eta_at is None


def test_osrm_configuration_error_does_not_discard_gps(gps, monkeypatch):
    from app.services import live_position
    from app.models import RoutePosition
    def broken(*args, **kwargs):
        raise ValueError('Invalid OSRM URL')
    monkeypatch.setattr(live_position,'osrm_table',broken)
    assert upload(gps).json()['accepted']
    assert gps[1].get(RoutePosition,gps[2].id).eta_at is None


def test_next_stop_change_invalidates_cached_eta(gps):
    from app.models import Delivery, DeliveryStatus
    from app.services.route_schedule import route_schedule_datetimes
    client, db, plan, delivery, *_ = gps
    delivery.ordine = 1
    second = Delivery(route_plan_id=plan.id, cliente_nome='Second',indirizzo='Test',ordine=2,arrivo_stimato=time(23,55))
    db.add(second); db.commit()
    assert upload(gps).json()['accepted']
    state = DeliveryStatus(route_plan_id=plan.id,delivery_id=delivery.id,status='mancata',completata_il=datetime.now())
    db.add(state); db.commit()
    assert route_schedule_datetimes(plan,{delivery.id:state})['deliveries'][second.id]['source'] != 'gps'


def test_one_position_per_driver_across_routes_and_cleanup(gps):
    from app.models import RoutePosition, RoutePlan
    from app.services.live_position import cleanup_positions
    client, db, plan, *_ = gps
    assert upload(gps).json()['accepted']
    second = RoutePlan(user_id=plan.user_id,driver_id=plan.driver_id,nome='Next',data_giro=plan.data_giro,
                       orario_partenza=time(10),status='in_corso')
    db.add(second); db.commit()
    assert client.post(f'/api/driver/routes/{second.id}/position',json=sample()).json()['accepted']
    assert db.query(RoutePosition).count() == 1
    row = db.query(RoutePosition).one()
    assert row.route_plan_id == second.id
    row.received_at -= timedelta(days=2); db.commit()
    assert cleanup_positions(db) == 1


def test_osrm_retry_is_bounded_and_missing_coordinates_do_not_geocode(gps, monkeypatch):
    from app.services import live_position
    from app.models import RoutePosition
    client, db, plan, delivery, _, _, _, calls = gps
    delivery.customer.lat = delivery.customer.lon = None; db.commit()
    assert upload(gps).json()['accepted']
    assert calls == []
    row = db.get(RoutePosition,plan.id)
    delivery.customer.lat, delivery.customer.lon = 45.46, 9.19; db.commit()
    now = row.received_at + timedelta(seconds=121)
    monkeypatch.setattr(live_position,'utcnow',lambda:now)
    assert upload(gps,captured_at=now.replace(tzinfo=timezone.utc).isoformat()).json()['accepted']
    assert len(calls) == 1 and row.eta_at


def test_gps_eta_preserves_opening_times_unload_and_midnight(gps, monkeypatch):
    from app.services import live_position
    from app.services.route_schedule import route_schedule_datetimes, LOCAL
    from app.models import Delivery
    client, db, plan, first, *_ = gps
    first.ordine=1; first.tempo_scarico_min=20
    first.scarico_pomeriggio_da=time(23,30); first.scarico_pomeriggio_a=time(23,59)
    second=Delivery(route_plan_id=plan.id,cliente_nome='Tomorrow',indirizzo='Private',ordine=2,minuti_tappa=30)
    db.add(second);db.commit()
    now=datetime.combine(plan.data_giro,time(23),LOCAL)
    monkeypatch.setattr(live_position,'utcnow',lambda:now.astimezone(timezone.utc).replace(tzinfo=None))
    assert upload(gps,captured_at=now.isoformat()).json()['accepted']
    schedule=route_schedule_datetimes(plan,now=now)['deliveries']
    assert schedule[first.id]['arrival'].time()==time(23,30)
    assert schedule[second.id]['arrival'].time()==time(0,20)
    assert schedule[second.id]['arrival'].date()==plan.data_giro+timedelta(days=1)


def test_expired_eta_and_reassignment_cannot_be_made_fresh_by_new_gps(gps):
    from app.models import RoutePosition
    from app.services.route_schedule import route_schedule_datetimes
    from app.services.live_position import position_view
    client, db, plan, delivery, *_ = gps
    assert upload(gps).json()['accepted']
    row=db.get(RoutePosition,plan.id)
    row.eta_calculated_at-=timedelta(seconds=151);db.commit()
    assert route_schedule_datetimes(plan)['deliveries'][delivery.id]['source']!='gps'
    plan.driver_id=None;db.commit()
    assert position_view(plan)['position'] is None
    assert route_schedule_datetimes(plan)['deliveries'][delivery.id]['source']!='gps'
