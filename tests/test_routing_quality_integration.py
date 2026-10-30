"""Fresh operational acceptance cases for the October 2026 fleet controls.

Only the isolated account fixture is reused. Stops, vehicles, bookings, road
times and expectations are new. Road, traffic and toll boundaries are frozen;
the API, resource availability, search, schedule, revision and persistence run
unchanged. These scenarios prove integration, not global optimality.
"""
from copy import deepcopy
from datetime import date, time
from types import SimpleNamespace

import pytest
import requests

from test_agents_feature import env
from stop_fixture import verified_stop


@pytest.fixture
def quality_api(env, monkeypatch):
    from app import optimizer
    from app.models import Deposit, Driver, SaaSPlatformSetting, Vehicle
    from app.routers import fleet_planning, routes
    from app.services import road_routing, route_enrichment, traffic_provider
    from app.core.clock import utc_now

    client, db, owner, *_ = env
    owner.has_time_windows = True
    client.app.include_router(routes.router)
    client.app.include_router(fleet_planning.router)
    depot = Deposit(user_id=owner.id, nome='Audit ottobre', indirizzo='Deposito audit fittizio',
                    lat=44.91, lon=9.21)
    vehicles = [
        Vehicle(user_id=owner.id, nome='Audit diesel', capacita_kg=8, capacita_colli=8,
                alimentazione='gasolio', consumo_primario_100km=8, consumo_l_100km=8),
        Vehicle(user_id=owner.id, nome='Audit elettrico', capacita_kg=8, capacita_colli=8,
                alimentazione='elettrico', consumo_kwh_100km=18),
    ]
    drivers = [Driver(user_id=owner.id, nome='Audit Elisa'), Driver(user_id=owner.id, nome='Audit Neri')]
    for driver in drivers:
        driver.work_schedule = {'start': '07:30', 'end': '12:00', 'breaks': []}
    margin = SaaSPlatformSetting(key='fleet_traffic_margin', value='1')
    db.add_all([depot, *vehicles, *drivers, margin])
    db.commit()

    def forbidden(*args, **kwargs):
        pytest.fail('Quality integration attempted a real external provider')

    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    matrix_calls, traffic_calls = [], []

    def matrix(db, uid, points, keys, **kwargs):
        matrix_calls.append(len(points))
        return road_routing.RoadMatrix({
            (i, j): {'km': 0.0 if i == j else 2.0, 'min': 0.0 if i == j else 7.0}
            for i in range(len(points)) for j in range(len(points))
        }, source='osrm')

    class FrozenTraffic:
        name = 'audit-frozen'

        def calculate(self, points, departure, **kwargs):
            traffic_calls.append(len(points) - 1)
            return dict(provider=self.name, status='updated',
                        legs=[{'duration': 420, 'distance': 2000} for _ in points[1:]],
                        geometries=[], departure_time=departure,
                        calculated_at=utc_now().isoformat() + 'Z', version=1)

    monkeypatch.setattr(optimizer, 'build_distance_matrix', matrix)
    monkeypatch.setattr(traffic_provider, 'get_traffic_provider', lambda *a: FrozenTraffic())
    monkeypatch.setattr(route_enrichment, 'get_traffic_provider', lambda *a: FrozenTraffic())
    monkeypatch.setattr(road_routing, 'road_route', lambda *a, **k: {'geometries': [], 'legs': []})
    monkeypatch.setattr(route_enrichment, 'get_toll_calculator', lambda *a: SimpleNamespace(
        estimate=lambda *args, **kwargs: dict(provider='audit-frozen', status='estimated', amount_eur=0)))

    body = dict(nome='Audit operativo ottobre', data_giro='2099-10-30', orario_partenza='07:40',
        deposit_id=depot.id, strategy='balanced', rientro_deposito=True,
        resources=[dict(vehicle_id=v.id, driver_id=d.id, energy_price_primary=1.5,
                        energy_price_electric=1.5, energy_price_mode='manual')
                   for v, d in zip(vehicles, drivers)],
        consegne=[verified_stop(owner.id, cliente_nome=f'Audit ottobre {i}',
                    indirizzo=f'Via Audit {700+i}, località fittizia', lat=44.93+i*.002,
                    lon=9.25+i*.003, peso_kg=4, colli=1, tempo_scarico_min=4)
                  for i in range(3)])
    return SimpleNamespace(client=client, db=db, owner=owner, body=body, drivers=drivers,
                           vehicles=vehicles, margin=margin, matrix_calls=matrix_calls,
                           traffic_calls=traffic_calls)


