"""Fresh fleet audit cases and an adapter to the current public planning service.

Fixtures were created for the 2026-10-30 campaign. They do not import historical
simulation scenarios or their reference solvers. ``max_minutes`` in a fixture
means resource availability before another booking/end of day; the removed
user-configurable maximum route duration is deliberately not revived.
"""
from contextlib import ExitStack
from copy import deepcopy
import math
import os
import random
import socket
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


def _stop(index, *, weight=1, packages=1, service=4, **updates):
    row = dict(customer_id=index + 1, cliente_nome=f"Audit flotta {index + 1}",
               indirizzo=f"Via Campagna Fittizia {index + 1}",
               lat=45.47 + index * .0007, lon=9.18 + index * .0009,
               peso_kg=weight, colli=packages, tempo_scarico_min=service,
               ztl=False, sponda=False)
    row.update(updates)
    return row


def _resource(weight=1000, packages=1000, *, available=840, schedule=None, **updates):
    row = dict(capacita_kg=weight, capacita_colli=packages,
               ha_sponda=True, accesso_ztl=True, max_minutes=available,
               driver_schedule=deepcopy(schedule or {
                   'start': '08:00', 'end': '23:00', 'breaks': []}))
    row.update(updates)
    return row


def _uniform(n, *, km=2.7, minutes=7.0):
    return {(i, j): {'km': 0.0 if i == j else float(km),
                     'min': 0.0 if i == j else float(minutes)}
            for i in range(n + 1) for j in range(n + 1)}


def _geometry(n, seed, *, spread=5):
    """A new directed road-like metric; time and distance are not proportional."""
    rng = random.Random(seed)
    xy = [(0.0, 0.0)] + [(rng.uniform(-spread, spread), rng.uniform(-spread, spread))
                            for _ in range(n)]
    matrix = {}
    for i, (ax, ay) in enumerate(xy):
        for j, (bx, by) in enumerate(xy):
            distance = math.hypot(bx - ax, by - ay)
            matrix[i, j] = {
                'km': 0.0 if i == j else .23 + distance * 1.13 + (bx - ax) * .08,
                'min': 0.0 if i == j else 1.4 + distance * 2.1 + (by - ay) * .13,
            }
    coords = [{'lat': 45.47 + y / 111, 'lon': 9.18 + x / 78} for x, y in xy]
    return matrix, coords


def _case(identifier, family, stops, resources, matrix=None, *, returning=True,
          reference='exact', seed=20261030, witness=None, **updates):
    result = dict(id=identifier, kind='fleet', family=family, seed=seed,
                  stops=stops, resources=resources, matrix=matrix or _uniform(len(stops)),
                  return_depot=returning, start_time='08:00', reference=reference,
                  traffic_margin=1.0,
                  availability_semantics='minutes until a conflicting booking or midnight')
    if witness is not None:
        result['witness'] = witness
    result.update(updates)
    return result


