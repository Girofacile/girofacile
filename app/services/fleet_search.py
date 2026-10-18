"""Deterministic fleet-wide search on one immutable road matrix.

Geographic orders are flexible seeds, never territory constraints. Every accepted
route is replayed by the caller's scheduler (windows, unloading, breaks, shifts,
capacity and existing bookings). Equipment remains a preference, not a veto.
"""
from itertools import permutations, zip_longest
import math
import os


def candidate_limit(stop_count):
    default = min(20000, max(5000, 500000 // max(1, stop_count)))
    try:
        return max(0, min(100000, int(os.getenv("FLEET_MAX_CANDIDATES", str(default)))))
    except (TypeError, ValueError):
        return default


def _numbers(result):
    if result is None:
        return 0.0, 0.0
    raw = result.get("_objective")
    return (float(raw[1]), float(raw[0])) if raw else (
        float(result["total_min"]), float(result["total_km"]))


def optimize_fleet(rows, resource_count, evaluate, strategy, *,
                   initial_routes=None, initial_results=None, matrix=None,
                   points=None, equipment_penalty=None, resource_signatures=None,
                   return_depot=True):
    """Return resource-indexed stop sequences, evaluations and search diagnostics.

    Exhaustive subset/permutation search is restricted to <=7 stops/<=3 resources.
    Larger problems retain the complete existing insertion as a quality floor and
    use a deterministic additional evaluation budget, including all seed work.
    No wall-clock cut-off changes the result across repeated identical requests.
    """
    n = len(rows)
    penalty = equipment_penalty or (lambda sequence, resource: 0)
    empty = tuple(() for _ in range(resource_count))
    initial_routes = tuple(tuple(route) for route in (initial_routes or empty))
    initial_results = tuple(initial_results or (None,) * resource_count)
    aliases = list(range(resource_count))
    if resource_signatures:
        known = {}
        for resource, signature in enumerate(resource_signatures):
            aliases[resource] = known.setdefault(signature, resource)
    cache = {}
    used = 0
    limit = candidate_limit(n)
    exact = n <= 7 and resource_count <= 3
    exhausted = False

    def replay(sequence, resource):
        nonlocal used, exhausted
        if not sequence:
            return None
        key = (aliases[resource], tuple(sequence))
        if key in cache:
            return cache[key]
        if not exact and used >= limit:
            exhausted = True
            return None
        used += 1
        result = evaluate(tuple(sequence), resource)
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
        return common + (active, sum(durations), sum(distances))

    best_routes, best_results = initial_routes, initial_results
    best_key = plan_key(best_routes, best_results)

    def consider(routes, results):
        nonlocal best_routes, best_results, best_key
        key = plan_key(routes, results)
        if key < best_key:
            best_routes = tuple(tuple(route) for route in routes)
            best_results = tuple(results)
            best_key = key
            return True
        return False

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
                    duration, distance = _numbers(result)
                    key = (duration, distance)
                    if winner is None or key < winner[0]:
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
            return positions[:3] if quick else positions

        def insert(index, routes, results, *, quick=False, deadline=None):
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
                    if candidate_best is None or key < candidate_best[0]:
                        candidate_best = key, tuple(changed_routes), tuple(changed_results)
            return candidate_best

        # Flexible road-neighbour groups: no postcode, boundary or straight-line
        # membership can prevent a later feasible cross-zone move.
        remaining = set(range(n))
        nearest = []
        previous = None
        while remaining:
            chosen = min(remaining, key=lambda i: (
                depot_leg(i) if previous is None else leg(previous, i), i))
            nearest.append(chosen)
            remaining.remove(chosen)
            previous = chosen
        farthest = sorted(range(n), key=lambda i: (-depot_leg(i), i))
        by_weight = sorted(range(n), key=lambda i: (
            float(rows[i].get("peso_kg") or 0), float(rows[i].get("colli") or 0), i))
        seeds = [nearest, list(reversed(nearest)), farthest, by_weight]
        if points and len(points) > n:
            depot = points[0]
            sweep = sorted(range(n), key=lambda i: (
                math.atan2(points[i + 1]["lat"] - depot["lat"],
                           (points[i + 1]["lon"] - depot["lon"]) *
                           math.cos(math.radians(depot["lat"]))), depot_leg(i), i))
            seeds.extend((sweep, list(reversed(sweep))))
        seed_budget = limit // 2
        seen = set()
        for seed_index, order in enumerate(seeds):
            signature = tuple(order)
            if signature in seen:
                continue
            seen.add(signature)
            deadline = min(seed_budget, (seed_index + 1) * seed_budget // len(seeds))
            routes, results = empty, (None,) * resource_count
            completed = True
            for index in order:
                if used >= deadline:
                    completed = False
                    break
                candidate = insert(index, routes, results, quick=True, deadline=deadline)
                if candidate is not None:
                    _, routes, results = candidate
            if completed:
                consider(routes, results)

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
            if best_key >= round_key:
                break

    diagnostics = {
        "method": "exact-subsets" if exact else "bounded-geographic-multistart",
        "additional_evaluations": used, "candidate_budget": None if exact else limit,
        "budget_exhausted": bool(not exact and (exhausted or used >= limit)),
        "global_optimum_proven": exact,
        "equipment_policy": "prefer-compatible-with-warning-fallback",
    }
    return best_routes, best_results, diagnostics
