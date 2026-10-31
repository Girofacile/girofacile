"""Deterministic fleet-wide search on one immutable road matrix.

Geographic orders are flexible seeds, never territory constraints. Every accepted
route is replayed by the caller's scheduler (windows, unloading, breaks, shifts,
capacity and existing bookings). The caller enforces physical compatibility;
remaining advisory equipment preferences are ranked by its penalty callback.
"""
from itertools import permutations, zip_longest
import json
import math
import os


def candidate_limit(stop_count):
    # Two complementary searches share this TOTAL quota: the established
    # vehicle/time construction and the adaptive distance/coverage search.
    default = 2 * min(20000, max(5000, 500000 // max(1, stop_count)))
    try:
        return max(0, min(100000, int(os.getenv("FLEET_MAX_CANDIDATES", str(default)))))
    except (TypeError, ValueError):
        return default


def _better(left, right):
    """Compare objectives without letting floating representation noise win."""
    for a, b in zip(left, right):
        noise = max(1e-9, 512 * max(math.ulp(float(a)), math.ulp(float(b))))
        if a < b - noise:
            return True
        if a > b + noise:
            return False
    return False


def _numbers(result):
    if result is None:
        return 0.0, 0.0
    raw = result.get("_objective")
    return (float(raw[1]), float(raw[0])) if raw else (
        float(result["total_min"]), float(result["total_km"]))


def _route_key(result, strategy):
    minutes, distance = _numbers(result)
    return (distance, minutes) if strategy == "efficient" else (minutes, distance)


def stable_stop_key(row):
    """A request-order-independent tie key, including distinct orders at a customer."""
    fields = ('order_stop_key', 'order_refs', 'customer_id', 'cliente_nome',
              'indirizzo', 'lat', 'lon', 'coord', 'peso_kg', 'colli',
              'tempo_scarico_min', 'scarico_mattina_da', 'scarico_mattina_a',
              'scarico_pomeriggio_da', 'scarico_pomeriggio_a', 'sponda', 'ztl')
    stable = {name: row.get(name) for name in fields if name in row}
    return json.dumps(stable, sort_keys=True, default=str, ensure_ascii=True)


def _identity(row, fallback):
    return stable_stop_key(row), fallback


def _urgency(row):
    """First closing window, narrowest window, then the greatest declared load."""
    windows = []
    for period in ('mattina', 'pomeriggio'):
        start, end = row.get('scarico_' + period + '_da'), row.get('scarico_' + period + '_a')
        try:
            a = sum(int(value) * multiplier for value, multiplier in zip(str(start).split(':')[:2], (60, 1)))
            b = sum(int(value) * multiplier for value, multiplier in zip(str(end).split(':')[:2], (60, 1)))
            if start and end and b > a:
                windows.append((b, b - a))
        except (ValueError, TypeError):
            continue
    return (*min(windows, default=(math.inf, math.inf)),
            -float(row.get('peso_kg') or 0), -float(row.get('colli') or 0))


def optimize_fleet(rows, resource_count, evaluate, strategy, *,
                   initial_routes=None, initial_results=None, matrix=None,
                   points=None, equipment_penalty=None, resource_signatures=None,
                   return_depot=True, initial_candidates=None,
                   membership_compatible=None):
    """Return resource-indexed stop sequences, evaluations and search diagnostics.

    Exhaustive subset/permutation search is restricted to <=7 stops/<=3 resources.
    Larger problems retain the complete existing insertion as a quality floor and
    use a deterministic additional evaluation budget, including all seed work.
    No wall-clock cut-off changes the result across repeated identical requests.
    """
    n = len(rows)
    identities = [_identity(row, index) for index, row in enumerate(rows)]
    stable = sorted(range(n), key=identities.__getitem__)
    penalty = equipment_penalty or (lambda sequence, resource: 0)
    empty = tuple(() for _ in range(resource_count))
    initial_routes = tuple(tuple(route) for route in (initial_routes or empty))
    initial_results = tuple(initial_results or (None,) * resource_count)
    def valid_plan(routes, results):
        assigned = [index for route in routes for index in route]
        return (len(routes) == resource_count and len(results) == resource_count
                and len(assigned) == len(set(assigned))
                and all(type(index) is int and 0 <= index < n for index in assigned)
                and all(not route or result is not None for route, result in zip(routes, results)))
    if not valid_plan(initial_routes, initial_results):
        initial_routes, initial_results = empty, (None,) * resource_count
    initial_candidates = tuple((tuple(tuple(route) for route in routes), tuple(results))
                               for routes, results in (initial_candidates or ())
                               if valid_plan(routes, results))
    aliases = list(range(resource_count))
    if resource_signatures:
        known = {}
        for resource, signature in enumerate(resource_signatures):
            aliases[resource] = known.setdefault(signature, resource)
    cache = {}
    membership_cache = {}
    membership_rejections = 0
    membership_checks = 0
    used = 0
    limit = candidate_limit(n)
    exact = n <= 7 and resource_count <= 3
    exhausted = False
    from .fleet_route_pool import RoutePool
    pool = RoutePool(resource_count, n, route_key=lambda result: _route_key(result, strategy))
    for resource, (order, result) in enumerate(zip(initial_routes, initial_results)):
        if order and result is not None:
            pool.add(resource, order, result)
    for candidate_routes, candidate_results in initial_candidates or ():
        for resource, (order, result) in enumerate(zip(candidate_routes, candidate_results)):
            if order and result is not None:
                pool.add(resource, order, result)

    def replay(sequence, resource):
        nonlocal used, exhausted, membership_rejections, membership_checks
        if not sequence:
            return None
        key = (aliases[resource], tuple(sequence))
        if key in cache:
            result = cache[key]
            if result is not None:
                pool.add(resource, sequence, result)
            return result
        # Weight, parcel count and required equipment depend on membership,
        # not visit order. Reject these necessary conditions once before
        # spending a full scheduling evaluation on every permutation.
        if membership_compatible is not None:
            membership = (aliases[resource], frozenset(sequence))
            if membership not in membership_cache:
                if len(membership_cache) >= 4096:
                    membership_cache.clear()
                membership_checks += 1
                membership_cache[membership] = bool(membership_compatible(sequence, resource))
            if not membership_cache[membership]:
                membership_rejections += 1
                return None
        if not exact and used >= limit:
            exhausted = True
            return None
        used += 1
        result = evaluate(tuple(sequence), resource)
        if result is not None:
            pool.add(resource, sequence, result)
        if len(cache) >= 4096:
            cache.clear()
        cache[key] = result
        return result

    def plan_key(routes, results):
        durations, distances = zip(*(_numbers(result) for result in results))
        served = sum(map(len, routes))
        mismatches = sum(penalty(route, resource) for resource, route in enumerate(routes))
        active = sum(bool(route) for route in routes)
        common = (-served, mismatches)
        if strategy == "balanced":
            return common + (-active, max(durations, default=0),
                             sum(value * value for value in durations),
                             sum(durations), sum(distances))
        return common + (sum(distances), sum(durations), active)

    best_routes, best_results = initial_routes, initial_results
    best_key = plan_key(best_routes, best_results)
    repair_population = {}

    def remember(routes, results, key):
        if sum(map(len, routes)) == n:
            return
        assigned = frozenset(index for route in routes for index in route)
        if len(assigned) < -best_key[0] - 3:
            return
        previous = repair_population.get(assigned)
        if previous is None or _better(key, previous[0]):
            repair_population[assigned] = (key, tuple(tuple(route) for route in routes), tuple(results))
        if len(repair_population) > 12:
            obsolete = max(repair_population, key=lambda mask: repair_population[mask][0])
            del repair_population[obsolete]

    def consider(routes, results):
        nonlocal best_routes, best_results, best_key
        if not valid_plan(routes, results):
            return False
        key = plan_key(routes, results)
        remember(routes, results, key)
        if _better(key, best_key):
            best_routes = tuple(tuple(route) for route in routes)
            best_results = tuple(results)
            best_key = key
            return True
        return False

    for candidate_routes, candidate_results in initial_candidates or ():
        consider(candidate_routes, candidate_results)

    seed_diagnostics = None
    if exact:
        # No partial-feasibility pruning: waiting and breaks need a full replay.
        options = []
        equivalent = {}
        for resource in range(resource_count):
            if aliases[resource] in equivalent:
                options.append(equivalent[aliases[resource]])
                continue
            choices = {0: ((), None)}
            for mask in range(1, 1 << n):
                members = tuple(index for index in range(n) if mask & (1 << index))
                winner = None
                for order in permutations(members):
                    result = replay(order, resource)
                    if result is None:
                        continue
                    key = _route_key(result, strategy)
                    if winner is None or _better(key, winner[0]):
                        winner = (key, order, result)
                if winner is not None:
                    choices[mask] = (winner[1], winner[2])
            options.append(choices)
            equivalent[aliases[resource]] = choices

        def partition(resource, remaining, routes, results):
            if resource == resource_count:
                consider(routes, results)
                return
            subset = remaining
            while True:
                selected = options[resource].get(subset)
                if selected is not None:
                    order, result = selected
                    partition(resource + 1, remaining ^ subset,
                              routes + (order,), results + (result,))
                if subset == 0:
                    break
                subset = (subset - 1) & remaining

        partition(0, (1 << n) - 1, (), ())
    elif limit:
        from .fleet_seed_search import optimize_seed
        seed_allowance = limit // 2
        seed_routes, seed_results = initial_candidates[0] if initial_candidates else (
            initial_routes, initial_results)
        before_seed = used
        seed_routes, seed_results, seed_diagnostics = optimize_seed(
            rows, resource_count, replay, strategy, budget=seed_allowance,
            initial_routes=seed_routes, initial_results=seed_results,
            matrix=matrix, points=points, equipment_penalty=penalty,
            resource_signatures=resource_signatures, return_depot=return_depot)
        consider(seed_routes, seed_results)
        seed_diagnostics = dict(seed_diagnostics,
            shared_budget_allowance=seed_allowance,
            canonical_evaluations=used-before_seed)
        if strategy == 'balanced' and -best_key[0] < n and used < limit:
            # A different exploration priority can expose a feasible packing
            # that workload-first moves never visit. Its output still competes
            # under the selected BALANCED objective and the same total quota.
            before_alternate = used
            alternate_allowance = min(5000, (limit-used)//3)
            alternate_routes, alternate_results, alternate_diagnostics = optimize_seed(
                rows, resource_count, replay, 'efficient', budget=alternate_allowance,
                initial_routes=best_routes, initial_results=best_results,
                matrix=matrix, points=points, equipment_penalty=penalty,
                resource_signatures=resource_signatures, return_depot=return_depot)
            consider(alternate_routes, alternate_results)
            seed_diagnostics['complementary_search'] = dict(alternate_diagnostics,
                shared_budget_allowance=alternate_allowance,
                canonical_evaluations=used-before_alternate)
        phase_start = used
        phase_allowance = limit-phase_start

        def leg(a, b):
            if a == b:
                return 0.0
            return float((matrix or {}).get((a + 1, b + 1), {}).get("km", 0.0))

        def depot_leg(index):
            return float((matrix or {}).get((0, index + 1), {}).get("km", 0.0))

        def positions(order, index, quick=False):
            positions = list(range(len(order) + 1))
            def added(position):
                before = order[position - 1] if position else None
                after = order[position] if position < len(order) else None
                value = depot_leg(index) if before is None else leg(before, index)
                if after is not None:
                    value += leg(index, after)
                    value -= depot_leg(after) if before is None else leg(before, after)
                elif return_depot:
                    value += float((matrix or {}).get((index + 1, 0), {}).get('km', 0.0))
                    if before is not None:
                        value -= float((matrix or {}).get((before + 1, 0), {}).get('km', 0.0))
                return value, position
            positions.sort(key=added)
            # Critical windows/equipment must never be limited to the three
            # geographically cheapest slots; a feasible insertion can be later.
            critical = bool(_urgency(rows[index])[0] < math.inf or
                            rows[index].get('sponda') or rows[index].get('ztl'))
            return positions[:4] if quick and not critical else positions

        def insert(index, routes, results, *, quick=False, deadline=None,
                   construction=None):
            candidate_best = None
            resources = list(range(resource_count))
            if quick:
                def proximity(resource):
                    order = routes[resource]
                    geographic = min((leg(i, index) + leg(index, i) for i in order),
                                     default=2 * depot_leg(index))
                    use = bool(order) if strategy == "balanced" else not bool(order)
                    return penalty((index,), resource), use, geographic, resource
                resources.sort(key=proximity)
                if not (_urgency(rows[index])[0] < math.inf or
                        rows[index].get('sponda') or rows[index].get('ztl')):
                    resources = resources[:3]
            for resource in resources:
                for position in positions(routes[resource], index, quick):
                    if deadline is not None and used >= deadline:
                        return candidate_best
                    order = routes[resource][:position] + (index,) + routes[resource][position:]
                    result = replay(order, resource)
                    if result is None:
                        continue
                    changed_routes, changed_results = list(routes), list(results)
                    changed_routes[resource], changed_results[resource] = order, result
                    key = plan_key(changed_routes, changed_results)
                    if construction == 'balanced':
                        # A distance-first greedy packing can strand a heavy or
                        # bulky job even when every delivery fits jointly.
                        # Balance an independent construction, then compare its
                        # completed plan under the user's unchanged objective.
                        minutes = [_numbers(score)[0] for score in changed_results]
                        key = key[:2] + (-sum(bool(route) for route in changed_routes),
                            max(minutes, default=0), sum(value * value for value in minutes),
                            sum(minutes), sum(_numbers(score)[1] for score in changed_results))
                    if candidate_best is None or _better(key, candidate_best[0]):
                        candidate_best = key, tuple(changed_routes), tuple(changed_results)
            return candidate_best

        # Flexible road-neighbour groups: no postcode, boundary or straight-line
        # membership can prevent a later feasible cross-zone move.
        remaining = set(stable)
        nearest = []
        previous = None
        while remaining:
            chosen = min(remaining, key=lambda i: (
                depot_leg(i) if previous is None else leg(previous, i), identities[i]))
            nearest.append(chosen)
            remaining.remove(chosen)
            previous = chosen
        farthest = sorted(stable, key=lambda i: (-depot_leg(i), identities[i]))
        by_weight = sorted(stable, key=lambda i: (
            -float(rows[i].get("peso_kg") or 0), -float(rows[i].get("colli") or 0), identities[i]))
        urgency = sorted(stable, key=lambda i: (_urgency(rows[i]), identities[i]))
        # Urgency and stable business identity come before spatial starts. This
        # is independent of CSV/input order and reserves early service slots.
        seeds = [(urgency, 'balanced' if strategy == 'efficient' else None, False),
                 (nearest, None, True), (list(reversed(nearest)), None, True),
                 (stable, None, True), (farthest, None, True), (by_weight, None, True)]
        if points and len(points) > n:
            depot = points[0]
            sweep = sorted(stable, key=lambda i: (
                math.atan2(points[i + 1]["lat"] - depot["lat"],
                           (points[i + 1]["lon"] - depot["lon"]) *
                           math.cos(math.radians(depot["lat"]))), depot_leg(i), identities[i]))
            seeds.extend(((sweep, None, True), (list(reversed(sweep)), None, True)))
        seed_budget = min(limit, phase_start + max(1, phase_allowance * 35 // 100))
        seen = set()
        for seed_index, (order, construction, quick) in enumerate(seeds):
            signature = (tuple(order), construction, quick)
            if signature in seen:
                continue
            seen.add(signature)
            deadline = seed_budget
            routes, results = empty, (None,) * resource_count
            completed = True
            for index in order:
                if used >= deadline:
                    completed = False
                    break
                candidate = insert(index, routes, results, quick=quick or n > 60,
                                   deadline=deadline, construction=construction)
                if candidate is not None:
                    _, routes, results = candidate
                    # A valid partial construction may already serve more
                    # deliveries than the incumbent when its budget expires.
                    consider(routes, results)
            consider(routes, results)

        def rebuild(removed, deadline, *, focus=(), base=None):
            """Regret-2 reconstruction of a small neighbourhood, never a plan commit.

            Whole reconstruction states may be worse in coverage than the
            incumbent. Only the final valid state passes through consider().
            """
            removed = set(removed)
            base_routes, _ = base if base is not None else (best_routes, best_results)
            changed = tuple(tuple(i for i in order if i not in removed) for order in base_routes)
            scores = []
            for resource, order in enumerate(changed):
                score = replay(order, resource) if order else None
                if order and score is None:
                    return False
                scores.append(score)
            scores = tuple(scores)
            present = {i for order in changed for i in order}
            pending = set(stable) - present
            while pending and used < deadline:
                choice = None
                # Missing/removed urgent jobs first, but scarcity/regret can
                # select another job whose few feasible slots would disappear.
                candidates = sorted(pending, key=lambda i: (
                    i not in focus, not rows[i].get('sponda'), _urgency(rows[i]), identities[i]))
                for index in candidates[:8]:
                    alternatives = []
                    for resource in range(resource_count):
                        resource_best = None
                        for insertion in positions(changed[resource], index):
                            if used >= deadline:
                                break
                            order = changed[resource][:insertion] + (index,) + changed[resource][insertion:]
                            score = replay(order, resource)
                            if score is None:
                                continue
                            rr, ss = list(changed), list(scores)
                            rr[resource], ss[resource] = order, score
                            rank = plan_key(rr, ss)
                            proposal = (rank, resource, order, score)
                            if resource_best is None or _better(rank, resource_best[0]):
                                resource_best = proposal
                        if resource_best is not None:
                            alternatives.append(resource_best)
                        if used >= deadline:
                            break
                    if not alternatives:
                        continue
                    alternatives.sort(key=lambda item: item[0])
                    best = alternatives[0]
                    second = alternatives[min(1, len(alternatives) - 1)][0]
                    regret = tuple(-(b - a) for a, b in zip(best[0], second))
                    priority = (index not in focus, len(alternatives), regret,
                                _urgency(rows[index]), identities[index])
                    if choice is None or priority < choice[0]:
                        choice = (priority, index, best)
                if choice is None:
                    break
                _, index, (_, resource, order, score) = choice
                rr, ss = list(changed), list(scores)
                rr[resource], ss[resource] = order, score
                changed, scores = tuple(rr), tuple(ss)
                pending.remove(index)
            return consider(changed, scores)

        def ejection_repair(missing, deadline, *, base=None, depth=1):
            """Insert an unserved job, then relocate the single displaced job.

            Trying missing jobs first avoids spending the repair budget on
            arbitrary moves from resource zero. Each intermediate route and the
            complete repaired plan still pass through the full scheduler.
            """
            routes, results = base if base is not None else (best_routes, best_results)
            first_pass_end = deadline if not depth else used + max(1, (deadline-used)*2//3)
            frontiers = []
            resources = sorted(range(resource_count), key=lambda r: (
                penalty((missing,), r), len(routes[r]), r))
            for resource_number, resource in enumerate(resources):
                if used >= first_pass_end:
                    break
                resource_end = used + max(1, (first_pass_end-used)//(len(resources)-resource_number))
                order = routes[resource]
                # Different scarcity dimensions matter: interleave large parcel
                # loads, heavy loads and road neighbours rather than assuming
                # that a spatial neighbour frees the required capacity.
                by_parcels = sorted(order, key=lambda i: (
                    -float(rows[i].get('colli') or 0), identities[i]))
                by_weight_local = sorted(order, key=lambda i: (
                    -float(rows[i].get('peso_kg') or 0), identities[i]))
                nearby = sorted(order, key=lambda i: (
                    leg(missing, i) + leg(i, missing), identities[i]))
                displaced = list(dict.fromkeys(i for group in
                    zip_longest(by_parcels, by_weight_local, nearby)
                    for i in group if i is not None))
                for removed in displaced:
                    if used >= resource_end:
                        break
                    rest = tuple(i for i in order if i != removed)
                    winner = None
                    for position in positions(rest, missing):
                        if used >= resource_end:
                            break
                        changed_order = rest[:position] + (missing,) + rest[position:]
                        score = replay(changed_order, resource)
                        if score is not None and (winner is None or
                                _better(_route_key(score, strategy), _route_key(winner[1], strategy))):
                            winner = changed_order, score
                    if winner is None:
                        continue
                    rr, ss = list(routes), list(results)
                    rr[resource], ss[resource] = winner
                    rr, ss = tuple(rr), tuple(ss)
                    repaired = insert(removed, rr, ss, deadline=resource_end)
                    if repaired is not None and consider(repaired[1], repaired[2]):
                        return True
                    if depth:
                        frontiers.append((plan_key(rr, ss), resource, removed, rr, ss))
            # Keep another displacement as a working state even when the first
            # ejected stop cannot move directly. Only the COMPLETE chain may
            # replace the incumbent; no infeasible midpoint is ever accepted.
            frontiers.sort(key=lambda state: (state[0], identities[state[2]], state[3]))
            # Do not let four variants of the same vehicle consume every
            # continuation: scarce capacity can require a different vehicle.
            groups = {resource: [state for state in frontiers if state[1] == resource]
                      for resource in resources}
            continuations = [groups[resource][rank] for rank in range(2)
                             for resource in resources if len(groups[resource]) > rank]
            for index, (_, _, removed, rr, ss) in enumerate(continuations):
                if used >= deadline:
                    break
                branch_end = used + max(1, (deadline-used)//(len(continuations)-index))
                if ejection_repair(removed, branch_end, base=(rr, ss), depth=depth-1):
                    return True
            return False

        # A separate repair allowance cannot be consumed by kilometre polishing.
        # Reconstruct small groups around unserved urgent jobs rather than
        # repeatedly attempting the same single insertion at a local plateau.
        coverage_end = min(limit, max(used, phase_start + phase_allowance * 70 // 100))
        repair_attempts = 0
        while used < coverage_end:
            assigned = {i for order in best_routes for i in order}
            pending = [i for i in urgency if i not in assigned]
            if not pending:
                break
            before = best_key
            for missing in pending:
                direct = insert(missing, best_routes, best_results, deadline=coverage_end)
                if direct is not None:
                    consider(direct[1], direct[2])
            assigned = {i for order in best_routes for i in order}
            pending = [i for i in urgency if i not in assigned]
            if not pending or used >= coverage_end:
                break
            states = sorted(repair_population.values(), key=lambda state: state[0])
            if repair_attempts % 3 and states:
                _, repair_routes, repair_results = states[(repair_attempts // 3) % len(states)]
            else:
                repair_routes, repair_results = best_routes, best_results
            repair_assigned = {i for route in repair_routes for i in route}
            repair_pending = [i for i in urgency if i not in repair_assigned]
            target = repair_pending[repair_attempts % len(repair_pending)]
            # First repair a concrete missing job with a coordinated exchange.
            # This is particularly important when one vehicle is parcel-full
            # while another has spare room but cannot take the missing job.
            ejection_end = min(coverage_end, used + max(300, (coverage_end - used) // 2))
            if ejection_repair(target, ejection_end, base=(repair_routes, repair_results)):
                repair_attempts += 1
                continue
            if used >= coverage_end:
                break
            nearby = sorted(repair_assigned, key=lambda i: (
                leg(target, i) + leg(i, target), abs(_urgency(rows[i])[0] - _urgency(rows[target])[0])
                if _urgency(rows[i])[0] < math.inf and _urgency(rows[target])[0] < math.inf else math.inf,
                identities[i]))
            width = (2, 4, 6, 8)[repair_attempts % 4]
            removed = set(nearby[:width])
            if repair_attempts % 2:
                # Jobs at the beginning of each route can block early windows,
                # even if their coordinates are far from the unserved stop.
                # An early unserved appointment can need several initial jobs
                # moved together, even when those jobs are far apart on roads.
                removed.update(i for route in repair_routes for i in route[:3])
            attempt_end = min(coverage_end, used + max(200, (coverage_end - used) // 2))
            rebuild(removed, attempt_end, focus=(target,), base=(repair_routes, repair_results))
            repair_attempts += 1
            if not _better(best_key, before) and repair_attempts >= 8:
                break

        def internal_moves(order):
            def relocations():
                for source, index in enumerate(order):
                    rest = order[:source] + order[source + 1:]
                    for position in range(len(rest) + 1):
                        moved = rest[:position] + (index,) + rest[position:]
                        if moved != order:
                            yield moved
            def swaps():
                for left in range(len(order)):
                    for right in range(left + 1, len(order)):
                        moved = list(order)
                        moved[left], moved[right] = moved[right], moved[left]
                        yield tuple(moved)
            def reversals():
                for left in range(len(order)):
                    for right in range(left + 2, len(order)):
                        yield order[:left] + order[left:right + 1][::-1] + order[right + 1:]
            for group in zip_longest(relocations(), swaps(), reversals()):
                for moved in group:
                    if moved is not None:
                        yield moved

        # Best improvement in bounded rounds. A relocation can open capacity or
        # free a driver before inserting an unassigned, time-critical delivery.
        for round_index in range(4):
            if used >= limit:
                exhausted = True
                break
            routes, results, round_key = best_routes, best_results, best_key
            round_end = used + (limit - used) // (4 - round_index)
            internal_end = used + max(1, (round_end - used) // 3)
            assigned = {i for route in routes for i in route}
            pending = [i for i in range(n) if i not in assigned]
            for index in pending:
                candidate = insert(index, best_routes, best_results, deadline=internal_end)
                if candidate is not None:
                    consider(candidate[1], candidate[2])
            routes, results = best_routes, best_results
            assigned = {i for route in routes for i in route}
            pending = [i for i in range(n) if i not in assigned]
            # Optimize each route with relocations and swaps under the same
            # scheduler; do not import the single-route distance-only objective.
            for resource, order in enumerate(routes):
                if used >= internal_end:
                    break
                resource_end = used + max(1, (internal_end - used) // (resource_count - resource))
                for moved in internal_moves(order):
                    if used >= resource_end:
                        break
                    result = replay(moved, resource)
                    if result is not None:
                        changed_routes, changed_results = list(routes), list(results)
                        changed_routes[resource], changed_results[resource] = moved, result
                        consider(changed_routes, changed_results)
            # Exchange route tails atomically. This can undo geographically
            # crossed memberships without first accepting an infeasible
            # capacity/window midpoint or moving only one stop at a time.
            tail_end = used + max(1, (round_end - used) // 3)
            for left in range(resource_count):
                for right in range(left + 1, resource_count):
                    one, two = routes[left], routes[right]
                    cuts = [(a, b) for a in range(len(one) + 1)
                            for b in range(len(two) + 1)
                            if (a, b) not in ((len(one), len(two)), (0, 0))]
                    # Cheap directed connector costs only order the trials;
                    # every accepted candidate still uses full scheduling.
                    def connector(cut):
                        a, b = cut
                        return ((leg(one[a - 1], two[b]) if a and b < len(two) else 0)
                                + (leg(two[b - 1], one[a]) if b and a < len(one) else 0), cut)
                    cuts.sort(key=connector)
                    for a, b in cuts:
                        if used >= tail_end:
                            break
                        first, second = one[:a] + two[b:], two[:b] + one[a:]
                        first_result = replay(first, left) if first else None
                        if first and first_result is None:
                            continue
                        second_result = replay(second, right) if second else None
                        if second and second_result is None:
                            continue
                        rr, ss = list(routes), list(results)
                        rr[left], rr[right] = first, second
                        ss[left], ss[right] = first_result, second_result
                        consider(rr, ss)
                    if used >= tail_end:
                        break
                if used >= tail_end:
                    break
            relocation_end = used + max(1, (round_end - used) // 2)
            # Relocation across vehicles, plus an ejection repair before accepting
            # a neutral/worse move: useful when coverage needs two coordinated moves.
            for source, order in enumerate(routes):
                for position, index in enumerate(order):
                    if used >= relocation_end:
                        break
                    rest = order[:position] + order[position + 1:]
                    result = replay(rest, source) if rest else None
                    if rest and result is None:
                        continue
                    base_routes, base_results = list(routes), list(results)
                    base_routes[source], base_results[source] = rest, result
                    for target in range(resource_count):
                        if target == source:
                            continue
                        for insertion in positions(routes[target], index):
                            moved = routes[target][:insertion] + (index,) + routes[target][insertion:]
                            target_result = replay(moved, target)
                            if target_result is None:
                                continue
                            changed_routes, changed_results = base_routes[:], base_results[:]
                            changed_routes[target], changed_results[target] = moved, target_result
                            consider(changed_routes, changed_results)
                            for missing in pending:
                                repaired = insert(missing, tuple(changed_routes), tuple(changed_results),
                                                  quick=True, deadline=relocation_end)
                                if repaired is not None:
                                    consider(repaired[1], repaired[2])
                            if used >= relocation_end:
                                break
                        if used >= relocation_end:
                            break
            # Exchanges preserve route sizes and can fix geographic crossings,
            # scarce equipment and capacity packing without an infeasible midpoint.
            for left in range(resource_count):
                for right in range(left + 1, resource_count):
                    for a, first in enumerate(routes[left]):
                        for b, second in enumerate(routes[right]):
                            if used >= round_end:
                                break
                            one, two = list(routes[left]), list(routes[right])
                            one[a], two[b] = second, first
                            first_result = replay(tuple(one), left)
                            if first_result is None:
                                continue
                            second_result = replay(tuple(two), right)
                            if second_result is None:
                                continue
                            changed_routes, changed_results = list(routes), list(results)
                            changed_routes[left], changed_routes[right] = tuple(one), tuple(two)
                            changed_results[left], changed_results[right] = first_result, second_result
                            consider(changed_routes, changed_results)
                        if used >= round_end:
                            break
            if not _better(best_key, round_key):
                # A plateau is a reason to diversify the construction, not
                # proof that all coordinated assignments have been explored.
                assigned = [i for order in best_routes for i in order]
                if not assigned:
                    break
                anchor = stable[round_index % len(stable)]
                neighbours = sorted(assigned, key=lambda i: (
                    leg(anchor, i) + leg(i, anchor), identities[i]))
                rebuild(neighbours[:min(8, max(3, n // 8))], round_end)

        # Spend remaining deterministic budget on diverse small reconstructions.
        # Local minima may need several coordinated changes even at full
        # coverage. Completed candidates never replace a better incumbent.
        ruin_round = 0
        while used < limit and ruin_round < 12:
            assigned = {i for order in best_routes for i in order}
            if not assigned:
                break
            anchor = stable[(ruin_round * 7 + 3) % n]
            nearby = sorted(assigned, key=lambda i: (
                leg(anchor, i) + leg(i, anchor), identities[i]))
            width = min(len(assigned), (3, 5, 8)[ruin_round % 3])
            removed = set(nearby[:width])
            if ruin_round % 3 == 1:
                # Also try contiguous pieces rather than only spatial peers.
                route = best_routes[ruin_round % resource_count]
                start = (ruin_round * 3) % max(1, len(route))
                removed.update(route[start:start + 3])
            deadline = min(limit, used + max(200, (limit - used) // 2))
            before = used
            rebuild(removed, deadline)
            ruin_round += 1
            if used == before and ruin_round >= 6:
                break

    pool_diagnostics = None
    if not exact and limit:
        recombined, recombined_results, pool_diagnostics = pool.recombine(
            best_routes, best_results, plan_key, _better)
        consider(recombined, recombined_results)
    diagnostics = {
        "method": "exact-subsets" if exact else "bounded-adaptive-multistart",
        "additional_evaluations": used, "candidate_budget": None if exact else limit,
        "budget_exhausted": bool(not exact and (exhausted or used >= limit)),
        "global_optimum_proven": exact,
        "equipment_policy": "prefer-compatible-with-warning-fallback",
        "objective": "distance-then-work-time" if strategy == "efficient" else "balanced-workload",
        "construction": "stable-identity-and-urgent-windows",
        "membership_checks": membership_checks,
        "membership_rejections": membership_rejections,
    }
    if pool_diagnostics is not None:
        diagnostics['route_pool'] = pool_diagnostics
    if seed_diagnostics is not None:
        diagnostics['established_search_seed'] = seed_diagnostics
    return best_routes, best_results, diagnostics


def refine_routes(routes, results, evaluate, *, global_exact=False, prepare=None,
                  strategy='balanced'):
    """Find each <=8-stop route's best order with fixed membership and resource.

    This final pass is independent of the fleet heuristic candidate budget.
    Larger routes retain their existing heuristic order. A fleet-wide optimum
    and an optimum within a chosen group are deliberately separate claims.
    """
    routes = tuple(tuple(order) for order in routes)
    refined, scores = list(routes), list(results)
    details, evaluations = [], 0
    for resource, order in enumerate(routes):
        size = len(order)
        info = {"resource": resource, "stops": size, "evaluations": 0,
                "scope": "fixed-membership-and-resource", "improved": False,
                "order_optimum_proven": False}
        if not order:
            info["method"] = "empty"
        elif size > 8:
            info["method"] = "existing-heuristic"
        elif global_exact and scores[resource] is not None:
            info.update(method="global-exact-reuse", order_optimum_proven=True)
        else:
            score = prepare(order, resource) if prepare is not None else (
                lambda candidate, r=resource: evaluate(candidate, r))
            best_order, best_result = order, scores[resource]
            initial = best_result
            for candidate in permutations(order):
                result = score(candidate)
                info["evaluations"] += 1
                if result is not None and (best_result is None or
                                          _better(_route_key(result, strategy), _route_key(best_result, strategy))):
                    best_order, best_result = candidate, result
            info["method"] = "exact-permutations"
            # Verify compiled scoring against the canonical evaluator. An
            # unexpected discrepancy falls back to a complete canonical pass.
            if prepare is not None:
                verified = evaluate(best_order, resource) if best_result is not None else None
                info["canonical_verifications"] = int(best_result is not None)
                agrees = (verified is not None and best_result is not None
                          and not _better(_route_key(verified, strategy), _route_key(best_result, strategy))
                          and not _better(_route_key(best_result, strategy), _route_key(verified, strategy)))
                if agrees:
                    best_result = verified
                else:
                    best_order, best_result = order, initial
                    for candidate in permutations(order):
                        result = evaluate(candidate, resource)
                        info["evaluations"] += 1
                        if result is not None and (best_result is None or
                                                  _better(_route_key(result, strategy), _route_key(best_result, strategy))):
                            best_order, best_result = candidate, result
                    info["method"] = "exact-permutations-canonical-fallback"
                    info["canonical_fallback_evaluations"] = math.factorial(size)
            refined[resource], scores[resource] = best_order, best_result
            info["order_optimum_proven"] = best_result is not None
            info["all_orders_infeasible"] = best_result is None
            info["improved"] = (best_result is not None and (
                initial is None or _better(_route_key(best_result, strategy), _route_key(initial, strategy))))
        evaluations += info["evaluations"]
        details.append(info)
    return tuple(refined), tuple(scores), {
        "route_refinement": details, "exact_route_evaluations": evaluations}
