"""Global, sparse mixed-integer feasibility recovery on the existing road matrix.

The model assigns deliveries and vehicle arcs jointly. Fixed driver breaks are
removed from each resource's working clock, so travel remains additive while
service-start domains prevent unloading across a break. The canonical calendar
is the final authority for every accepted plan. No road/provider call is made.
"""
from __future__ import annotations

import math
from time import perf_counter
import warnings

from .fleet_working_clock import TIME_SCALE, _compatible, _plan_key, service_domains


class _Model:
    def __init__(self):
        self.cost, self.lower, self.upper, self.integer = [], [], [], []
        self.ri, self.ci, self.values, self.lo, self.hi = [], [], [], [], []

    def variable(self, low=0, high=1, *, integer=False, cost=0):
        index = len(self.cost)
        self.cost.append(float(cost))
        self.lower.append(float(low))
        self.upper.append(float(high))
        self.integer.append(int(integer))
        return index

    def constraint(self, terms, low=-math.inf, high=math.inf):
        row = len(self.lo)
        self.lo.append(float(low))
        self.hi.append(float(high))
        for variable, coefficient in terms:
            if coefficient:
                self.ri.append(row)
                self.ci.append(variable)
                self.values.append(float(coefficient))

    def solve(self, seconds, hints=None):
        if hints:
            from .fleet_highs_start import solve_with_start
            ordered = sorted(hints)
            return solve_with_start(self, seconds, hint_indices=ordered,
                                    hint_values=[hints[index] for index in ordered])
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array

        if not hasattr(self, '_compiled'):
            matrix = coo_array((np.asarray(self.values),
                (np.asarray(self.ri, dtype=np.int32), np.asarray(self.ci, dtype=np.int32))),
                shape=(len(self.lo), len(self.cost))).tocsc()
            # HiGHS' C interface uses int32 sparse indices on supported wheels.
            matrix.indices = matrix.indices.astype(np.int32)
            matrix.indptr = matrix.indptr.astype(np.int32)
            self._compiled = matrix
        matrix = self._compiled
        lower, upper = np.asarray(self.lower), np.asarray(self.upper)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Unrecognized options detected')
            return milp(np.asarray(self.cost), integrality=np.asarray(self.integer),
                bounds=Bounds(lower, upper),
                constraints=LinearConstraint(matrix, np.asarray(self.lo), np.asarray(self.hi)),
                options={'time_limit': float(seconds), 'presolve': True,
                         'mip_rel_gap': 1.0, 'threads': 1, 'random_seed': 0})


