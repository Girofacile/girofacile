"""Independent, exhaustive reference for bounded fleet-quality experiments.

This module deliberately imports no application code. Times are absolute local
minutes within one day; matrices are directed and index 0 is the depot. Delivery
indices used by callers are zero-based and map to matrix indices index + 1.
"""
from itertools import permutations, product
import math

_EPS = 1e-9


def _minute(value):
    if hasattr(value, "hour"):
        return value.hour * 60 + value.minute
    hour, minute = str(value).split(":")[:2]
    return int(hour) * 60 + int(minute)


def _flag(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "si", "sì", "yes", "y", "vero"}


def _pauses(resource):
    return sorted(
        (_minute(pause["start"]), _minute(pause["end"]))
        for pause in (resource.get("driver_schedule") or {}).get("breaks", [])
    )


def _drive(start, work, pauses):
    """Consume driving work only in the complement of fixed break intervals."""
    cursor = float(start)
    remaining = float(work)
    for opening, closing in pauses:
        if closing <= cursor:
            continue
        free = max(0.0, opening - cursor)
        if cursor <= opening and remaining <= free:
            return cursor + remaining
        remaining -= free
        cursor = closing
    return cursor + remaining


def _service(start, duration, pauses):
    """Find an uninterrupted unloading interval, including the zero-work rule."""
    cursor = float(start)
    for opening, closing in pauses:
        intersects = cursor < closing and (
            cursor >= opening or cursor + duration > opening
        )
        if intersects:
            cursor = float(closing)
    return cursor


def _windows(stop):
    windows = []
    for prefix in ("scarico_mattina", "scarico_pomeriggio"):
        opening, closing = stop.get(prefix + "_da"), stop.get(prefix + "_a")
        if opening and closing:
            windows.append((_minute(opening), _minute(closing)))
    return sorted(windows)


def route_replay(case, resource, order):
    """Replay one ordered route independently of the production scheduler."""
    settings = case["resources"][resource] if isinstance(resource, int) else resource
    start = float(case.get("start_min", 480))
    result = {
        "feasible": True, "errors": [], "km": 0.0, "minutes": 0.0,
        "end": start, "wait_min": 0.0, "drive_min": 0.0,
        "break_drive_min": 0.0, "mismatches": 0, "timings": [],
    }
    if not order:
        return result
    if len(order) != len(set(order)):
        result["errors"].append("duplicate_stop")
    if any(not isinstance(index, int) or index < 0 or index >= len(case["stops"]) for index in order):
        result["errors"].append("invalid_stop")
        result["feasible"] = False
        return result
    stops = [case["stops"][index] for index in order]
    for field, quantity in (("capacita_kg", "peso_kg"), ("capacita_colli", "colli")):
        capacity = settings.get(field)
        if capacity is not None and sum(float(stop.get(quantity) or 0) for stop in stops) > float(capacity) + _EPS:
            result["errors"].append(field)
    pauses = _pauses(settings)
    cursor, origin = start, 0

    def travel(destination):
        nonlocal cursor, origin
        leg = case["matrix"][(origin, destination)]
        drive = float(leg["min"])
        arrived = _drive(cursor, drive, pauses)
        result["km"] += float(leg["km"])
        result["drive_min"] += drive
        result["break_drive_min"] += arrived - cursor - drive
        cursor, origin = arrived, destination

    for index, stop in zip(order, stops):
        travel(index + 1)
        arrival = cursor
        duration = float(stop.get("tempo_scarico_min") or 0)
        windows = _windows(stop)
        choices = []
        for opening, closing in windows or [(float("-inf"), float("inf"))]:
            ready = _service(max(arrival, opening), duration, pauses)
            if ready + duration <= closing + _EPS:
                choices.append(ready)
        if choices:
            ready = min(choices)
        else:
            result["errors"].append("window:" + str(index))
            ready = _service(arrival, duration, pauses)
        wait = ready - arrival
        cursor = ready + duration
        result["wait_min"] += wait
        result["mismatches"] += int(_flag(stop.get("sponda")) and not _flag(settings.get("ha_sponda")))
        result["mismatches"] += int(_flag(stop.get("ztl")) and not _flag(settings.get("accesso_ztl")))
        result["timings"].append({
            "index": index, "arrival": arrival, "service_start": ready,
            "service_end": cursor, "wait": wait,
        })
    if case.get("return_depot", True):
        travel(0)
    result["end"] = cursor
    result["minutes"] = cursor - start
    schedule = settings.get("driver_schedule") or {}
    if schedule.get("start") and (
        start < _minute(schedule["start"]) - _EPS
        or cursor > _minute(schedule["end"]) + _EPS
    ):
        result["errors"].append("shift")
    maximum = float(settings.get("max_minutes", 1440))
    available = settings.get("available_minutes")
    if available is not None:
        maximum = min(maximum, float(available))
    if math.ceil(result["minutes"] - _EPS) > maximum:
        result["errors"].append("duration")
    result["feasible"] = not result["errors"]
    return result


