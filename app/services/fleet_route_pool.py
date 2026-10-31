"""Bounded recombination of resource-specific, canonically feasible routes.

The pool never invents an itinerary or calls a road/traffic provider. It combines
routes already accepted by the caller's full scheduler, retaining their vehicle
and driver identity. Its beam is a heuristic over that finite candidate pool;
it is not a global optimality certificate for the delivery problem.
"""
from copy import deepcopy
import math


def _mask(order, stop_count):
    value = 0
    for index in order:
        if type(index) is not int or not 0 <= index < stop_count:
            raise ValueError('Route pool stop index is outside the delivery set')
        bit = 1 << index
        if value & bit:
            raise ValueError('Route pool itinerary contains a duplicate delivery')
        value |= bit
    return value


def _distance_time(result):
    raw = result.get('_objective')
    values = (raw[0], raw[1]) if raw is not None else (
        result['total_km'], result['total_min'])
    values = tuple(float(value) for value in values)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError('Route pool requires finite nonnegative route metrics')
    return values


class RoutePool:
    """Keep diverse route memberships, separately for each real resource.

    ``route_key`` compares two orders with the SAME membership and resource.
    Efficient can use (distance, duration); workload balancing can use
    (duration, distance). The callback must match the fleet objective and its
    per-route monotone dominance rule.
    """

    def __init__(self, resource_count, stop_count, *, max_options=48, route_key=None):
        if resource_count < 0 or stop_count < 0 or max_options < 1:
            raise ValueError('Route pool sizes must be nonnegative and options positive')
        self.resource_count = resource_count
        self.stop_count = stop_count
        self.max_options = int(max_options)
        self.route_key = route_key or _distance_time
        self._entries = [{} for _ in range(resource_count)]
        self.accepted = 0

    def _key(self, result):
        # Independently validate physical totals even with a custom sort key.
        _distance_time(result)
        key = tuple(float(value) for value in self.route_key(result))
        if any(not math.isfinite(value) for value in key):
            raise ValueError('Route pool sort key must contain finite numbers')
        return key

    def add(self, resource, order, result):
        """Record only a route already checked by the canonical scheduler.

        A missing/explicitly infeasible result is ignored. Empty routes are
        built into recombination and do not consume candidate storage.
        """
        if type(resource) is not int or not 0 <= resource < self.resource_count:
            raise ValueError('Route pool resource index is invalid')
        order = tuple(order)
        mask = _mask(order, self.stop_count)
        if not order or result is None:
            return False
        if result.get('violations', 0) or result.get('feasible') is False:
            return False
        rank = self._key(result)
        old = self._entries[resource].get(mask)
        if old is not None and (rank, order) >= (old[3], old[1]):
            return False
        self._entries[resource][mask] = (mask, order, deepcopy(result), rank)
        self.accepted += 1
        # Amortize diversity selection instead of doing a quadratic selection
        # after every feasible route replay. Storage is still strictly bounded.
        if len(self._entries[resource]) > 2 * self.max_options:
            selected = self._select(self._entries[resource].values())
            self._entries[resource] = {item[0]: item for item in selected}
        return True

    def _select(self, candidates):
        candidates = list(candidates)
        if len(candidates) <= self.max_options:
            return sorted(candidates, key=lambda item: (-item[0].bit_count(), item[3], item[1]))
        selected, chosen = [], set()

        def take(items, maximum):
            for item in items:
                if len(selected) >= maximum:
                    break
                if item[0] not in chosen:
                    selected.append(item)
                    chosen.add(item[0])

        # Keep high-coverage routes, representatives of different route sizes,
        # cheap routes per served delivery, and distinct memberships. Retaining
        # only the cheapest absolute route would erase useful full-load plans.
        coverage = sorted(candidates, key=lambda item: (-item[0].bit_count(), item[3], item[1]))
        take(coverage, max(1, self.max_options // 4))
        by_size = {}
        for item in candidates:
            size = item[0].bit_count()
            if size not in by_size or (item[3], item[1]) < (by_size[size][3], by_size[size][1]):
                by_size[size] = item
        take((by_size[size] for size in sorted(by_size, reverse=True)),
             max(1, self.max_options // 2))
        efficient = sorted(candidates, key=lambda item: (
            tuple(value / item[0].bit_count() for value in item[3]), item[3], item[1]))
        take(efficient, max(1, 3 * self.max_options // 4))
        while len(selected) < self.max_options:
            remaining = [item for item in candidates if item[0] not in chosen]
            winner = min(remaining, key=lambda item: (
                -min((item[0] ^ other[0]).bit_count() for other in selected), item[3], item[1]))
            selected.append(winner)
            chosen.add(winner[0])
        return sorted(selected, key=lambda item: (-item[0].bit_count(), item[3], item[1]))

    def recombine(self, initial_routes, initial_results, plan_key, better, *,
                  beam_width=64, max_states=5000):
        """Return the best valid incumbent or an improvement assembled from pool.

        ``plan_key`` compares full resource-indexed plans with coverage first.
        State expansion has a deterministic quota for each resource depth, so
        a large early layer cannot consume all work before complete plans exist.
        No dominance pruning silently assumes that a lower partial makespan
        remains better after adding future routes.
        """
        initial_routes = tuple(tuple(order) for order in initial_routes)
        initial_results = tuple(initial_results)
        if len(initial_routes) != self.resource_count or len(initial_results) != self.resource_count:
            raise ValueError('Route pool incumbent needs one route and result per resource')
        initial_mask = 0
        for order, result in zip(initial_routes, initial_results):
            mask = _mask(order, self.stop_count)
            if initial_mask & mask:
                raise ValueError('Route pool incumbent duplicates a delivery across resources')
            if order and (result is None or result.get('violations', 0) or result.get('feasible') is False):
                raise ValueError('Route pool incumbent must be canonically feasible')
            if order:
                self._key(result)
            initial_mask |= mask
        beam_width, max_states = max(1, int(beam_width)), max(0, int(max_states))
        best_routes, best_results = initial_routes, initial_results
        best_rank = plan_key(best_routes, best_results)
        best_served = initial_mask.bit_count()
        generated = checked = completed = 0
        truncated = False
        options = []
        for resource in range(self.resource_count):
            selected = self._select(self._entries[resource].values())
            incumbent = initial_routes[resource]
            if incumbent:
                mask = _mask(incumbent, self.stop_count)
                original = (mask, incumbent, deepcopy(initial_results[resource]),
                            self._key(initial_results[resource]))
                recorded = self._entries[resource].get(mask)
                if recorded is not None and (recorded[3], recorded[1]) < (original[3], original[1]):
                    original = recorded
                selected = [item for item in selected if item[0] != mask]
                selected.append(original)
            selected.append((0, (), None, (0.0, 0.0)))
            options.append(sorted(selected, key=lambda item: (-item[0].bit_count(), item[3], item[1])))
        # Most restricted resource first; route/resource arrays remain in their
        # original identity order for the callback and final output.
        resource_order = sorted(range(self.resource_count), key=lambda i: (len(options[i]), i))
        remaining_unions = [0] * (len(resource_order) + 1)
        for depth in range(len(resource_order) - 1, -1, -1):
            union = remaining_unions[depth + 1]
            for mask, *_ in options[resource_order[depth]]:
                union |= mask
            remaining_unions[depth] = union
        empty = tuple(() for _ in range(self.resource_count))
        beam = [(0, empty, (None,) * self.resource_count)]
        if max_states < self.resource_count:
            truncated = bool(self.resource_count)
            beam = []
        for depth, resource in enumerate(resource_order):
            if not beam:
                break
            allowance = max(1, (max_states - generated) // (self.resource_count - depth))
            proposed = []
            reached_quota = False
            for mask, routes, results in beam:
                for option_mask, order, result, _ in options[resource]:
                    checked += 1
                    if mask & option_mask:
                        continue
                    covered = mask | option_mask
                    # This is only a coverage upper bound, not a distance or
                    # scheduling feasibility bound.
                    if (covered | remaining_unions[depth + 1]).bit_count() < best_served:
                        continue
                    changed_routes, changed_results = list(routes), list(results)
                    changed_routes[resource], changed_results[resource] = order, result
                    changed_routes, changed_results = tuple(changed_routes), tuple(changed_results)
                    rank = plan_key(changed_routes, changed_results)
                    generated += 1
                    if better(rank, best_rank):
                        best_routes, best_results, best_rank = changed_routes, changed_results, rank
                        best_served = covered.bit_count()
                    proposed.append((covered, changed_routes, changed_results))
                    if depth == self.resource_count - 1:
                        completed += 1
                    if len(proposed) >= allowance:
                        reached_quota = True
                        break
                if reached_quota:
                    break
            proposed.sort(key=lambda state: (
                -(state[0] | remaining_unions[depth + 1]).bit_count(),
                plan_key(state[1], state[2]), state[1]))
            if len(proposed) > beam_width or reached_quota:
                truncated = True
            beam = proposed[:beam_width]
        diagnostics = dict(method='bounded-route-pool', scope='candidate-pool-only',
            global_optimum_proven=False, generated_states=generated,
            max_states=max_states, beam_width=beam_width, option_checks=checked,
            complete_candidates=completed, truncated=truncated,
            options_per_resource=[len(items) - 1 for items in options],
            improved=bool(better(best_rank, plan_key(initial_routes, initial_results))))
        return best_routes, tuple(deepcopy(result) for result in best_results), diagnostics
