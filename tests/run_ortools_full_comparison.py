"""Confronto completo GiroFacile / OR-Tools sui vincoli reali del multi-mezzo.

Esperimento offline, mai importato dall'applicazione. Richiede OR-Tools
(tests/requirements-ortools-benchmark.txt) in un ambiente o cartella separati.

Casi: i 43 problemi già usati per il motore multi-mezzo (50 consegne, da 2 a 5
mezzi, pause fisse, partenze diverse, una o due fasce, sponda e ZTL come
preferenze, capacità in kg e colli) più 4 problemi da 100 consegne con 8 e 10
mezzi, generati qui con lo stesso metodo: un piano testimone indipendente prova
che tutte le consegne sono servibili.

Per ogni caso: GiroFacile con il budget standard; OR-Tools con lo stesso tempo
impiegato da GiroFacile (minimo 1 s) e con 30 s. Tutti i piani sono giudicati
dallo stesso verificatore indipendente (routing_quality_oracle), con l'obiettivo
della strategia «Riduci chilometri e tempi»: più consegne, meno avvisi di
sponda/ZTL, meno km, meno minuti, meno mezzi.
"""
import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['ALLOW_SQLITE_LEGACY'] = 'true'
os.environ['APP_ENV'] = 'test'
os.environ['BILLING_MODE'] = 'disabled'

from fleet_constraint_holdout import constraint_holdout_cases
from fleet_upgrade_cases import (_add_windows_and_available_turns, _hhmm, _nearest_order,
                                 _validate_witness, upgrade_cases)
from routing_quality_fleet import _case, _geometry, _resource, _stop, run_fleet
from routing_quality_oracle import _minute, _truth, _windows, objective, plan_metrics

SCALE = 60  # secondi: tempi interi per OR-Tools, sempre arrotondati per eccesso


def large_case(n, count, family, seed):
    """Come fleet_upgrade_cases._base, con n consegne: testimone indipendente prima della ricerca."""
    rng = random.Random(seed)
    matrix, coords = _geometry(n, seed, spread=7.5)
    indices = list(range(n))
    rng.shuffle(indices)
    orders = [_nearest_order(indices[v::count], matrix) for v in range(count)]
    rows = [_stop(i, weight=rng.choice((5, 10, 15, 20, 25)), packages=rng.choice((1, 1, 2, 3)),
                  service=rng.choice((2, 3, 4, 5, 6)), lat=coords[i + 1]['lat'], lon=coords[i + 1]['lon'])
            for i in range(n)]
    resources = []
    for v, order in enumerate(orders):
        lift = family != 'combined_tight' or (v + seed) % 2 == 0
        access = v % 3 != 1
        weight = sum(rows[i]['peso_kg'] for i in order)
        parcels = sum(rows[i]['colli'] for i in order)
        quantum = 10 if family == 'combined_tight' else 25
        first, second = 9 * 60 + 15 + v * 9, 11 * 60 + 55 + v * 7
        schedule = {'start': '07:30' if v % 2 else '08:00', 'end': '19:00', 'breaks': [
            {'start': _hhmm(first), 'end': _hhmm(first + 15 + v % 2 * 5)},
            {'start': _hhmm(second), 'end': _hhmm(second + 25)}]}
        resources.append(_resource(math.ceil(weight / quantum) * quantum,
                                   parcels + (0 if family == 'combined_tight' else 1),
                                   available=660, schedule=schedule, ha_sponda=lift, accesso_ztl=access))
        for position, index in enumerate(order):
            rows[index]['sponda'] = bool(family == 'combined_tight' and lift and position % 2 == 0)
            rows[index]['ztl'] = bool(access and (index + seed) % 7 == 0)
    case = _case(f'large-{n}-{count}-{family}-{seed}', family, rows, resources, matrix,
                 reference='witness', seed=seed, witness=orders, split='large', hard_tail_lift=False,
                 expected_served=n, expected_unassigned=[], expected_upper_bound=n, requested_vehicles=count,
                 witness_origin='independent constructive membership and calendar; no production answer')
    _add_windows_and_available_turns(case, family, rng)
    _validate_witness(case)
    return case


def all_cases():
    large = [large_case(100, count, family, 2061100000 + count * 97 + i * 1009)
             for count in (8, 10) for i, family in enumerate(('windows_shifts', 'combined_tight'))]
    return [*upgrade_cases(False), *upgrade_cases(True), *constraint_holdout_cases(), *large]