def _aggregate(orders, routes, extra_errors=()):
    durations = [route["minutes"] for route in routes]
    return {
        "served": len(set(index for order in orders for index in order)),
        "mismatches": sum(route["mismatches"] for route in routes),
        "used": sum(bool(order) for order in orders),
        "km": sum(route["km"] for route in routes),
        "minutes": sum(durations),
        "makespan": max(durations, default=0),
        "sumsq": sum(duration * duration for duration in durations),
        "orders": [list(order) for order in orders],
        "feasible": not extra_errors and all(route["feasible"] for route in routes),
    }


def plan_metrics(case, orders):
    """Aggregate orders by resource; missing trailing resources mean empty routes."""
    resource_count = len(case["resources"])
    normalized = [list(order) for order in orders]
    extra_errors = []
    if len(normalized) > resource_count:
        extra_errors.append("extra_resources")
    normalized += [[] for _ in range(max(0, resource_count - len(normalized)))]
    flat = [index for order in normalized for index in order]
    if len(flat) != len(set(flat)):
        extra_errors.append("duplicate_stop")
    routes = [route_replay(case, resource, order) for resource, order in enumerate(normalized[:resource_count])]
    metrics = _aggregate(normalized[:resource_count], routes, extra_errors)
    metrics["served"] = len({index for order in normalized[:resource_count] for index in order
                             if isinstance(index, int) and 0 <= index < len(case["stops"])})
    return metrics


def _key(kind, metrics):
    common = (-metrics["served"], metrics["mismatches"])
    if kind == "km":
        return common + (metrics["km"], metrics["minutes"], metrics["used"])
    if kind == "time":
        return common + (metrics["minutes"], metrics["km"], metrics["used"])
    if kind == "efficient":
        return common + (metrics["used"], metrics["minutes"], metrics["km"])
    return common + (
        -metrics["used"], metrics["makespan"], metrics["sumsq"],
        metrics["minutes"], metrics["km"],
    )


def solve_exact(case):
    """Enumerate every subset order and every assignment, including unassigned.

    Bounded to seven stops and three resources. "balanced" here is a transparent
    global comparison objective, not a claim that the product implements it.
    """
    n, resource_count = len(case["stops"]), len(case["resources"])
    if n > 7 or resource_count > 3 or resource_count < 1:
        raise ValueError("Exact fleet reference supports at most 7 stops and 1–3 resources")
    subset_routes = []
    for resource in range(resource_count):
        choices = {}
        for mask in range(1 << n):
            members = tuple(index for index in range(n) if mask & (1 << index))
            best_km = best_time = None
            for order in permutations(members):
                replay = route_replay(case, resource, order)
                if not replay["feasible"]:
                    continue
                km_key = (replay["mismatches"], replay["km"], replay["minutes"])
                time_key = (replay["mismatches"], replay["minutes"], replay["km"])
                if best_km is None or km_key < best_km[0]:
                    best_km = (km_key, order, replay)
                if best_time is None or time_key < best_time[0]:
                    best_time = (time_key, order, replay)
            choices[mask] = {"km": best_km, "time": best_time}
        subset_routes.append(choices)
    best = {kind: None for kind in ("km", "time", "efficient", "balanced")}
    for assignment in product(range(-1, resource_count), repeat=n):
        masks = [0] * resource_count
        for index, resource in enumerate(assignment):
            if resource >= 0:
                masks[resource] |= 1 << index
        for kind in best:
            preference = "km" if kind == "km" else "time"
            selected = [subset_routes[resource][mask][preference] for resource, mask in enumerate(masks)]
            if any(route is None for route in selected):
                continue
            metrics = _aggregate(
                [route[1] for route in selected], [route[2] for route in selected]
            )
            if best[kind] is None or _key(kind, metrics) < _key(kind, best[kind]):
                best[kind] = metrics
    return best