def fleet_cases(quick=False):
    """Return newly authored, deterministic cases, never generated from outputs.

    All small cases have at most six stops and three resources, permitting an
    independent global reference. Large cases have an explicit feasible witness;
    their witness is a comparison candidate, not a claim of optimality.
    """
    cases = []
    cases.append(_case('fleet-new-weight-repacking', 'weight-capacity',
        [_stop(i, weight=w, service=2) for i, w in enumerate((9, 8, 6, 5, 4, 4))],
        [_resource(18), _resource(18)], witness=[[0, 3, 4], [1, 2, 5]]))
    cases.append(_case('fleet-new-parcels-repacking', 'parcel-capacity',
        [_stop(i, packages=p, service=3) for i, p in enumerate((5, 4, 3, 3, 2, 1))],
        [_resource(None, 9), _resource(None, 9)], witness=[[0, 2, 5], [1, 3, 4]]))
    cases.append(_case('fleet-new-soft-equipment', 'soft-equipment',
        [_stop(i, sponda=i in (0, 1, 4), ztl=i in (2, 3, 4)) for i in range(5)],
        [_resource(3, ha_sponda=True, accesso_ztl=False),
         _resource(3, ha_sponda=False, accesso_ztl=True)]))
    cases.append(_case('fleet-new-coverage-before-equipment', 'coverage-priority',
        [_stop(i, weight=4, sponda=True) for i in range(4)],
        [_resource(4, ha_sponda=True), _resource(12, ha_sponda=False)]))
    pause = {'start': '08:00', 'end': '17:00',
             'breaks': [{'start': '08:10', 'end': '08:40'}]}
    rows = [_stop(0, service=5, scarico_mattina_da='08:00', scarico_mattina_a='08:20')]
    rows += [_stop(i, service=7, scarico_mattina_da='08:35', scarico_mattina_a='10:00')
             for i in range(1, 5)]
    cases.append(_case('fleet-new-urgent-stop-break-conflict', 'break-window-interaction',
        rows, [_resource(3, schedule=pause), _resource(3)]))
    cases.append(_case('fleet-new-shift-start-is-not-delayed', 'driver-shift-start',
        [_stop(i, service=4, scarico_mattina_da='09:00', scarico_mattina_a='11:00')
         for i in range(4)],
        [_resource(schedule={'start': '09:00', 'end': '17:00', 'breaks': []}),
         _resource()]))
    cases.append(_case('fleet-new-upcoming-bookings', 'availability-horizon',
        [_stop(i, service=10) for i in range(6)],
        [_resource(6, available=42), _resource(6, available=75), _resource(6, available=120)],
        _uniform(6, minutes=6)))
    pause_return = {'start': '08:00', 'end': '17:00',
                    'breaks': [{'start': '08:25', 'end': '08:45'}]}
    cases.append(_case('fleet-new-return-through-break', 'return-break',
        [_stop(i, service=3) for i in range(3)],
        [_resource(3, schedule=pause_return), _resource(3)], _uniform(3, minutes=10)))
    for returning in (False, True):
        matrix = _uniform(4, minutes=5)
        for node in range(1, 5):
            matrix[0, node]['min'] = matrix[node, 0]['min'] = 15
        cases.append(_case('fleet-new-return-policy-' + ('closed' if returning else 'open'),
            'return-policy', [_stop(i, service=4) for i in range(4)],
            [_resource(4, available=40), _resource(4, available=40)], matrix,
            returning=returning))
    cases.append(_case('fleet-new-zero-and-unlimited-capacity', 'capacity-boundaries',
        [_stop(0, weight=0, packages=0)] + [_stop(i, weight=5, packages=2) for i in range(1, 4)],
        [_resource(0, 0), _resource(None, None)]))
    cases.append(_case('fleet-new-two-service-windows', 'dual-windows',
        [_stop(i, service=10, scarico_mattina_da='08:40', scarico_mattina_a='09:05',
               scarico_pomeriggio_da='13:00', scarico_pomeriggio_a='14:00') for i in range(5)],
        [_resource(3), _resource(3)], _uniform(5, minutes=18)))
    for travel in (17.5, 17.50001):
        cases.append(_case('fleet-new-availability-ceil-' + ('boundary' if travel == 17.5 else 'over'),
            'unrounded-availability', [_stop(i, service=0) for i in range(2)],
            [_resource(1, available=35), _resource(1, available=36)],
            _uniform(2, minutes=travel)))
    for margin in (1.0, 1.15):
        rows = [_stop(0, service=5, scarico_mattina_da='08:00', scarico_mattina_a='08:16')]
        rows += [_stop(i, service=5, scarico_mattina_da='08:00', scarico_mattina_a='08:55')
                 for i in range(1, 3)]
        cases.append(_case(f'fleet-new-prudent-margin-{margin}', 'traffic-margin', rows,
            [_resource(2), _resource(2)], _uniform(3, minutes=10), traffic_margin=margin))
    cases.append(_case('fleet-new-energy-prices-per-resource', 'energy-accounting',
        [_stop(i, service=4) for i in range(3)],
        [_resource(2, alimentazione='elettrico', consumo_kwh_100km=19,
                   energy_price_electric=.41),
         _resource(2, alimentazione='gasolio', consumo_primario_100km=8.7,
                   energy_price_primary=1.91)], _uniform(3, km=4.3)))
    if quick:
        # Keep every new-feature family represented while bounding CI time.
        wanted = {'fleet-new-weight-repacking', 'fleet-new-soft-equipment',
                  'fleet-new-coverage-before-equipment', 'fleet-new-urgent-stop-break-conflict',
                  'fleet-new-shift-start-is-not-delayed', 'fleet-new-upcoming-bookings',
                  'fleet-new-return-policy-open', 'fleet-new-return-policy-closed',
                  'fleet-new-availability-ceil-over', 'fleet-new-prudent-margin-1.15',
                  'fleet-new-energy-prices-per-resource'}
        return [case for case in cases if case['id'] in wanted]
    for offset in range(6):
        seed = 2026103000 + offset
        rng = random.Random(seed)
        n = 5 + offset % 2
        matrix, coords = _geometry(n, seed)
        rows = [_stop(i, weight=rng.randint(1, 4), packages=rng.randint(1, 3),
                      service=rng.randint(2, 8),
                      sponda=(i + offset) % 4 == 0, ztl=(i + offset) % 5 == 0,
                      lat=coords[i + 1]['lat'], lon=coords[i + 1]['lon']) for i in range(n)]
        if offset % 2:
            rows[0].update(scarico_mattina_da='08:10', scarico_mattina_a='09:00')
            rows[-1].update(scarico_mattina_da='09:20', scarico_mattina_a='11:00')
        schedule = {'start': '08:00', 'end': '17:00',
                    'breaks': [{'start': '09:10', 'end': '09:25'}] if offset % 3 else []}
        resources = [_resource(7 + offset, packages=8, schedule=schedule,
                               ha_sponda=True, accesso_ztl=False),
                     _resource(8 + offset, packages=9, ha_sponda=False, accesso_ztl=True)]
        cases.append(_case(f'fleet-new-random-{seed}', 'seeded-mixed', rows, resources,
                           matrix, seed=seed))
    for n, count, capacity in ((8, 2, 4), (12, 3, 4), (25, 4, 7), (50, 5, 12), (100, 10, 10)):
        seed = 2026103100 + n
        matrix, coords = _geometry(n, seed, spread=4)
        rows = [_stop(i, service=2, lat=coords[i + 1]['lat'], lon=coords[i + 1]['lon'])
                for i in range(n)]
        resources = [_resource(capacity, capacity, available=840) for _ in range(count)]
        witness = [list(range(i, n, count)) for i in range(count)]
        cases.append(_case(f'fleet-new-scale-{n}', 'scaling-known-witness', rows,
            resources, matrix, seed=seed, reference='exact' if n == 8 else 'witness', witness=witness))
    return cases


