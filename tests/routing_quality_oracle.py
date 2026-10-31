"""Independent, deliberately small reference for the October routing audit.

This module imports no application code or historical benchmark helper. It
models declared, fixed breaks: travel may resume after a break; unloading may
not overlap one. A delivery must finish inside one of its same-day windows.
The exhaustive fleet reference includes leaving stops unassigned and compares
the two commercial strategies separately. References are for frozen matrices,
not predictions of live road traffic.
"""
from itertools import permutations
import math


def _minute(value):
    if hasattr(value, 'hour'):
        return value.hour * 60 + value.minute
    hour, minute = str(value).split(':')[:2]
    return int(hour) * 60 + int(minute)


def _windows(stop):
    result = []
    for period in ('mattina', 'pomeriggio'):
        opening = stop.get(f'scarico_{period}_da')
        closing = stop.get(f'scarico_{period}_a')
        if opening is not None and closing is not None:
            left, right = _minute(opening), _minute(closing)
            if right > left:
                result.append((left, right))
    return sorted(result)


def _truth(value):
    if isinstance(value, bool):
        return value
    return str(value or '').strip().lower() in {'1', 'true', 'si', 'sì', 'yes', 'y', 'vero'}


def _travel(start, duration, breaks):
    """Integrate active driving time over the complement of fixed rest periods."""
    remaining, clock = float(duration), float(start)
    for left, right in breaks:
        if clock >= right:
            continue
        active = max(0.0, left - clock)
        if remaining <= active and clock <= left:
            return clock + remaining
        remaining -= active
        clock = right
    return clock + remaining


def _service_start(earliest, duration, breaks):
    """Find the first uninterrupted working interval of the requested length."""
    clock = earliest
    for left, right in breaks:
        if clock < right and (left <= clock or clock + duration > left):
            clock = right
    return clock


def _opening_warning(arrival, duration, windows, breaks):
    """Distinguish waiting for an opening from waiting for declared rest.

    When rest displaces an otherwise usable earlier opening, the new readiness
    bound may already equal the later opening. That is not an additional
    opening warning, even though the route still contains the complete wait.
    This affects only the last, diagnostic tie-break; the schedule above is
    computed directly from uninterrupted working intervals.
    """
    ready = arrival
    for _ in range(len(breaks) + 2):
        starts = [(max(ready, left), right) for left, right in windows
                  if max(ready, left) + duration <= right]
        if not starts:
            return True
        candidate, _ = min(starts)
        working = _service_start(candidate, duration, breaks)
        if working == candidate:
            return candidate > ready
        ready = working
    raise AssertionError('Finite fixed breaks failed to converge')


def _stop_timing(arrival, stop, breaks):
    service = float(stop.get('tempo_scarico_min') or 0)
    windows = _windows(stop)
    if not windows:
        start = _service_start(arrival, service, breaks)
        return start, None, 0.0, False
    # For a fixed visit order, earlier feasible completion dominates later
    # completion because driving through fixed breaks is FIFO.
    candidates = []
    for opening, closing in windows:
        initial = max(arrival, opening)
        start = _service_start(initial, service, breaks)
        if start + service <= closing:
            candidates.append((start, closing))
    if candidates:
        start, closing = min(candidates)
        return start, closing, 0.0, _opening_warning(arrival, service, windows, breaks)
    # Diagnostics for an infeasible route are intentionally not a reproduction
    # of the application's historical weighted score. Exact single references
    # certify feasibility/distance only when at least one feasible route exists.
    failed = []
    for opening, closing in windows:
        start = _service_start(max(arrival, opening), service, breaks)
        failed.append((max(0.0, start + service - closing), start, closing))
    late, start, closing = min(failed)
    return start, closing, late, True


