"""Research only: fictional deliveries, saved real-road matrices, independent solvers.

Use the isolated environment from requirements-routing-benchmark.txt.
No production optimizer or production dependencies are modified.
"""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch
from urllib.parse import urlparse

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('ALLOW_SQLITE_LEGACY', 'true')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import optimizer as opt

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/road_margin_matrices.json'
OUTPUT = ROOT / 'docs/optimizer-road-margin-results.json'
SIZES = (8, 15, 20, 30, 50)
AREAS = {
    'urban': [(14.25, 40.85), (14.225, 40.838), (14.278, 40.863)],
    'provincial': [(14.208, 40.973), (14.33, 41.07), (14.373, 40.944), (14.534, 40.925)],
    'mixed': [(14.25, 40.85), (14.373, 40.944), (14.497, 40.75), (14.77, 40.68)],
}


def collect(base_url):
    """Only this explicit acquisition step may contact a server; local OSRM only."""
    import requests
    if urlparse(base_url).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Use a local OSRM instance; no public demo server')
    pools = {}
    for number, (kind, centers) in enumerate(AREAS.items()):
        rng = random.Random(20261001 + number)
        points, requested, offsets = [], [], []
        attempts = 0
        while len(points) < 51:
            attempts += 1
            if attempts > 2000:
                raise RuntimeError('Unable to collect enough nearby routable points')
            center = centers[len(points) % len(centers)]
            point = [round(center[0] + rng.uniform(-.012, .012), 6),
                     round(center[1] + rng.uniform(-.009, .009), 6)]
            response = requests.get(f'{base_url}/nearest/v1/driving/{point[0]},{point[1]}',
                                    params={'number': 1}, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get('code') != 'Ok':
                raise ValueError(data.get('message', data.get('code')))
            waypoint = data['waypoints'][0]
            snapped = waypoint['location']
            if waypoint['distance'] > 200 or any(math.dist(snapped, p) < .0004 for p in points):
                continue
            points.append(snapped)
            requested.append(point)
            offsets.append(waypoint['distance'])
        coordinates = ';'.join(','.join(map(str, p)) for p in points)
        response = requests.get(f'{base_url}/table/v1/driving/{coordinates}',
                                params={'annotations': 'distance,duration'}, timeout=120)
        response.raise_for_status()
        data = response.json()
        if data.get('code') != 'Ok' or data.get('fallback_speed_cells'):
            raise ValueError('Missing road matrix or straight-line fallback')
        if any(v is None for key in ('distances', 'durations') for row in data[key] for v in row):
            raise ValueError('Unreachable point: do not replace with straight-line distances')
        # Identical integer precision for production, reference and certificates.
        pools[kind] = dict(coordinates=points, requested_coordinates=requested,
            snap_distance_m=offsets,
            distance_m=[[int(round(v)) for v in line] for line in data['distances']],
            duration_s=[[int(math.ceil(v)) for v in line] for line in data['durations']])
        print('collected', kind, len(points), flush=True)
    snapshot = dict(schema_version=1, source='fictional_deliveries_on_real_osm_roads',
        acquired_at_utc=datetime.now(timezone.utc).isoformat(),
        dataset='Local sud-latest.osrm; OSM source timestamp not independently verified',
        attribution='© OpenStreetMap contributors, ODbL https://www.openstreetmap.org/copyright',
        profile='OSRM driving; distances of fastest routes, not shortest-distance paths',
        precision='distance rounded to metres, duration rounded up to seconds, shared by all engines',
        pools=pools)
    FIXTURE.write_text(json.dumps(snapshot, indent=2) + '\n', encoding='utf-8')


def scenario(pool, n, windows, back):
    distances = [row[:n+1] for row in pool['distance_m'][:n+1]]
    times = [row[:n+1] for row in pool['duration_s'][:n+1]]
    coordinates = pool['coordinates'][:n+1]
    # Simulated zone sweep, not a claimed model of expert human behaviour.
    depot = coordinates[0]
    order = sorted(range(1, n+1), key=lambda i: (
        int((math.atan2(coordinates[i][1]-depot[1],
                        (coordinates[i][0]-depot[0])*.76) + math.pi) / (math.pi/3)),
        math.dist(coordinates[i], depot), i))
    service = [0] + [(3 + (i*7 % 6))*60 for i in range(1, n+1)]
    bounds = [None] * (n+1)
    if windows:
        clock, previous = 0, 0
        for i in order:
            arrival = clock + times[previous][i]
            # Appointment band: 60–120 minutes plus unloading service.
            half = (30 + i % 3 * 15)*60
            opening = max(0, (arrival-half)//60*60)
            closing = math.ceil((arrival+service[i]+half)/60)*60
            if closing + 8*3600 >= 24*3600:
                raise ValueError('Generated appointment extends beyond the same day')
            bounds[i] = [opening, closing]
            clock, previous = arrival + service[i], i
    return dict(n=n, distance_m=distances, duration_s=times, service_s=service,
                windows_s=bounds, operator_order=order, return_depot=back)


def replay(data, order):
    """Independent integer replay: mandatory stops, service completion in window."""
    if sorted(order) != list(range(1, data['n']+1)):
        raise ValueError('Not a complete delivery permutation')
    clock = distance = wait = late = violations = 0
    previous = 0
    for i in order:
        distance += data['distance_m'][previous][i]
        clock += data['duration_s'][previous][i]
        window = data['windows_s'][i]
        if window:
            delay = max(0, window[0]-clock)
            clock += delay
            wait += delay
        clock += data['service_s'][i]
        if window and clock > window[1]:
            violations += 1
            late += clock-window[1]
        previous = i
    if data['return_depot']:
        distance += data['distance_m'][previous][0]
        clock += data['duration_s'][previous][0]
    return dict(distance_m=distance, duration_s=clock, wait_s=wait,
                violations=violations, lateness_s=late, order=order)


def production_input(data):
    rows = {}
    for i in range(1, data['n']+1):
        row = dict(customer_id=i, cliente_nome=f'Fictional {i}', indirizzo=f'Simulated stop {i}',
                   _matrix_index=i, tempo_scarico_min=data['service_s'][i]/60)
        if data['windows_s'][i]:
            for suffix, value in zip(('da', 'a'), data['windows_s'][i]):
                minute = 480 + value//60
                row[f'scarico_mattina_{suffix}'] = f'{minute//60:02}:{minute%60:02}'
        rows[i] = row
    matrix = {(i,j): {'km': data['distance_m'][i][j]/1000, 'min': data['duration_s'][i][j]/60}
              for i in range(data['n']+1) for j in range(data['n']+1) if i != j}
    return rows, matrix


def forbidden(*args, **kwargs):
    raise AssertionError('Benchmark execution must use saved matrices, no provider calls')


def routing_reference(data, seed, seconds):
    """Distance objective, mandatory nodes, exact directed time windows; local GLS."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n = data['n']
    end_node = 0 if data['return_depot'] else n+1
    manager = pywrapcp.RoutingIndexManager(n+1 if end_node == 0 else n+2, 1, [0], [end_node])
    routing = pywrapcp.RoutingModel(manager)
    def arc(a, b, field):
        a, b = manager.IndexToNode(a), manager.IndexToNode(b)
        return 0 if a > n or b > n else data[field][a][b]
    distance_cb = routing.RegisterTransitCallback(lambda a,b: arc(a,b,'distance_m'))
    routing.SetArcCostEvaluatorOfAllVehicles(distance_cb)
    def transit(a,b):
        node = manager.IndexToNode(a)
        return arc(a,b,'duration_s') + (data['service_s'][node] if node <= n else 0)
    time_cb = routing.RegisterTransitCallback(transit)
    horizon = sum(data['service_s']) + (n+1)*max(map(max,data['duration_s'])) + max(
        (w[1] for w in data['windows_s'] if w), default=0) + 1
    routing.AddDimension(time_cb, horizon, horizon, True, 'Time')
    dimension = routing.GetDimensionOrDie('Time')
    for i in range(1,n+1):
        if data['windows_s'][i]:
            a,b = data['windows_s'][i]
            dimension.CumulVar(manager.NodeToIndex(i)).SetRange(a,b-data['service_s'][i])
    routing.AddVariableMinimizedByFinalizer(dimension.CumulVar(routing.End(0)))
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(seconds*1000))
    params.log_search = False
    # Collect incumbents and select lexicographically with the common replay.
    candidates = [replay(data, seed)]
    def capture():
        index, order = routing.Start(0), []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node: order.append(node)
            index = routing.NextVar(index).Value()
        candidate = replay(data, order)
        if not candidate['violations']:
            candidates.append(candidate)
    routing.AddAtSolutionCallback(capture)
    assignment = routing.ReadAssignmentFromRoutes([seed], True)
    if assignment is None:
        raise ValueError('Feasible seed rejected by independent routing model')
    routing.SolveFromAssignmentWithParameters(assignment, params)
    return min(candidates, key=lambda r:(r['violations'],r['distance_m'],r['duration_s'],r['wait_s']))


def certificate(data, seed, seconds):
    """Independent CP-SAT circuit model: proves primary distance only if OPTIMAL."""
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    n = data['n']
    arcs = {(i,j):model.new_bool_var(f'x{i}_{j}') for i in range(n+1) for j in range(n+1) if i != j}
    model.add_circuit([(i,j,x) for (i,j),x in arcs.items()])
    horizon = sum(data['service_s'])+(n+1)*max(map(max,data['duration_s']))+max(
        (w[1] for w in data['windows_s'] if w),default=0)+1
    starts = {i:model.new_int_var(0,horizon,f't{i}') for i in range(n+1)}
    model.add(starts[0] == 0)
    for (i,j),x in arcs.items():
        if j:
            model.add(starts[j] >= starts[i]+data['service_s'][i]+data['duration_s'][i][j]).only_enforce_if(x)
    for i,w in enumerate(data['windows_s']):
        if w:
            model.add(starts[i] >= w[0])
            model.add(starts[i]+data['service_s'][i] <= w[1])
    objective = sum(x*(data['distance_m'][i][j] if j or data['return_depot'] else 0)
                    for (i,j),x in arcs.items())
    model.minimize(objective)
    route = [0,*seed,0]
    used = set(zip(route,route[1:]))
    for edge,x in arcs.items(): model.add_hint(x,int(edge in used))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 20261001
    status = solver.solve(model)
    result = dict(status=solver.status_name(status), distance_optimal=status == cp_model.OPTIMAL,
                  lower_bound_m=solver.best_objective_bound, wall_s=solver.wall_time, order=None)
    if status in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        order, current = [], 0
        for _ in range(n):
            current = next(j for (i,j),x in arcs.items() if i == current and solver.value(x))
            order.append(current)
        result.update(order=order, distance_m=replay(data,order)['distance_m'])
    return result


def run_one(pool, kind, n, windows, back, search_seconds, proof_seconds):
    data = scenario(pool,n,windows,back)
    rows,matrix = production_input(data)
    diagnostics = {}
    cpu,wall = process_time(),perf_counter()
    with patch.object(opt.requests.sessions.Session,'request',forbidden), redirect_stdout(io.StringIO()):
        result = opt._best_internal_sequence([deepcopy(rows[i]) for i in data['operator_order']],
                    matrix,[],return_depot=back,diagnostics=diagnostics)
    production_timing = dict(cpu_s=process_time()-cpu,wall_s=perf_counter()-wall)
    actual = replay(data,[d['customer_id'] for d in result['ordered']])
    manual = replay(data,data['operator_order'])
    assert manual['violations'] == actual['violations'] == 0
    assert actual['distance_m'] <= manual['distance_m']
    assert abs(actual['distance_m']/1000-result['total_km']) <= .00501
    assert abs(actual['duration_s']/60-result['total_min']) <= .05001
    cpu,wall = process_time(),perf_counter()
    independent = routing_reference(data,manual['order'],search_seconds)
    warm = routing_reference(data,actual['order'],search_seconds)
    candidates = [actual,independent,warm]
    proof = certificate(data,min(candidates,key=lambda r:r['distance_m'])['order'],proof_seconds) if n <= 15 else None
    if proof and proof['order']:
        candidates.append(replay(data,proof['order']))
    best = min(candidates,key=lambda r:(r['violations'],r['distance_m'],r['duration_s'],r['wait_s']))
    assert best['violations'] == 0
    # Every reported reference winner is rechecked by the production evaluator too.
    canonical = opt._evaluate_fixed_sequence([rows[i] for i in best['order']],matrix,[],return_depot=back)
    assert canonical['violations'] == 0
    assert abs(best['distance_m']/1000-canonical['total_km']) <= .00501
    gain = actual['distance_m']-best['distance_m']
    exact = bool(proof and proof['distance_optimal'])
    if exact: assert proof['distance_m'] == best['distance_m']
    return dict(id=f'{kind}-{n}-{"windows" if windows else "free"}-{"closed" if back else "open"}',
        family=kind,n=n,windows=windows,return_depot=back,operator=manual,girofacile=actual,
        reference_independent=independent,reference_warm=warm,best_known=best,
        certificate=proof,margin_is_exact=exact,found_margin_km=gain/1000,
        found_margin_pct=100*gain/actual['distance_m'],production_timing=production_timing,
        reference_timing=dict(cpu_s=process_time()-cpu,wall_s=perf_counter()-wall),diagnostics=diagnostics)


def run(sizes, search_seconds, proof_seconds, output):
    import ortools
    if os.getenv('OPTIMIZER_MAX_CANDIDATES') is not None:
        raise ValueError('Unset OPTIMIZER_MAX_CANDIDATES: benchmark must test production defaults')
    snapshot = json.loads(FIXTURE.read_text(encoding='utf-8'))
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report = dict(schema_version=1,source=snapshot['source'],matrix_sha256=hashlib.sha256(FIXTURE.read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
        production_commit=revision,
        ortools_version=ortools.__version__,routing_seconds_per_start=search_seconds,
        cp_sat_seconds=proof_seconds,records=[])
    for kind,pool in snapshot['pools'].items():
        for n in sizes:
            for windows in (False,True):
                for back in (False,True):
                    record = run_one(pool,kind,n,windows,back,search_seconds,proof_seconds)
                    report['records'].append(record)
                    # Checkpoint every completed case; all results retained, no cherry-picking.
                    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
                    print(record['id'],record['girofacile']['distance_m'],record['best_known']['distance_m'],
                          record['found_margin_pct'], 'exact',record['margin_is_exact'],flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--base-url',default='http://localhost:5000')
    parser.add_argument('--sizes',nargs='+',type=int,default=SIZES)
    parser.add_argument('--search-seconds',type=float,default=3)
    parser.add_argument('--proof-seconds',type=float,default=5)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args = parser.parse_args()
    if args.collect: collect(args.base_url)
    else: run(args.sizes,args.search_seconds,args.proof_seconds,args.output)