class _NoDatabase:
    def __getattr__(self, name):
        raise AssertionError(f'Fleet quality adapter unexpectedly accessed database: {name}')


def run_fleet(case, strategy, input_order=None, budget=None):
    """Exercise distribute, canonical scheduling and fleet search without providers.

    Matrix indices are remapped for every input permutation, while returned
    route indices always refer to the original case. The application sees the
    actual traffic-margin transform and per-card driver/energy settings.
    """
    from app import optimizer as opt
    from app.services import fleet_planning as fleet
    from app.services.road_routing import RoadMatrix
    from app.schemas.fleet_planning import FleetInput

    snapshot = deepcopy(case)
    n = len(case['stops'])
    order = list(range(n)) if input_order is None else list(input_order)
    if sorted(order) != list(range(n)):
        raise ValueError('input_order must be a permutation of all original stop indices')
    nodes = [0] + [case['stops'][i]['customer_id'] for i in order]
    local_matrix = RoadMatrix({(i, j): dict(case['matrix'][nodes[i], nodes[j]])
                              for i in range(n + 1) for j in range(n + 1)},
                             source='quality-frozen-matrix')
    payload = dict(nome='Audit flotta corrente', data_giro='2099-06-15', deposit_id=9001,
                   orario_partenza=case['start_time'], rientro_deposito=case['return_depot'],
                   strategy=strategy, consegne=[deepcopy(case['stops'][i]) for i in order],
                   resources=[dict(vehicle_id=i + 1, driver_id=i + 1,
                       driver_schedule=deepcopy(resource.get('driver_schedule') or {}),
                       energy_price_mode='manual',
                       energy_price_primary=resource.get('energy_price_primary', 1.83),
                       energy_price_electric=resource.get('energy_price_electric', .34))
                       for i, resource in enumerate(case['resources'])])
    data = FleetInput.model_validate(payload)
    rows = [stop.model_dump(mode='json') for stop in data.consegne]
    deposit = SimpleNamespace(id=9001, user_id=1, indirizzo='Deposito audit fittizio',
                              lat=45.47, lon=9.18)
    vehicles = [SimpleNamespace(id=i + 1, nome=f'Mezzo audit {i + 1}', targa=f'AUDIT{i + 1}',
        ha_sponda=resource.get('ha_sponda', False), accesso_ztl=resource.get('accesso_ztl', False),
        capacita_kg=resource.get('capacita_kg'), capacita_colli=resource.get('capacita_colli'),
        alimentazione=resource.get('alimentazione', 'gasolio'),
        consumo_primario_100km=resource.get('consumo_primario_100km', 8),
        consumo_l_100km=resource.get('consumo_primario_100km', 8),
        consumo_kwh_100km=resource.get('consumo_kwh_100km', 0))
        for i, resource in enumerate(case['resources'])]
    drivers = [SimpleNamespace(id=i + 1, nome=f'Autista audit {i + 1}', cognome='')
               for i in range(len(vehicles))]
    max_day = fleet.day_minutes_left(case['start_time'])
    limits = [min(resource.get('max_minutes', max_day), max_day)
              for resource in case['resources']]
    calls = {'matrix': 0, 'external': 0, 'traffic_preview': 0}

    def matrix_boundary(*args, **kwargs):
        calls['matrix'] += 1
        return local_matrix

    def no_external(*args, **kwargs):
        calls['external'] += 1
        raise AssertionError('Fleet quality adapter attempted an external request')

    def no_live_traffic(*args, **kwargs):
        calls['traffic_preview'] += 1
        return {'status': 'disabled'}

    with ExitStack() as stack:
        stack.enter_context(patch.object(fleet, 'input_state',
            lambda *args: (deposit, deepcopy(rows), vehicles, drivers)))
        stack.enter_context(patch.object(fleet, 'work_limits', lambda *args: limits))
        stack.enter_context(patch.object(fleet, 'traffic_margin',
            lambda *args: case.get('traffic_margin', 1.0)))
        stack.enter_context(patch.object(fleet, 'preview_traffic', no_live_traffic))
        stack.enter_context(patch.object(opt, 'geocode_deposit',
            lambda *args: {'lat': deposit.lat, 'lon': deposit.lon}))
        stack.enter_context(patch.object(opt, 'build_distance_matrix', matrix_boundary))
        stack.enter_context(patch('requests.sessions.Session.request', no_external))
        stack.enter_context(patch.object(socket.socket, 'connect', no_external))
        stack.enter_context(patch('smtplib.SMTP', no_external))
        if budget is not None:
            stack.enter_context(patch.dict(os.environ, {'FLEET_MAX_CANDIDATES': str(budget)}))
        started, cpu = perf_counter(), process_time()
        production = fleet.distribute(_NoDatabase(), SimpleNamespace(id=1), data)
        elapsed_ms, cpu_ms = (perf_counter() - started) * 1000, (process_time() - cpu) * 1000
    routes = [[] for _ in case['resources']]
    for route in production['routes']:
        routes[route['resource']] = [order[index] for index in route['stop_indexes']]
    used = len(production['routes'])
    durations = [float(route['result']['total_min']) for route in production['routes']]
    return dict(routes=routes, production=production, diagnostics=production['search'],
        production_metrics=dict(served=sum(map(len, routes)), used=used,
            km=sum(float(route['result']['total_km']) for route in production['routes']),
            minutes=sum(durations), makespan=max(durations, default=0),
            sumsq=sum(value * value for value in durations),
            fuel_cost=sum(float(route['fuel_cost']) for route in production['routes'])),
        unassigned=[order[item['index']] for item in production['unassigned']],
        elapsed_ms=elapsed_ms, cpu_ms=cpu_ms, routing_matrix_calls=calls['matrix'],
        external_calls=calls['external'], traffic_preview_calls=calls['traffic_preview'],
        mutation_detected=case != snapshot,
        availability_semantics=case.get('availability_semantics',
            'minutes until a conflicting booking or midnight'),
        traffic_margin=case.get('traffic_margin', 1.0))