def replay(case, resource_index, order):
    """Replay one zero-based stop order without touching the supplied input.

    ``max_minutes`` denotes the already computed available booking/day horizon
    for fleet planning. It is not a single-route setting. Set
    ``enforce_availability`` explicitly to use it on an isolated reference.
    """
    order = tuple(order)
    if len(set(order)) != len(order):
        raise ValueError('A route cannot contain the same stop twice')
    if any(not isinstance(i, int) or not 0 <= i < len(case['stops']) for i in order):
        raise ValueError('Stop index is outside the supplied case')
    resource = case['resources'][resource_index]
    started = _minute(case.get('start_time', '08:00'))
    result = dict(order=order, feasible=True, violations=0, km=0.0,
                  minutes=0.0, wait=0.0, lateness=0.0, mismatches=0,
                  warnings=0, stops=[], errors=[])
    if not order:
        return result
    schedule = resource.get('driver_schedule') or {}
    breaks = sorted((_minute(item['start']), _minute(item['end']))
                    for item in schedule.get('breaks', []))
    if any(right <= left for left, right in breaks):
        raise ValueError('Audit reference requires valid same-day breaks')
    rows = [case['stops'][i] for i in order]
    for field, stop_field in (('capacita_kg', 'peso_kg'), ('capacita_colli', 'colli')):
        load = sum(float(row.get(stop_field) or 0) for row in rows)
        cap = resource.get(field)
        if cap is not None and load > float(cap):
            result['errors'].append(field)
            result['violations'] += 1
    clock, previous = float(started), 0
    for index, row in zip(order, rows):
        node = int(row.get('customer_id') or index + 1)
        leg = case['matrix'][previous, node]
        km, duration = float(leg['km']), float(leg['min'])
        if not all(math.isfinite(value) and value >= 0 for value in (km, duration)):
            raise ValueError('Reference matrix must contain finite nonnegative legs')
        arrival = _travel(clock, duration, breaks)
        service_start, window_end, late, warning = _stop_timing(arrival, row, breaks)
        service_end = service_start + float(row.get('tempo_scarico_min') or 0)
        result['km'] += km
        result['wait'] += service_start - arrival
        result['lateness'] += late
        result['warnings'] += int(warning) + int(_truth(row.get('sponda')))
        result['violations'] += int(late > 0)
        result['mismatches'] += int(_truth(row.get('sponda')) and not _truth(resource.get('ha_sponda')))
        result['mismatches'] += int(_truth(row.get('ztl')) and not _truth(resource.get('accesso_ztl')))
        if case.get('hard_tail_lift') and _truth(row.get('sponda')) and not _truth(resource.get('ha_sponda')):
            result['violations'] += 1
            result['errors'].append('tail_lift_required')
        result['stops'].append(dict(index=index, arrival=arrival, service_start=service_start,
                                    service_end=service_end, window_end=window_end, lateness=late))
        previous, clock = node, service_end
    if case.get('return_depot', True):
        back = case['matrix'][previous, 0]
        result['km'] += float(back['km'])
        clock = _travel(clock, float(back['min']), breaks)
    result['minutes'] = clock - started
    if schedule.get('start') and (started < _minute(schedule['start']) or
                                  clock > _minute(schedule['end'])):
        result['violations'] += 1
        result['errors'].append('driver_shift')
    if case.get('kind') == 'fleet' or case.get('enforce_availability'):
        available = resource.get('max_minutes')
        if available is not None and math.ceil(result['minutes']) > available:
            result['violations'] += 1
            result['errors'].append('availability')
    result['feasible'] = result['violations'] == 0
    return result


def plan_metrics(case, orders):
    """Aggregate raw route totals and independently detect duplicate assignment."""
    orders = tuple(tuple(order) for order in orders)
    if len(orders) != len(case['resources']):
        raise ValueError('One route, possibly empty, is required per resource')
    routes = [replay(case, i, order) for i, order in enumerate(orders)]
    assigned = [index for order in orders for index in order]
    duplicates = len(assigned) - len(set(assigned))
    durations = [route['minutes'] for route in routes]
    return dict(served=len(set(assigned)), used=sum(bool(order) for order in orders),
                km=sum(route['km'] for route in routes), minutes=sum(durations),
                wait=sum(route['wait'] for route in routes),
                lateness=sum(route['lateness'] for route in routes),
                violations=sum(route['violations'] for route in routes) + duplicates,
                mismatches=sum(route['mismatches'] for route in routes),
                warnings=sum(route['warnings'] for route in routes),
                makespan=max(durations, default=0.0), sumsq=sum(value ** 2 for value in durations),
                feasible=not duplicates and all(route['feasible'] for route in routes),
                unassigned=tuple(sorted(set(range(len(case['stops']))) - set(assigned))),
                orders=orders, routes=routes)