def _pair_exchange_repair(rows, vehicles, matrix, points, start_time, return_depot,
                          limits, routes, scores, possible, evaluate, strategy,
                          deadline):
    """Exactly enumerate a coordinated exchange plus one missing insertion.

    Other relative orders remain fixed, but every insertion position is tested.
    Physical load/equipment pruning comes before prepared calendar evaluation;
    each accepted whole plan is verified again with the canonical evaluator.
    This is a bounded neighbourhood, not a global infeasibility certificate.
    """
    from .fleet_route_evaluator import FixedRouteEvaluator
    from .fleet_search import _better, stable_stop_key

    started = perf_counter()
    info = dict(method='prepared-pair-exchange', physical_pairs=0,
                prepared_evaluations=0, canonical_candidates=0,
                invalid_candidates=0, improvements=0, budget_exhausted=False)
    prepared_rows = [row if '_matrix_index' in row else {**row, '_matrix_index': i+1}
                     for i, row in enumerate(rows)]
    identities = {i: stable_stop_key(rows[i]) for i in possible}
    compatible = {(v, i): _compatible(rows[i], vehicle)
                  for v, vehicle in enumerate(vehicles) for i in possible}
    values = {i: (float(row.get('peso_kg') or 0), float(row.get('colli') or 0))
              for i, row in enumerate(rows)}
    capacities = [tuple(math.inf if vehicle.get(field) is None else float(vehicle[field])
                        for field in ('capacita_kg', 'capacita_colli')) for vehicle in vehicles]

    def expired():
        if perf_counter() >= deadline:
            info['budget_exhausted'] = True
            return True
        return False

    def fit(resource, load):
        return all(value <= capacity for value, capacity in zip(load, capacities[resource]))

    def prepare(members, resource):
        return FixedRouteEvaluator(prepared_rows, members, matrix, points,
            vehicles[resource], return_depot, start_time, limits[resource])

    def replay(prepared, order):
        info['prepared_evaluations'] += 1
        return prepared(order)

    def step():
        assigned = {i for order in routes for i in order}
        missing = sorted(set(possible)-assigned, key=identities.__getitem__)
        loads = [tuple(sum(values[i][k] for i in order) for k in range(2))
                 for order in routes]
        for pending in missing:
            for source, original_left in enumerate(routes):
                for target, original_right in enumerate(routes):
                    if source == target or not compatible.get((target, pending)):
                        continue
                    for a in original_left:
                        if not compatible.get((target, a)):
                            continue
                        for b in original_right:
                            if expired():
                                return None
                            if not compatible.get((source, b)):
                                continue
                            left_load = tuple(loads[source][k]-values[a][k]+values[b][k]
                                              for k in range(2))
                            right_load = tuple(loads[target][k]-values[b][k]+values[a][k]+values[pending][k]
                                               for k in range(2))
                            if not fit(source, left_load) or not fit(target, right_load):
                                continue
                            info['physical_pairs'] += 1
                            left_rest = tuple(i for i in original_left if i != a)
                            right_rest = tuple(i for i in original_right if i != b)
                            left_evaluator = prepare(left_rest+(b,), source)
                            best_left = None
                            for position in range(len(left_rest)+1):
                                order = left_rest[:position]+(b,)+left_rest[position:]
                                score = replay(left_evaluator, order)
                                if score is not None:
                                    # Fastest feasible source leaves the most slack.
                                    raw = score['_objective']
                                    rank = (raw[1], raw[0])
                                    if best_left is None or _better(rank, best_left[0]):
                                        best_left = rank, order, score
                            if best_left is None:
                                continue
                            right_evaluator = prepare(right_rest+(a, pending), target)
                            for position in range(len(right_rest)+1):
                                middle = right_rest[:position]+(a,)+right_rest[position:]
                                for insertion in range(len(middle)+1):
                                    if expired():
                                        return None
                                    right = middle[:insertion]+(pending,)+middle[insertion:]
                                    fast_score = replay(right_evaluator, right)
                                    if fast_score is None:
                                        continue
                                    candidate = list(routes)
                                    candidate[source], candidate[target] = best_left[1], right
                                    candidate = tuple(candidate)
                                    candidate_scores = list(scores)
                                    candidate_scores[source] = evaluate(candidate[source], source)
                                    candidate_scores[target] = evaluate(candidate[target], target)
                                    info['canonical_candidates'] += 1
                                    if candidate_scores[source] is None or candidate_scores[target] is None:
                                        info['invalid_candidates'] += 1
                                        continue
                                    candidate_scores = tuple(candidate_scores)
                                    if _better(_plan_key(candidate, candidate_scores, rows, vehicles, strategy),
                                               _plan_key(routes, scores, rows, vehicles, strategy)):
                                        return candidate, candidate_scores
        return None

    while sum(map(len, routes)) < len(possible) and not expired():
        improved = step()
        if improved is None:
            break
        routes, scores = improved
        info['improvements'] += 1
    info['wall_seconds'] = perf_counter()-started
    return routes, scores, info


