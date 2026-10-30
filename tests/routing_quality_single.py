"""New single-route experiments for the 30 October 2026 quality audit.

Fixtures are synthetic road matrices, generated here independently of historical
benchmarks. Public ``optimize_route`` remains the system under test. Only the
matrix boundary is replaced; database and provider access are forbidden.
"""
from __future__ import annotations

from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from collections.abc import Mapping
import io
import math
import random
import socket
from time import perf_counter, process_time
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch


def _clock(value):
    value = int(value)
    return f"{value // 60:02d}:{value % 60:02d}"


def _stops(n, **updates):
    result = []
    for i in range(n):
        row = dict(customer_id=i + 1, cliente_nome=f"Destinatario Q30-{i+1}",
                   indirizzo=f"Via Caso Sintetico {i+1}, località fittizia",
                   lat=40.82 + (i + 1) * .00031,
                   lon=14.22 + (i + 1) * .00043,
                   peso_kg=1.0, colli=1, tempo_scarico_min=0,
                   ztl=False, sponda=False)
        row.update(deepcopy(updates))
        result.append(row)
    return result


def _resource(**updates):
    row = dict(capacita_kg=10000, capacita_colli=10000, ha_sponda=True,
               accesso_ztl=True, max_minutes=1440, driver_schedule={})
    row.update(deepcopy(updates))
    return row


def _uniform(n, km=7.0, minutes=9.0):
    return {(i, j): dict(km=0.0 if i == j else float(km),
                         min=0.0 if i == j else float(minutes))
            for i in range(n + 1) for j in range(n + 1)}


def _road_matrix(n, seed):
    """Directed road graph, with distance attached to the fastest path.

    Duration and distance are deliberately not proportional. Floyd-Warshall
    freezes a possible road-provider matrix, including asymmetric one-way legs.
    This is fictional infrastructure, not a measurement of Italian roads.
    """
    rng = random.Random(seed)
    matrix = {(i, j): dict(km=0.0 if i == j else rng.randint(8, 145) / 10,
                           min=0.0 if i == j else float(rng.randint(3, 29)))
              for i in range(n + 1) for j in range(n + 1)}
    for middle in range(n + 1):
        for origin in range(n + 1):
            for destination in range(n + 1):
                first, second = matrix[origin, middle], matrix[middle, destination]
                old = matrix[origin, destination]
                proposal = (first['min'] + second['min'], first['km'] + second['km'])
                if proposal < (old['min'], old['km']):
                    matrix[origin, destination] = dict(min=proposal[0], km=proposal[1])
    return matrix


def _case(identifier, family, rows, matrix, *, resource=None, returning=True,
          start='08:00', reference='exact', seed=20261030, **metadata):
    return dict(id=identifier, kind='single', family=family, seed=seed,
                stops=rows, matrix=matrix, resources=[resource or _resource()],
                start_time=start, return_depot=returning, reference=reference,
                **metadata)


