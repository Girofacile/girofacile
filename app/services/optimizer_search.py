"""Deterministic, matrix-only search beyond eight stops.

The full historical search is a mandatory quality floor. The configurable
candidate budget applies to additional search, never truncates that floor.
"""
import os
import time
from itertools import zip_longest


class RouteEvaluator:
    """Score-only replay with pre-parsed windows; final output uses the canonical evaluator."""

    def __init__(self, deliveries, matrix, points, vehicle, return_depot, start_time):
        from .. import optimizer as opt
        self.opt = opt
        self.matrix, self.points, self.vehicle = matrix, points, vehicle
        self.return_depot, self.start_time = return_depot, start_time
        self.start = opt._start_clock(start_time)
        self.windows = {d['_matrix_index']: opt.delivery_windows(d) for d in deliveries}
        self.service = {d['_matrix_index']: float(d.get('tempo_scarico_min') or 0) for d in deliveries}
        self.warnings = {d['_matrix_index']: len(opt.delivery_warnings(d, vehicle)) for d in deliveries}
        self.constrained = {d['_matrix_index']: opt._has_strong_constraints([d]) for d in deliveries}
        self.timing_cache = {}
        self.candidates = 0

    def evaluate(self, sequence, *args, include_details=True, earliest_windows=False):
        self.candidates += 1
        opt = self.opt
        if include_details or earliest_windows:
            result = opt._evaluate_fixed_sequence(sequence, self.matrix, self.points, self.vehicle,
                self.return_depot, self.start_time, include_details=include_details, earliest_windows=earliest_windows)
            result['_search_order'] = tuple(d['_matrix_index'] for d in sequence)
            return result
        clock, previous = self.start, 0
        km = wait = late = 0.0
        violations = warnings = 0
        constrained = False
        for d in sequence:
            node = d['_matrix_index']
            leg = opt._matrix_leg(self.matrix, self.points, previous, node)
            windows = self.windows[node]
            if windows:
                timing_key = (previous, node, clock)
                ev = self.timing_cache.get(timing_key)
                if ev is None:
                    ev = opt.evaluate_candidate(clock, leg, d, windows=windows)
                    # Request-local, bounded cache. Exact clock keys; no rounding
                    # or dominance assumptions that could change feasibility.
                    if len(self.timing_cache) >= 8192:
                        self.timing_cache.clear()
                    self.timing_cache[timing_key] = ev
                clock = ev['service_start'] + self.service[node]
                wait += ev['wait']
                violations += not ev['feasible']
                warnings += bool(ev['warning'])
                late += max(0.0, clock - ev['window_end'])
            else:
                clock = clock + leg['min'] + self.service[node]
            warnings += self.warnings[node]
            constrained |= self.constrained[node]
            km += leg['km']
            previous = node
        if self.return_depot and sequence:
            back = opt._matrix_leg(self.matrix, self.points, previous, 0)
            km += back['km']
            clock += back['min']
        duration = clock - self.start
        # Preserve the existing diagnostic/infeasible score exactly; all search
        # comparisons go through solution_key, not this weighted legacy field.
        score = (violations * 100000 + duration * 10 + wait * 1.5 + warnings * 25 + km
                 if constrained else duration * 10 + km)
        return dict(total_km=round(km, 2), total_min=round(duration, 1),
                    total_wait=round(wait, 1), total_lateness_min=late,
                    violations=violations, score=score, _objective=(km, duration, wait, warnings))


