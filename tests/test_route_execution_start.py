"""Every delivery command shares the explicit route start rules."""
from datetime import time, timedelta
import pytest
from test_agents_feature import env
from test_stability import seed_route

COMMANDS = [('driver', a) for a in ('start', 'note', 'complete', 'missed', 'signature')]
COMMANDS += [('operator', a) for a in ('start', 'note', 'complete', 'missed')]


def prepare(env, *, days=0, status='programmato', signature=False):
    from app.core.utils import local_today
    from app.routers import driver, operator
    client, db, owner, *_ = env
    route, delivery, account = seed_route(env)
    route.status, route.data_giro = status, local_today() + timedelta(days=days)
    owner.delivery_signature_enabled = signature
    db.commit()
    client.app.include_router(driver.router)
    client.app.include_router(operator.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    return client, db, owner, route, delivery


def path(portal, action, route, delivery):
    prefix = '/api/driver' if portal == 'driver' else '/api/operator/test-route'
    if action == 'start':
        return f'{prefix}/routes/{route.id}/start' if portal == 'driver' else f'{prefix}/start'
    return f'{prefix}/delivery/{delivery.id}/{action}'


@pytest.mark.parametrize('portal,action', COMMANDS)
@pytest.mark.parametrize('state', ['bozza', 'programmato'])
def test_future_route_cannot_start_through_any_command(env, portal, action, state):
    from app.models import DeliveryStatus, RouteUsage
    client, db, _, route, delivery = prepare(env, days=1, status=state, signature=action == 'signature')
    response = client.post(path(portal, action, route, delivery), json={'note': 'Prima della partenza'})
    assert response.status_code == 409, response.text
    assert 'futura' in response.json()['detail']
    assert route.status == state and route.started_at is None
    assert db.query(RouteUsage).count() == db.query(DeliveryStatus).count() == 0


@pytest.mark.parametrize('portal,action', [('driver', 'start'), ('operator', 'start'),
    ('driver', 'note'), ('operator', 'note'), ('driver', 'complete'), ('operator', 'missed')])
@pytest.mark.parametrize('resource', ['driver', 'vehicle'])
def test_running_resource_blocks_explicit_and_delivery_starts(env, portal, action, resource):
    from app.models import DeliveryStatus, RoutePlan, RouteUsage, Vehicle
    client, db, owner, route, delivery = prepare(env)
    running = RoutePlan(user_id=owner.id, nome='Già in corso', data_giro=route.data_giro,
                        orario_partenza=time(8), status='in_corso')
    if resource == 'driver':
        running.driver_id = route.driver_id
    else:
        vehicle = Vehicle(user_id=owner.id, nome='Mezzo condiviso')
        db.add(vehicle)
        db.flush()
        route.vehicle_id = running.vehicle_id = vehicle.id
    db.add(running)
    db.commit()
    response = client.post(path(portal, action, route, delivery), json={'note': 'Attendere'})
    assert response.status_code == 409, response.text
    assert route.status == 'programmato' and route.started_at is None
    assert running.status == 'in_corso'
    assert db.query(RouteUsage).count() == db.query(DeliveryStatus).count() == 0


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_allowed_note_and_repeated_explicit_start_count_once(env, portal):
    from app.models import RouteUsage
    client, db, _, route, delivery = prepare(env)
    assert client.post(path(portal, 'note', route, delivery), json={'note': 'Pronti'}).status_code == 200
    started = route.started_at
    assert route.status == 'in_corso' and started is not None
    assert client.post(path(portal, 'start', route, delivery), json={}).status_code == 200
    assert client.post(path(portal, 'note', route, delivery), json={'note': 'In partenza'}).status_code == 200
    assert route.started_at == started
    assert db.query(RouteUsage).count() == 1


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_legacy_running_route_can_close_after_expiry(env, portal):
    from app.models import RouteUsage
    client, db, owner, route, delivery = prepare(env, days=1, status='in_corso')
    owner.plan_status = 'expired'
    db.commit()
    response = client.post(path(portal, 'missed', route, delivery), json={})
    assert response.status_code == 200, response.text
    assert route.status == 'completato'
    assert db.query(RouteUsage).count() == 1