def _curated():
    result = []
    matrix = _uniform(3, km=8, minutes=3)
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
        matrix[a, b] = dict(km=2.25, min=19.0)
    result.append(_case('single-q30-shorter-is-slower', 'distance_before_speed',
                        _stops(3), matrix))

    matrix = _uniform(4, km=11, minutes=7)
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 4)):
        matrix[a, b] = dict(km=1.4, min=6.0)
    matrix[4, 0] = dict(km=39, min=10)
    matrix[0, 4] = dict(km=3, min=8)
    matrix[1, 0] = dict(km=2, min=6)
    for returning in (True, False):
        result.append(_case(f'single-q30-terminal-{"closed" if returning else "open"}',
                            'return_leg_changes_sequence', _stops(4), deepcopy(matrix),
                            returning=returning))

    rows, matrix = _stops(5, tempo_scarico_min=6), _road_matrix(5, 301017)
    rows[3].update(scarico_mattina_da='08:00', scarico_mattina_a='08:16')
    result.append(_case('single-q30-urgent-detour', 'feasibility_before_distance', rows, matrix))

    rows = _stops(4, tempo_scarico_min=11)
    rows[0].update(scarico_mattina_da='08:00', scarico_mattina_a='08:14',
                   scarico_pomeriggio_da='09:05', scarico_pomeriggio_a='10:30')
    rows[1].update(scarico_mattina_da='08:00', scarico_mattina_a='08:28')
    rows[2].update(scarico_mattina_da='08:35', scarico_mattina_a='10:30')
    result.append(_case('single-q30-second-window-is-needed', 'double_window',
                        rows, _uniform(4, 3.4, 6)))

    rows, matrix = _stops(3, tempo_scarico_min=7.5), _uniform(3, 2, 4.5)
    rows[1].update(scarico_mattina_da='08:00', scarico_mattina_a='08:12')
    result.append(_case('single-q30-service-finishes-on-boundary',
                        'service_completion_boundary', rows, matrix))

    rows = _stops(4, tempo_scarico_min=8)
    schedule = dict(start='08:00', end='12:30',
                    breaks=[dict(start='08:18', end='08:42')])
    rows[2].update(scarico_mattina_da='09:05', scarico_mattina_a='11:00')
    result.append(_case('single-q30-pause-interrupts-driving', 'driver_pause_travel',
                        rows, _road_matrix(4, 301021),
                        resource=_resource(driver_schedule=schedule)))

    rows = _stops(3, tempo_scarico_min=16)
    rows[0].update(scarico_mattina_da='08:00', scarico_mattina_a='08:28',
                   scarico_pomeriggio_da='09:00', scarico_pomeriggio_a='10:30')
    rows[1].update(scarico_mattina_da='08:00', scarico_mattina_a='08:22')
    schedule = dict(start='08:00', end='12:00',
                    breaks=[dict(start='08:20', end='08:50')])
    result.append(_case('single-q30-pause-forbids-split-unloading',
                        'driver_pause_service', rows, _uniform(3, 2.3, 4),
                        resource=_resource(driver_schedule=schedule)))

    rows = _stops(4, tempo_scarico_min=5, scarico_mattina_da='09:15', scarico_mattina_a='11:00')
    schedule = dict(start='08:00', end='12:00',
                    breaks=[dict(start='08:25', end='08:55')])
    result.append(_case('single-q30-waiting-covers-pause', 'waiting_and_pause',
                        rows, _uniform(4, 4.1, 8),
                        resource=_resource(driver_schedule=schedule)))

    rows, matrix = _stops(3, tempo_scarico_min=2), _uniform(3, km=6, minutes=4)
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
        matrix[a, b] = dict(km=1.5, min=17)
    result.append(_case('single-q30-shift-end-beats-shorter-distance',
                        'driver_shift_end', rows, matrix,
                        resource=_resource(driver_schedule=dict(start='08:00', end='08:35', breaks=[]))))

    rows = _stops(4)
    for row, weight, packages in zip(rows, (8.25, 3.75, 11.5, 13.5), (2, 1, 5, 3)):
        row.update(peso_kg=weight, colli=packages)
    result.append(_case('single-q30-load-exactly-at-both-caps', 'load_boundary',
                        rows, _road_matrix(4, 301029),
                        resource=_resource(capacita_kg=37, capacita_colli=11)))

    rows = _stops(4, tempo_scarico_min=4)
    rows[0]['sponda'] = True
    rows[2]['ztl'] = True
    result.append(_case('single-q30-equipment-remains-warning', 'soft_equipment_requirements',
                        rows, _road_matrix(4, 301033),
                        resource=_resource(ha_sponda=False, accesso_ztl=False)))

    result.append(_case('single-q30-crosses-midnight', 'midnight_clock',
                        _stops(4, tempo_scarico_min=7), _road_matrix(4, 301037), start='23:37'))

    rows = _stops(2, peso_kg=12)
    result.append(_case('single-q30-rejects-capacity-overrun', 'capacity_validation',
                        rows, _uniform(2), resource=_resource(capacita_kg=23.99),
                        reference='validation', expected_error='Capacità mezzo superata'))
    return result


def _seeded(n, seed, windows=False):
    rows, matrix = _stops(n), _road_matrix(n, seed)
    rng = random.Random(seed + 199)
    clock, previous = 480, 0
    witness = list(range(n))
    rng.shuffle(witness)
    for index in witness:
        row = rows[index]
        row.update(peso_kg=rng.randint(1, 16) / 2,
                   colli=rng.randint(1, 4), tempo_scarico_min=rng.randint(2, 9))
        arrival = clock + matrix[previous, index + 1]['min']
        if windows:
            opening = max(480, int(arrival) - rng.randint(0, 8))
            closing = int(arrival + row['tempo_scarico_min']) + rng.randint(12, 31)
            row.update(scarico_mattina_da=_clock(opening), scarico_mattina_a=_clock(closing))
        clock = arrival + row['tempo_scarico_min']
        previous = index + 1
    return _case(f'single-q30-seeded-{n}-{seed}-{"windows" if windows else "plain"}',
                 'new_seeded_windows' if windows else 'new_seeded_directed', rows, matrix,
                 seed=seed, reference='exact' if n <= 7 else 'witness', witness=[witness])