def solve_fleet_milp(rows, vehicles, matrix, points, start_time, return_depot,
                     limits, initial_routes, evaluate, *, initial_results=None,
                     strategy='efficient', max_seconds=30):
    """Recover a complete allocation using HiGHS, retaining a validated incumbent.

    The first-stage objective preserves existing arcs to help find a complete
    feasible repair quickly. Actual acceptance uses the application's declared
    coverage/compatibility/distance/workload objective, never this guide cost.
    A timeout or an infeasible conservative model is not a physical-impossibility
    certificate. All vehicle-to-stop compatibilities and feasible time arcs are
    represented; no geographical territory or witness is supplied to the model.
    """
    from .. import optimizer as opt
    from .fleet_search import _better, stable_stop_key

    started = perf_counter()
    routes = tuple(tuple(order) for order in initial_routes)
    scores = tuple(initial_results) if initial_results is not None else tuple(
        evaluate(order, v) if order else None for v, order in enumerate(routes))
    diagnostics = dict(method='highs-global-working-clock-milp', status='not-started',
        global_optimum_proven=False, max_seconds=float(max_seconds),
        canonical_candidates=0, invalid_candidates=0, improvements=0)
    if max_seconds <= 0 or not rows or not vehicles:
        diagnostics['status'] = 'disabled'
        return routes, scores, diagnostics
    try:
        import numpy as np
        import scipy
        from scipy.optimize import milp  # noqa: F401
    except ImportError:
        diagnostics['status'] = 'dependency-unavailable'
        return routes, scores, diagnostics
    n, resource_count = len(rows), len(vehicles)
    if len(routes) != resource_count or len(limits) != resource_count:
        raise ValueError('MILP recovery needs one route and horizon per resource')
    canonical = sorted(range(n), key=lambda i: (stable_stop_key(rows[i]), i))
    start = opt._start_clock(start_time)
    service = {i: float(rows[i].get('tempo_scarico_min') or 0) for i in canonical}
    nodes = {-1: 0, **{i: rows[i].get('_matrix_index', i+1) for i in canonical}}
    road = {(i, j): opt._matrix_leg(matrix, points, nodes[i], nodes[j])
            for i in nodes for j in nodes if i != j}
    model = _Model()
    y, t, u, end, arcs, bounds = {}, {}, {}, {}, {}, {}
    incoming, outgoing = {}, {}
    existing = set()
    for v, order in enumerate(routes):
        if order:
            existing.update((v, a, b) for a, b in zip((-1,)+order, order+(-2,)))
    domains, horizons = {}, {}
    for v, (vehicle, limit) in enumerate(zip(vehicles, limits)):
        _, scaled_horizon = service_domains({}, vehicle, start, limit)
        horizon = scaled_horizon / TIME_SCALE
        horizons[v] = horizon
        u[v] = model.variable(integer=True)
        end[v] = model.variable(high=horizon)
        model.constraint(((end[v], 1), (u[v], -horizon)), high=0)
        for i in canonical:
            intervals, _ = service_domains(rows[i], vehicle, start, limit)
            if not _compatible(rows[i], vehicle) or not intervals:
                continue
            intervals = tuple((lo/TIME_SCALE, hi/TIME_SCALE) for lo, hi in intervals)
            domains[v, i] = intervals
            low, high = intervals[0][0], intervals[-1][1]
            bounds[v, i] = low, high
            y[v, i] = model.variable(integer=True)
            t[v, i] = model.variable(high=high)
            model.constraint(((t[v, i], 1), (y[v, i], -low)), low=0)
            model.constraint(((t[v, i], 1), (y[v, i], -high)), high=0)
            if len(intervals) > 1:
                selectors = [model.variable(integer=True) for _ in intervals]
                model.constraint([(q, 1) for q in selectors]+[(y[v, i], -1)], low=0, high=0)
                model.constraint([(t[v, i], 1)]+[(q, -lo) for q, (lo, _) in zip(selectors, intervals)], low=0)
                model.constraint([(t[v, i], 1)]+[(q, -hi) for q, (_, hi) in zip(selectors, intervals)], high=0)
            incoming[v, i], outgoing[v, i] = [], []

    possible = [i for i in canonical if any((v, i) in y for v in range(resource_count))]
    diagnostics.update(potentially_serviceable=len(possible), scipy_version=scipy.__version__)
    if len(possible) <= sum(map(len, routes)):
        diagnostics.update(status='no-coverage-recovery-needed', wall_seconds=perf_counter()-started)
        return routes, scores, diagnostics
    pair_deadline = started+min(3.0, float(max_seconds)*.2)
    routes, scores, pair_info = _pair_exchange_repair(
        rows, vehicles, matrix, points, start_time, return_depot, limits,
        routes, scores, possible, evaluate, strategy, pair_deadline)
    diagnostics['repair_stages'] = [pair_info]
    diagnostics['canonical_candidates'] = pair_info['canonical_candidates']
    diagnostics['invalid_candidates'] = pair_info['invalid_candidates']
    diagnostics['improvements'] = int(pair_info['improvements'] > 0)
    if sum(map(len, routes)) == len(possible):
        diagnostics.update(status='feasible', completed_stage='prepared-pair-exchange',
                           served=sum(map(len, routes)), wall_seconds=perf_counter()-started)
        return routes, scores, diagnostics
    # The pair search leaves nearly all of the allowance for the unrestricted
    # global model. Failed pinned sub-MIPs must not exhaust this budget.
    existing = {(v, a, b) for v, order in enumerate(routes) if order
                for a, b in zip((-1,)+order, order+(-2,))}
    rank = {i: model.variable(low=1, high=n) for i in possible}
    for i in possible:
        model.constraint([(y[v, i], 1) for v in range(resource_count) if (v, i) in y], low=1, high=1)
    max_km = max((float(leg['km']) for leg in road.values()), default=1)
    # This is only a feasibility-search guide: any full feasible result beats
    # the incomplete incumbent under both actual fleet strategies.
    distance_factor = 1 / max(1.0, (n+resource_count)*max_km*100)
    for v, vehicle in enumerate(vehicles):
        members = [i for i in canonical if (v, i) in y]
        departures, arrivals = [], []
        for demand, capacity in (('peso_kg', 'capacita_kg'), ('colli', 'capacita_colli')):
            if vehicle.get(capacity) is not None:
                model.constraint([(y[v, i], float(rows[i].get(demand) or 0)) for i in members],
                                 high=float(vehicle[capacity]))
        for a in [-1]+members:
            for b in members+[-2]:
                if a == b or (a == -1 and b == -2):
                    continue
                duration = (road[a, b]['min'] if b != -2 else
                            road[a, -1]['min'] if return_depot else 0)
                distance = (road[a, b]['km'] if b != -2 else
                            road[a, -1]['km'] if return_depot else 0)
                before = 0 if a == -1 else bounds[v, a][0]+service[a]
                after = horizons[v] if b == -2 else bounds[v, b][1]
                if before + duration > after + 1e-10:
                    continue
                edge = model.variable(integer=True,
                    cost=(0 if (v, a, b) in existing else 1)+float(distance)*distance_factor)
                arcs[v, a, b] = edge
                if a == -1:
                    departures.append(edge)
                else:
                    outgoing[v, a].append(edge)
                if b == -2:
                    arrivals.append(edge)
                else:
                    incoming[v, b].append(edge)
                if a == -1:
                    model.constraint(((t[v, b], 1), (edge, -duration)), low=0)
                elif b == -2:
                    maximum = bounds[v, a][1]+service[a]+duration
                    model.constraint(((end[v], 1), (t[v, a], -1), (edge, -maximum)),
                                     low=service[a]+duration-maximum)
                else:
                    maximum = bounds[v, a][1]+service[a]+duration
                    model.constraint(((t[v, b], 1), (t[v, a], -1), (edge, -maximum)),
                                     low=service[a]+duration-maximum)
                    model.constraint(((rank[b], 1), (rank[a], -1), (edge, -(n+1))), low=-n)
        model.constraint([(edge, 1) for edge in departures]+[(u[v], -1)], low=0, high=0)
        model.constraint([(edge, 1) for edge in arrivals]+[(u[v], -1)], low=0, high=0)
        for i in members:
            model.constraint([(edge, 1) for edge in incoming[v, i]]+[(y[v, i], -1)], low=0, high=0)
            model.constraint([(edge, 1) for edge in outgoing[v, i]]+[(y[v, i], -1)], low=0, high=0)
    diagnostics.update(binary_variables=sum(model.integer), variables=len(model.cost),
                       constraints=len(model.lo), arcs=len(arcs))
    # Give the full model an advisory partial start from the validated plan.
    # Missing/nearby jobs and early temporal blockers remain unknown so HiGHS
    # can repair their assignments and sequence. No model bounds are fixed.
    assigned = {i for order in routes for i in order}
    missing = set(possible)-assigned
    nearby = sorted(assigned, key=lambda i: (
        min(road[m, i]['km']+road[i, m]['km'] for m in missing),
        stable_stop_key(rows[i])))
    freed = missing|set(nearby[:12])|{i for order in routes for i in order[:2]}
    hints = {y[v, i]: 1.0 for v, order in enumerate(routes) for i in order
             if i not in freed and (v, i) in y}
    hints.update({edge: 1.0 for (v, a, b), edge in arcs.items()
                  if (v, a, b) in existing and a not in freed and b not in freed})
    remaining = max(.001, float(max_seconds)-(perf_counter()-started))
    before = perf_counter()
    result = model.solve(remaining, hints=hints)
    diagnostics['repair_stages'].append(dict(method='global-unrestricted',
        released_stops=len(possible), fixed_arcs=0, status=int(result.status),
        sparse_hint_variables=len(hints), hint_released_stops=len(freed),
        backend=result.get('backend', 'scipy-public-milp'),
        native_start_status=result.get('native_start_status'),
        seconds=perf_counter()-before, has_solution=result.x is not None))
    diagnostics.update(status={0: 'feasible', 1: 'limit-reached', 2: 'model-infeasible',
                               3: 'unbounded', 4: 'solver-error'}.get(result.status, 'unknown'),
        message=str(result.message), solver_nodes=int(getattr(result, 'mip_node_count', 0) or 0),
        wall_seconds=perf_counter()-started)
    if result.x is None:
        return routes, scores, diagnostics
    candidate, covered = [], set()
    for v in range(resource_count):
        successor = {a: b for (resource, a, b), edge in arcs.items()
                     if resource == v and result.x[edge] > .5}
        order, cursor = [], successor.get(-1, -2)
        while cursor != -2:
            if cursor in covered or cursor not in possible:
                diagnostics.update(status='invalid-path', invalid_candidates=1)
                return routes, scores, diagnostics
            covered.add(cursor)
            order.append(cursor)
            if cursor not in successor:
                diagnostics.update(status='invalid-path', invalid_candidates=1)
                return routes, scores, diagnostics
            cursor = successor[cursor]
        candidate.append(tuple(order))
    if covered != set(possible):
        diagnostics.update(status='disconnected-path', invalid_candidates=1)
        return routes, scores, diagnostics
    candidate = tuple(candidate)
    proposed = tuple(evaluate(order, v) if order else None for v, order in enumerate(candidate))
    diagnostics['canonical_candidates'] += 1
    if any(order and score is None for order, score in zip(candidate, proposed)):
        diagnostics.update(status='canonical-rejection')
        diagnostics['invalid_candidates'] += 1
        return routes, scores, diagnostics
    if _better(_plan_key(candidate, proposed, rows, vehicles, strategy),
               _plan_key(routes, scores, rows, vehicles, strategy)):
        routes, scores = candidate, proposed
        diagnostics['improvements'] = 1
    diagnostics.update(served=sum(map(len, routes)), wall_seconds=perf_counter()-started)
    return routes, scores, diagnostics