def candidate_limit(n):
    # Bound default stop-visits too: 10k replays at 50 stops, 5k at 100.
    default = min(10000, max(100, 500000 // n))
    try:
        return max(0, min(200000, int(os.getenv('OPTIMIZER_MAX_CANDIDATES', str(default)))))
    except (ValueError, TypeError):
        return default


class CandidateBudget:
    def __init__(self, evaluator, limit):
        self.evaluator, self.limit = evaluator, limit
        self.used = 0
        self.exhausted = False

    def evaluate(self, sequence):
        if self.used >= self.limit:
            self.exhausted = True
            return None
        self.used += 1
        return self.evaluator.evaluate(sequence, include_details=False)


def nearest_neighbour(rows, matrix):
    remaining, order, previous = rows[:], [], 0
    while remaining:
        chosen = min(range(len(remaining)), key=lambda i: (
            matrix[previous, remaining[i]['_matrix_index']]['km'],
            matrix[previous, remaining[i]['_matrix_index']]['min'], i))
        stop = remaining.pop(chosen)
        order.append(stop)
        previous = stop['_matrix_index']
    return order


def cheapest_insertion(rows, matrix, return_depot):
    """Global cheapest directed insertion; a free endpoint stays free for open tours."""
    remaining, order = rows[:], []
    while remaining:
        best = None
        for i, row in enumerate(remaining):
            node = row['_matrix_index']
            for position in range(len(order) + 1):
                before = order[position - 1]['_matrix_index'] if position else 0
                after = order[position]['_matrix_index'] if position < len(order) else (0 if return_depot else None)
                delta_km, delta_min = matrix[before, node]['km'], matrix[before, node]['min']
                if after is not None:
                    delta_km += matrix[node, after]['km']
                    delta_min += matrix[node, after]['min']
                    if before != after:
                        delta_km -= matrix[before, after]['km']
                        delta_min -= matrix[before, after]['min']
                key = (delta_km, delta_min, i, position)
                if best is None or key < best:
                    best = key
        _, _, i, position = best
        order.insert(position, remaining.pop(i))
    return order


def window_insertion(rows, evaluator, budget):
    """Insert urgent windows first; placement still uses feasibility/distance/time.

    Partial schedules are charged to the same budget. An unfinished seed is
    discarded, never returned as a route with missing deliveries.
    """
    order = []
    pending = sorted(rows, key=lambda d: (
        min((b for _, b in evaluator.windows[d['_matrix_index']]), default=float('inf')),
        d['_matrix_index']))
    for row in pending:
        best, best_order = None, None
        for position in range(len(order) + 1):
            candidate = order[:position] + [row] + order[position:]
            result = budget.evaluate(candidate)
            if result is None:
                return None
            if best is None or evaluator.opt.solution_key(result) < evaluator.opt.solution_key(best):
                best, best_order = result, candidate
        order = best_order
    return order


def window_lookahead(rows, evaluator):
    """Distance-first greedy with a one-stop check against the next closing window.

    Time is used to detect a projected constraint violation, never weighted
    against km. This cheap window seed remains available on 50+ stop tours.
    """
    remaining, order, previous, clock = rows[:], [], 0, evaluator.start
    while remaining:
        urgent = sorted(remaining, key=lambda d: (
            min((b for _, b in evaluator.windows[d['_matrix_index']]), default=float('inf')),
            d['_matrix_index']))[:2]
        choices = []
        for i, row in enumerate(remaining):
            node = row['_matrix_index']
            leg = evaluator.matrix[previous, node]
            ev = evaluator.opt.evaluate_candidate(clock, leg, row, windows=evaluator.windows[node])
            end = ev['service_start'] + evaluator.service[node]
            next_urgent = next((d for d in urgent if d['_matrix_index'] != node), None)
            misses_next = False
            if next_urgent is not None:
                nxt = next_urgent['_matrix_index']
                future = evaluator.opt.evaluate_candidate(end, evaluator.matrix[node, nxt], next_urgent,
                                                          windows=evaluator.windows[nxt])
                misses_next = not future['feasible']
            priority = (not ev['feasible'], 0 if ev['feasible'] else ev['score'],
                        misses_next, leg['km'], leg['min'] + ev['wait'], ev['wait'], i)
            choices.append((priority, i, end))
        _, chosen, clock = min(choices)
        row = remaining.pop(chosen)
        order.append(row)
        previous = row['_matrix_index']
    return order


def or_opt_moves(sequence, length):
    """Relocate an intact block; never assumes A→B equals B→A."""
    n = len(sequence)
    for start in range(n - length + 1):
        block = sequence[start:start + length]
        rest = sequence[:start] + sequence[start + length:]
        for destination in range(len(rest) + 1):
            if destination != start:
                yield rest[:destination] + block + rest[destination:]


def swap_moves(sequence):
    for i in range(len(sequence) - 1):
        for j in range(i + 1, len(sequence)):
            candidate = sequence[:]
            candidate[i], candidate[j] = candidate[j], candidate[i]
            yield candidate


def reversal_moves(sequence):
    for i in range(len(sequence) - 2):
        for j in range(i + 2, len(sequence)):
            yield sequence[:i] + sequence[i:j + 1][::-1] + sequence[j + 1:]


def bounded_descent(sequence, result, budget, quota, *, block_lengths=(2, 3, 1), rounds=3):
    """Round-robin neighborhoods and best improvement; quota cannot starve a move family."""
    key = budget.evaluator.opt.solution_key
    used_at_start = budget.used
    for _ in range(rounds):
        previous_key = key(result)
        neighborhoods = [or_opt_moves(sequence, length) for length in block_lengths]
        neighborhoods += [swap_moves(sequence), reversal_moves(sequence)]
        best_order, best_result = sequence, result
        # Generators capture this round's starting order. Full directed schedule
        # replay handles reversed internal arcs, waiting and propagated lateness.
        for group in zip_longest(*neighborhoods):
            for candidate in group:
                if candidate is None:
                    continue
                if budget.used - used_at_start >= quota:
                    return best_order, best_result
                candidate_result = budget.evaluate(candidate)
                if candidate_result is None:
                    return best_order, best_result
                if key(candidate_result) < key(best_result):
                    best_order, best_result = candidate, candidate_result
        sequence, result = best_order, best_result
        if key(result) >= previous_key:
            break
    return sequence, result


def search_large_route(rows, matrix, points, vehicle, return_depot, start_time, diagnostics=None):
    from .. import optimizer as opt
    cpu_start, wall_start = time.process_time(), time.perf_counter()
    evaluator = RouteEvaluator(rows, matrix, points, vehicle, return_depot, start_time)
    # Complete *every* old seed/move and the old feasibility fallback first.
    baseline = opt._legacy_internal_sequence(rows, matrix, points, vehicle, return_depot,
                                            start_time, evaluator=evaluator.evaluate)
    baseline_candidates = evaluator.candidates
    baseline_ms = (time.process_time() - cpu_start) * 1000
    lookup = {d['_matrix_index']: d for d in rows}
    # Instrumented canonical evaluations retain indices internally, even for
    # identical customers/coordinates. Never reconstruct identity from labels.
    best_order = [lookup[i] for i in baseline['_search_order']]
    best = baseline
    budget = CandidateBudget(evaluator, candidate_limit(len(rows)))
    seeds, seen, seed_names = [], set(), []

    def add_seed(name, order):
        nonlocal best, best_order
        if order is None:
            return
        signature = tuple(d['_matrix_index'] for d in order)
        if signature in seen:
            return
        seen.add(signature)
        result = budget.evaluate(order)
        if result is None:
            return
        seeds.append((order, result))
        seed_names.append(name)
        if opt.solution_key(result) < opt.solution_key(best):
            best_order, best = order, result

    if budget.limit:
        greedy = opt._greedy_sequence(rows, matrix, points, vehicle, start_time)
        builders = [('baseline', lambda: best_order), ('greedy', lambda: greedy),
                    ('operator', lambda: rows), ('reverse_operator', lambda: rows[::-1]),
                    ('reverse_greedy', lambda: greedy[::-1]),
                    ('nearest_distance', lambda: nearest_neighbour(rows, matrix)),
                    ('cheapest_insertion', lambda: cheapest_insertion(rows, matrix, return_depot))]
        for name, build in builders:
            if budget.used >= budget.limit:
                budget.exhausted = True
                break
            add_seed(name, build())
        if any(evaluator.windows.values()) and budget.used < budget.limit:
            add_seed('window_lookahead', window_lookahead(rows, evaluator))
            # Reserve at least half of the remaining budget for local search.
            needed = len(rows) * (len(rows) + 1) // 2 + 1
            if needed <= (budget.limit - budget.used) // 2:
                add_seed('window_insertion', window_insertion(rows, evaluator, budget))
        # Each distinct seed gets a deterministic share, also above 15 stops.
        for i, (seed, result) in enumerate(seeds):
            quota = (budget.limit - budget.used) // (len(seeds) - i)
            order, result = bounded_descent(seed, result, budget, quota)
            if opt.solution_key(result) < opt.solution_key(best):
                best_order, best = order, result
    else:
        budget.exhausted = True
    result = evaluator.evaluate(best_order)
    # Preserve the baseline object on exact ties, including fallback schedules.
    if opt.solution_key(baseline) <= opt.solution_key(result):
        result = baseline
    result.pop('_search_order', None)
    if diagnostics is not None:
        diagnostics.update(optimizer_strategy='legacy-floor+bounded-multistart',
            candidates_evaluated=evaluator.candidates, baseline_candidates=baseline_candidates,
            additional_candidates=budget.used, candidate_budget=budget.limit,
            optimization_budget_exhausted=budget.exhausted or budget.used >= budget.limit,
            baseline_cpu_ms=baseline_ms, optimization_ms=(time.perf_counter() - wall_start) * 1000,
            optimization_cpu_ms=(time.process_time() - cpu_start) * 1000,
            seeds_evaluated=seed_names)
    return result