def _line_certificate(n):
    rng = random.Random(20261030 + n)
    positions = [float(i * 1.7) for i in range(1, n + 1)]
    rng.shuffle(positions)
    nodes = [0.0, *positions]
    matrix = {(i, j): dict(km=abs(a - b), min=abs(a - b) * 1.35)
              for i, a in enumerate(nodes) for j, b in enumerate(nodes)}
    order = sorted(range(n), key=positions.__getitem__)
    # Every closed tour must reach the furthest point and come back. A monotonic
    # outward visit followed by the return attains this lower bound exactly.
    return _case(f'single-q30-line-certificate-{n}', 'large_analytical_bound',
                 _stops(n, tempo_scarico_min=.5), matrix,
                 reference='bound', witness=[order], distance_lower_bound=2 * max(positions),
                 bound_proof='All points lie on one ray: reach furthest point and return.',
                 seed=20261030 + n)


def single_cases(quick=False):
    curated = _curated()
    if quick:
        # Keep operational constraints, public validation, and the heuristic path.
        chosen = [0, 1, 2, 3, 4, 6, 7, 9, 10, 13]
        return ([curated[i] for i in chosen] +
                [_seeded(5, 20261031), _seeded(6, 20261037, True), _line_certificate(9)])
    return (curated + [_seeded(n, 20261030 + 101 * n + sample, windows=sample % 2 == 1)
                       for n in (3, 4, 5, 6) for sample in range(5)] +
            [_line_certificate(n) for n in (9, 12, 20, 50, 100)] +
            [_seeded(n, 20261200 + n, True) for n in (9, 16, 24)])


class _FrozenMatrix(Mapping):
    source = 'synthetic-q30-frozen'

    def __init__(self, values):
        self.values = MappingProxyType({key: MappingProxyType(dict(value))
                                        for key, value in values.items()})

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __getitem__(self, key):
        return self.values[key]


class _NoDatabase:
    def __getattr__(self, name):
        raise AssertionError(f'Single audit attempted database operation: {name}')


def run_single(case, input_order=None, budget=None):
    """Exercise the public engine using stable node IDs under input permutations.

    ``max_minutes`` is intentionally not a single-route engine constraint; it is
    enforced by the multi-vehicle planner. Driver shifts remain real here.
    """
    import requests
    from app import optimizer as opt

    count = len(case['stops'])
    order = list(range(count)) if input_order is None else list(input_order)
    if sorted(order) != list(range(count)):
        raise ValueError('Input order must be a permutation of every stop index')
    rows = [deepcopy(case['stops'][index]) for index in order]
    resources = case.get('resources') or [_resource()]
    resource = deepcopy(resources[0])
    deposit = SimpleNamespace(id=301030, user_id=301030,
                              indirizzo='Deposito sintetico audit Q30', lat=40.82, lon=14.22)
    stable_nodes = [0, *[int(row['customer_id']) for row in rows]]
    local_matrix = _FrozenMatrix({(i, j): case['matrix'][a, b]
                                  for i, a in enumerate(stable_nodes)
                                  for j, b in enumerate(stable_nodes)})
    calls = dict(provider=0, matrix=0)
    diagnostics = {}
    raw = {}
    real_search = opt._best_internal_sequence

    def frozen_matrix(*args, **kwargs):
        calls['matrix'] += 1
        return local_matrix

    def observe_search(*args, **kwargs):
        kwargs['diagnostics'] = diagnostics
        result = real_search(*args, **kwargs)
        for field in ('_objective', 'violations', 'total_lateness_min', 'score'):
            raw[field] = deepcopy(result.get(field))
        return result

    def forbidden(*args, **kwargs):
        calls['provider'] += 1
        raise AssertionError('Single audit attempted an external provider/network call')

    result = None
    error = None
    wall, cpu = perf_counter(), process_time()
    with ExitStack() as stack, redirect_stdout(io.StringIO()):
        stack.enter_context(patch.object(opt, 'build_distance_matrix', frozen_matrix))
        stack.enter_context(patch.object(opt, '_best_internal_sequence', observe_search))
        stack.enter_context(patch.object(requests.sessions.Session, 'request', forbidden))
        stack.enter_context(patch.object(socket, 'create_connection', forbidden))
        stack.enter_context(patch.object(socket.socket, 'connect', forbidden))
        if budget is not None:
            stack.enter_context(patch.dict('os.environ', {'OPTIMIZER_MAX_CANDIDATES': str(budget)}))
        try:
            result = opt.optimize_route(_NoDatabase(), deposit, rows, resource,
                return_depot=case.get('return_depot', True),
                start_time=case.get('start_time', '08:00'), route_date='2099-01-14')
        except ValueError as exc:
            error = str(exc)
    by_id = {int(row['customer_id']): index for index, row in enumerate(case['stops'])}
    route = [by_id[int(row['customer_id'])] for row in result['ordered']] if result else []
    return dict(routes=[route], result=result, diagnostics=diagnostics,
                raw_metrics=raw, runtime_ms=(perf_counter() - wall) * 1000,
                cpu_ms=(process_time() - cpu) * 1000,
                provider_calls=calls['provider'], matrix_calls=calls['matrix'],
                rejected=error is not None, error=error)