def objective(metrics, strategy='single'):
    """Business priorities, without rounded presentation values or weights."""
    if strategy == 'single':
        if not metrics['feasible']:
            return (True, metrics['lateness'], metrics['violations'], metrics['km'], metrics['minutes'])
        return (False, metrics['km'], metrics['minutes'], metrics['wait'], metrics['warnings'])
    prefix = (-metrics['served'], metrics['mismatches'])
    if strategy == 'efficient':
        return (*prefix, metrics['km'], metrics['minutes'], metrics['used'])
    if strategy == 'balanced':
        return (*prefix, -metrics['used'], metrics['makespan'], metrics['sumsq'], metrics['minutes'], metrics['km'])
    raise ValueError('Unknown strategy')


def solve_single(case):
    """Enumerate every order, proving best feasible distance for up to 8 stops."""
    n = len(case['stops'])
    if n > 8:
        raise ValueError('Exhaustive single reference is limited to eight stops')
    best = None
    for order in permutations(range(n)):
        orders = (order,) + ((),) * (len(case['resources']) - 1)
        metrics = plan_metrics(case, orders)
        rank = objective(metrics, 'single')
        if best is None or rank < best['objective']:
            best = dict(orders=orders, metrics=metrics, objective=rank,
                        optimality_proven=metrics['feasible'], feasibility_proven=True)
    return best


def solve_fleet(case, strategy='efficient'):
    """Exhaust routes/subsets and their disjoint assignment to up to 3 resources.

    Each subset keeps its fastest feasible sequence (distance breaks ties).
    Both fleet objectives are monotone in every route duration, so that
    dominance preserves the complete optimum. Unassigned stops remain in the
    unused mask at the final resource. Only total weight/parcels, which are
    independent of visit order, prune subsets before enumerating their orders.
    Windows, pauses and shifts are always replayed on complete visit orders.
    """
    n, resources = len(case['stops']), len(case['resources'])
    if n > 8 or resources > 3:
        raise ValueError('Exhaustive fleet reference supports at most eight stops / three resources')
    options = []
    for resource_index in range(resources):
        choices = {0: ()}
        for mask in range(1, 1 << n):
            members = tuple(i for i in range(n) if mask & (1 << i))
            resource = case['resources'][resource_index]
            if any(resource.get(capacity) is not None and
                   sum(float(case['stops'][i].get(load) or 0) for i in members) > float(resource[capacity])
                   for capacity, load in (('capacita_kg', 'peso_kg'), ('capacita_colli', 'colli'))):
                continue
            best_order, best_rank = None, None
            for order in permutations(members):
                metrics = replay(case, resource_index, order)
                if metrics['feasible']:
                    rank = ((metrics['km'],metrics['minutes']) if strategy=='efficient'
                            else (metrics['minutes'], metrics['km']))
                    if best_rank is None or rank < best_rank:
                        best_order, best_rank = order, rank
            if best_order is not None:
                choices[mask] = best_order
        options.append(choices)
    best = None

    def assign(resource_index, remaining, orders):
        nonlocal best
        if resource_index == resources:
            metrics = plan_metrics(case, orders)
            rank = objective(metrics, strategy)
            if best is None or rank < best['objective']:
                best = dict(orders=orders, metrics=metrics, objective=rank,
                            optimality_proven=True, feasibility_proven=True)
            return
        subset = remaining
        while True:
            if subset in options[resource_index]:
                assign(resource_index + 1, remaining ^ subset, orders + (options[resource_index][subset],))
            if subset == 0:
                break
            subset = (subset - 1) & remaining

    assign(0, (1 << n) - 1, ())
    return best