def calculate(ctx, body=None):
    response = ctx.client.post('/api/fleet-planning/preview', json=body or ctx.body)
    assert response.status_code == 200, response.text
    return response.json()


def action(ctx, plan, name, **values):
    response = ctx.client.post(f"/api/fleet-planning/{plan['id']}/{name}",
                              json={'version': plan['version'], **values})
    assert response.status_code == 200, response.text
    return response.json()


def test_card_shift_pause_and_energy_override_survive_revision_and_programming(quality_api):
    from app.models import RoutePlan
    ctx = quality_api
    body = deepcopy(ctx.body)
    # Saved driver defaults deliberately cannot accommodate the departure.
    for driver in ctx.drivers:
        driver.work_schedule = {'start': '09:00', 'end': '12:00', 'breaks': []}
    ctx.db.commit()
    overrides = [
        {'start': '07:35', 'end': '11:00', 'breaks': [{'start': '07:45', 'end': '08:00'}]},
        {'start': '07:30', 'end': '11:30', 'breaks': []},
    ]
    for resource, schedule in zip(body['resources'], overrides):
        resource['driver_schedule'] = schedule
    body['resources'][0].update(energy_price_mode='automatic', energy_price_primary=2.25)
    body['resources'][1].update(energy_price_mode='manual', energy_price_electric=0.45)
    plan = calculate(ctx, body)
    assert not plan['unassigned'] and len(plan['routes']) == 2
    assignments = [None] * 3
    for route in plan['routes']:
        index = route['resource']
        count = len(route['stop_indexes'])
        # Every leg is seven minutes. The first driver's fixed break adds 15.
        assert route['result']['total_min'] == 7*(count+1) + 4*count + (15 if index == 0 else 0)
        assert bool(route['result']['driver_breaks']) is (index == 0)
        for stop in route['stop_indexes']:
            assignments[stop] = index
    plan = action(ctx, plan, 'revise', assignments=assignments)
    plan = action(ctx, plan, 'confirm')
    for row in ctx.db.query(RoutePlan).filter(RoutePlan.id.in_(plan['route_ids'])):
        index = next(i for i, resource in enumerate(body['resources']) if resource['driver_id'] == row.driver_id)
        assert row.driver_schedule == overrides[index]
        assert row.energy_price_mode == body['resources'][index]['energy_price_mode']
        assert row.energy_price_primary == body['resources'][index]['energy_price_primary']
        assert row.energy_price_electric == body['resources'][index]['energy_price_electric']
    provider_calls = len(ctx.traffic_calls)
    plan = action(ctx, plan, 'program')
    assert plan['status'] == 'programmed'
    assert len(ctx.traffic_calls) == provider_calls, 'Fresh preview traffic should be reused'
    assert all(row.status == 'programmato' for row in ctx.db.query(RoutePlan))
    assert len(ctx.matrix_calls) == 2, 'One shared matrix per initial/revised search'


def _book_first_pair(ctx):
    from app.models import RoutePlan
    resource = ctx.body['resources'][0]
    booking = RoutePlan(user_id=ctx.owner.id, nome='Audit appuntamento successivo',
        data_giro=date(2099, 10, 30), orario_partenza=time(8, 1), totale_minuti=45,
        driver_id=resource['driver_id'], vehicle_id=resource['vehicle_id'], status='programmato')
    ctx.db.add(booking)
    ctx.db.commit()
    return booking


def test_real_next_booking_limits_assignment_without_hiding_available_pair(quality_api):
    ctx = quality_api
    _book_first_pair(ctx)
    availability = ctx.client.get('/api/resources/availability', params={
        'data_giro': '2099-10-30', 'orario': '07:40', 'preview_minutes': 1}).json()
    assert all(item['available'] for item in availability['vehicles'])
    plan = calculate(ctx)
    routes = {route['resource']: route for route in plan['routes']}
    assert not plan['unassigned']
    # A one-stop round trip takes 18 minutes; two stops need 29 and cross 08:01.
    assert len(routes[0]['stop_indexes']) == 1 and routes[0]['result']['total_min'] == 18
    assert len(routes[1]['stop_indexes']) == 2 and routes[1]['result']['total_min'] == 29