def solve_ortools(case, seconds, initial=None, weights='practical'):
    """Modello OR-Tools con la semantica del verificatore; il verificatore resta il giudice."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    stops, resources = case['stops'], case['resources']
    n, count = len(stops), len(resources)
    started = _minute(case['start_time'])
    clock = perf_counter()
    manager = pywrapcp.RoutingIndexManager(n + 1, count, 0)
    routing = pywrapcp.RoutingModel(manager)
    node_of = [int(row.get('customer_id') or i + 1) for i, row in enumerate(stops)]  # nodo della matrice
    service = [0] + [math.ceil(float(row.get('tempo_scarico_min') or 0) * SCALE) for row in stops]

    def leg(a, b):
        return case['matrix'][0 if a == 0 else node_of[a - 1], 0 if b == 0 else node_of[b - 1]]

    horizon = 24 * 60 * SCALE
    ends = []
    for r in resources:
        schedule = r.get('driver_schedule') or {}
        end = _minute(schedule['end']) if schedule.get('end') else 24 * 60
        if r.get('max_minutes') is not None:
            end = min(end, started + int(r['max_minutes']))
        ends.append(end * SCALE)
    if weights == 'lexicographic':
        # Ordine rigido: consegna servita > avviso sponda/ZTL > 0,1 km > secondo > mezzo usato.
        # Pesi enormi: la ricerca locale fatica a reinserire le consegne escluse.
        time_weight = count + 1
        distance_weight = count * horizon * time_weight + count + 1
        max_leg = max(round(float(x['km']) * 10) for x in case['matrix'].values())
        mismatch_weight = (n + count) * max_leg * distance_weight + count * horizon * time_weight + count + 1
        drop_penalty = 2 * n * mismatch_weight + mismatch_weight
    else:
        # Pesi pratici in decimi di km: esclusa = 1.000 km, avviso = 20 km; i minuti spezzano i pareggi.
        distance_weight, time_weight = 1, 0
        mismatch_weight, drop_penalty = 200, 10000

    def mismatches(v, node):
        if node == 0:
            return 0
        row, r = stops[node - 1], resources[v]
        return (int(_truth(row.get('sponda')) and not _truth(r.get('ha_sponda')))
                + int(_truth(row.get('ztl')) and not _truth(r.get('accesso_ztl'))))

    for v in range(count):
        def cost(a, b, v=v):
            i, j = manager.IndexToNode(a), manager.IndexToNode(b)
            return round(float(leg(i, j)['km']) * 10) * distance_weight + mismatches(v, j) * mismatch_weight
        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost), v)
    routing.SetFixedCostOfAllVehicles(1 if weights == 'lexicographic' else 0)

    def transit(a, b):
        i, j = manager.IndexToNode(a), manager.IndexToNode(b)
        return service[i] + math.ceil(float(leg(i, j)['min']) * SCALE)
    routing.AddDimension(routing.RegisterTransitCallback(transit), horizon, horizon, False, 'Time')
    time = routing.GetDimensionOrDie('Time')
    if time_weight:
        time.SetSpanCostCoefficientForAllVehicles(time_weight)
    visit = [service[manager.IndexToNode(index)] for index in range(routing.Size())]
    for v, r in enumerate(resources):
        time.CumulVar(routing.Start(v)).SetRange(started * SCALE, started * SCALE)
        time.CumulVar(routing.End(v)).SetMax(ends[v])
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.End(v)))
        schedule = r.get('driver_schedule') or {}
        breaks = [routing.solver().FixedDurationIntervalVar(
                      _minute(b['start']) * SCALE, _minute(b['start']) * SCALE,
                      (_minute(b['end']) - _minute(b['start'])) * SCALE, False, f'pausa-{v}-{k}')
                  for k, b in enumerate(schedule.get('breaks', []))]
        if breaks:
            time.SetBreakIntervalsOfVehicle(breaks, v, visit)
    late_starters = [v for v, r in enumerate(resources)
                     if (r.get('driver_schedule') or {}).get('start') and _minute(r['driver_schedule']['start']) > started]
    for field, capacity in (('peso_kg', 'capacita_kg'), ('colli', 'capacita_colli')):
        def demand(a, field=field):
            node = manager.IndexToNode(a)
            return math.ceil(float(stops[node - 1].get(field) or 0)) if node else 0
        caps = [math.floor(float(r[capacity])) if r.get(capacity) is not None else 10 ** 9 for r in resources]
        routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(demand), 0, caps, True, field)
    for i, row in enumerate(stops):
        index = manager.NodeToIndex(i + 1)
        routing.AddDisjunction([index], drop_penalty)
        for v in late_starters:
            routing.VehicleVar(index).RemoveValue(v)
        windows = _windows(row)
        if not windows:
            time.CumulVar(index).SetRange(started * SCALE, horizon)
            continue
        # Inizio scarico ammesso: unione di [apertura, chiusura - scarico].
        allowed = [(left * SCALE, right * SCALE - service[i + 1]) for left, right in windows
                   if right * SCALE - service[i + 1] >= max(left, started) * SCALE]
        if not allowed:
            routing.ActiveVar(index).SetValue(0)
            continue
        low, high = max(started * SCALE, allowed[0][0]), allowed[-1][1]
        time.CumulVar(index).SetRange(low, high)
        for (_, gap_start), (gap_end, _) in zip(allowed, allowed[1:]):
            if gap_end - 1 >= gap_start + 1:
                time.CumulVar(index).RemoveInterval(gap_start + 1, gap_end - 1)
    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameters.time_limit.FromMilliseconds(round(seconds * 1000))
    if initial is not None:
        # Parte da un piano già valido (per esempio quello di GiroFacile) e cerca di migliorarlo.
        routing.CloseModelWithParameters(parameters)
        start = routing.ReadAssignmentFromRoutes([[manager.NodeToIndex(i + 1) for i in order] for order in initial], True)
        solution = routing.SolveFromAssignmentWithParameters(start, parameters) if start else None
    else:
        solution = routing.SolveWithParameters(parameters)
    elapsed = (perf_counter() - clock) * 1000
    if solution is None:
        return {'orders': None, 'elapsed_ms': elapsed, 'status': int(routing.status())}
    orders = []
    for v in range(count):
        index, order = routing.Start(v), []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node:
                order.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        orders.append(order)
    return {'orders': orders, 'elapsed_ms': elapsed, 'status': int(routing.status())}


def summary(metrics):
    return {key: (round(metrics[key], 2) if isinstance(metrics[key], float) else metrics[key])
            for key in ('feasible', 'served', 'mismatches', 'km', 'minutes', 'used', 'lateness', 'violations')} | {
            'unassigned': list(metrics['unassigned'])}


def judged(case, orders):
    if orders is None:
        return None
    metrics = plan_metrics(case, orders)
    return {'metrics': summary(metrics), 'objective': list(objective(metrics, 'efficient')) if metrics['feasible'] else None,
            'orders': [list(order) for order in orders]}


def winner(a, b):
    """Confronto con l'obiettivo «efficiente»; un piano non valido perde sempre."""
    ka = tuple(a['objective']) if a and a.get('objective') else None
    kb = tuple(b['objective']) if b and b.get('objective') else None
    if ka is None and kb is None:
        return 'nessuno'
    if kb is None or (ka is not None and ka < kb):
        return 'girofacile'
    if ka is None or kb < ka:
        return 'ortools'
    return 'pari'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--long-seconds', type=float, default=30)
    parser.add_argument('--seeded-seconds', type=float, default=10)
    parser.add_argument('--output', default='docs/ortools-full-comparison-2026-11-02.json')
    parser.add_argument('--only', default='', help='sottostringa degli id da eseguire')
    args = parser.parse_args()
    import ortools
    output = Path(args.output)
    previous = {r['id']: r for r in json.loads(output.read_text(encoding='utf-8'))['records']} if output.exists() else {}
    records = []
    for case in all_cases():
        if args.only and args.only not in case['id']:
            continue
        if case['id'] in previous:
            records.append(previous[case['id']])
            continue
        before = deepcopy(case)
        current = run_fleet(case, 'efficient')
        assert current['external_calls'] == 0 and not current['mutation_detected']
        giro = judged(case, current['routes']) | {'elapsed_ms': round(current['elapsed_ms'])}
        same_time = max(1.0, current['elapsed_ms'] / 1000)
        runs = {'ortools_same_time': solve_ortools(case, same_time),
                'ortools_long': solve_ortools(case, args.long_seconds),
                # Modalità combinata: OR-Tools parte dal piano di GiroFacile e prova a migliorarlo.
                'ortools_from_girofacile': solve_ortools(case, args.seeded_seconds, initial=current['routes'])}
        assert case == before
        record = {'id': case['id'], 'family': case['family'], 'stops': len(case['stops']),
                  'vehicles': len(case['resources']), 'witness_served': case['expected_served'],
                  'girofacile': giro}
        for name, result in runs.items():
            # Nessun piano entro il tempo: registrato, e perde il confronto.
            record[name] = (judged(case, result['orders']) or {'no_solution': True, 'status': result['status']}) | {
                'elapsed_ms': round(result['elapsed_ms'])}
            record['winner_' + name] = winner(giro, record[name])
        records.append(record)
        short = lambda run: {k: (run.get('metrics') or {}).get(k) for k in ('served', 'mismatches', 'km')}
        print(json.dumps({'id': record['id'], 'giro': short(giro), 'giro_s': round(current['elapsed_ms'] / 1000, 1),
                          **{name: short(record[name]) for name in runs}}), flush=True)
        report = {'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'python': platform.python_version(), 'ortools_version': ortools.__version__,
                  'strategy': 'efficient', 'long_seconds': args.long_seconds, 'records': records}
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
        temporary.replace(output)


if __name__ == '__main__':
    main()