def test_database_traffic_margin_changes_feasibility_before_real_traffic_check(quality_api):
    ctx = quality_api
    _book_first_pair(ctx)
    body = deepcopy(ctx.body)
    body['consegne'] = body['consegne'][:2]
    base = calculate(ctx, body)
    assert {route['resource'] for route in base['routes']} == {0, 1}
    ctx.margin.value = '1.30'
    ctx.db.commit()
    cautious = calculate(ctx, body)
    assert not cautious['unassigned']
    assert [route['resource'] for route in cautious['routes']] == [1]
    route = cautious['routes'][0]
    assert route['result']['total_min'] == 35.3
    assert all(stop['minuti_tappa'] == 9.1 and stop['km_tappa'] == 2 for stop in route['result']['ordered'])
    assert route['traffic']['total_min'] == 29, 'Post-search traffic is separately evaluated'


def test_energy_prices_change_estimate_but_not_the_declared_fleet_objective(quality_api):
    ctx = quality_api
    body = deepcopy(ctx.body)
    body['strategy'] = 'efficient'
    body['consegne'] = body['consegne'][:2]
    first = calculate(ctx, body)
    for resource in body['resources']:
        resource['energy_price_primary'] *= 10
        resource['energy_price_electric'] *= 10
    second = calculate(ctx, body)
    assert [(r['resource'], r['stop_indexes']) for r in first['routes']] == [
        (r['resource'], r['stop_indexes']) for r in second['routes']]
    assert [r['result']['total_km'] for r in first['routes']] == [r['result']['total_km'] for r in second['routes']]
    assert [r['fuel_cost'] for r in second['routes']] == [round(r['fuel_cost']*10, 2) for r in first['routes']]


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=(
    'Known audit finding: save_route_result replaces an explicit zero primary energy price '
    'with RoutePlanIn.prezzo_carburante_litro default 1.75 (app/routers/routes.py:477).'))
def test_explicit_zero_manual_energy_price_matches_preview_after_confirmation(quality_api):
    from app.models import RoutePlan
    ctx = quality_api
    for vehicle in ctx.vehicles:
        vehicle.alimentazione = 'gasolio'
        vehicle.consumo_primario_100km = vehicle.consumo_l_100km = 8
        vehicle.consumo_kwh_100km = 0
    ctx.db.commit()
    body = deepcopy(ctx.body)
    body['strategy'] = 'efficient'
    body['consegne'] = body['consegne'][:2]
    for resource in body['resources']:
        resource.update(energy_price_mode='manual', energy_price_primary=0, energy_price_electric=0)
    plan = calculate(ctx, body)
    assert plan['routes'] and all(route['fuel_cost'] == 0 for route in plan['routes'])
    saved = action(ctx, plan, 'confirm')
    rows = ctx.db.query(RoutePlan).filter(RoutePlan.id.in_(saved['route_ids'])).all()
    assert rows and all(row.energy_price_primary == 0 and row.costo_carburante == 0 for row in rows)


def test_invalid_card_schedule_and_window_fail_before_any_plan_is_persisted(quality_api):
    from app.fleet_models import FleetPlan
    ctx = quality_api
    for target, values in [
        ('stop', {'scarico_mattina_da': '08:25', 'scarico_mattina_a': '08:10'}),
        ('resource', {'driver_schedule': {'start': '07:30', 'end': '07:00'}}),
        ('resource', {'driver_schedule': {'start': '07:30', 'end': '12:00', 'breaks': [
            {'start': '09:10', 'end': '09:40'}, {'start': '09:25', 'end': '09:50'}]}}),
    ]:
        body = deepcopy(ctx.body)
        body['consegne' if target == 'stop' else 'resources'][0].update(values)
        response = ctx.client.post('/api/fleet-planning/preview', json=body)
        assert response.status_code == 422, response.text
    assert ctx.db.query(FleetPlan).count() == 0
    assert ctx.matrix_calls == [] and ctx.traffic_calls == []
