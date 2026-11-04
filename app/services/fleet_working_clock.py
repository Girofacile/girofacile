"""Specialized vehicle routing on one frozen matrix and exact fixed-break calendars.

Each vehicle has a compressed working clock: its declared fixed breaks are
removed from the wall clock. Interrupted driving is consequently additive;
service-start domains exclude breaks and ensure unloading remains contiguous.
Every returned route is replayed by the application's canonical evaluator.
The specialized search proposes candidates, never a global-optimality claim.
"""
from __future__ import annotations

import math

TIME_SCALE = 1_000_000  # millionths of a minute; <0.006s accumulated on 100 legs
WEIGHT_SCALE = 1_000_000
DISTANCE_SCALE = 1_000_000


def _ceil(value, scale=TIME_SCALE):
    return int(math.ceil(float(value) * scale))


def _floor(value, scale=TIME_SCALE):
    return int(math.floor(float(value) * scale))


def working_clock(clock, pauses, start=0):
    """Elapsed non-break minutes from the common departure to ``clock``."""
    def elapsed(value):
        return float(value) - sum(max(0.0, min(float(value), b) - a)
                                  for a, b in pauses if value > a)
    return elapsed(clock) - elapsed(start)


def service_domains(row, vehicle, start, available_minutes):
    """Conservative integer service-start intervals in a vehicle's work clock.

    A service must fit one customer window and one uninterrupted working spell.
    The original calendar permits driving to pause and resume, not unloading.
    """
    from .. import optimizer as opt
    from . import driver_schedule as shifts

    start = opt.vehicle_start_clock(start, vehicle)
    schedule = vehicle.get('driver_schedule') or {}
    if schedule.get('start') and start < shifts.minutes(schedule['start']):
        return (), 0
    horizon = min(1440.0, start + math.floor(float(available_minutes)))
    if schedule.get('end'):
        horizon = min(horizon, shifts.minutes(schedule['end']))
    if horizon < start:
        return (), 0
    pauses = shifts.intervals(schedule)
    service = float(row.get('tempo_scarico_min') or 0)
    windows = opt.delivery_windows(row) or [(start, horizon)]
    spells, cursor = [], float(start)
    for opening, closing in pauses:
        if closing <= cursor:
            continue
        if opening > horizon:
            break
        if opening > cursor:
            spells.append((cursor, min(float(opening), horizon), True))
        cursor = max(cursor, float(closing))
    if cursor <= horizon:
        spells.append((cursor, horizon, False))
    result = []
    for beginning, ending, before_pause in spells:
        for opening, closing in windows:
            lo = max(beginning, float(opening), float(start))
            hi = min(ending, float(closing), horizon) - service
            # service_ready() pushes even zero-duration service at break start
            # to the break end. A positive service may finish at break start.
            if service == 0 and before_pause and hi >= ending:
                hi = ending - 1 / TIME_SCALE
            if hi < lo:
                continue
            low = _ceil(working_clock(lo, pauses, start))
            high = _floor(working_clock(hi, pauses, start))
            if low <= high:
                result.append((low, high))
    result.sort()
    merged = []
    for lo, hi in result:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = merged[-1][0], max(merged[-1][1], hi)
        else:
            merged.append((lo, hi))
    return tuple(merged), max(0, _floor(working_clock(horizon, pauses, start)))


def _compatible(row, vehicle):
    """Check blocking load limits; equipment differences remain advisory."""
    return all(vehicle.get(capacity) is None or float(row.get(demand) or 0) <= float(vehicle[capacity])
               for demand, capacity in (('peso_kg', 'capacita_kg'), ('colli', 'capacita_colli')))


def _plan_key(routes, results, rows, vehicles, strategy):
    distances, durations = [], []
    for score in results:
        raw = score.get('_objective') if score else None
        distances.append(float(raw[0] if raw else score['total_km']) if score else 0.0)
        durations.append(float(raw[1] if raw else score['total_min']) if score else 0.0)
    mismatches = sum(
        int(bool(rows[i].get('sponda')) and not vehicles[v].get('ha_sponda', False))
        + int(bool(rows[i].get('ztl')) and not vehicles[v].get('accesso_ztl', False))
        for v, order in enumerate(routes) for i in order)
    common = (-sum(map(len, routes)), mismatches)
    used = sum(bool(order) for order in routes)
    if strategy == 'balanced':
        return common + (-used, max(durations, default=0), sum(t*t for t in durations),
                         sum(durations), sum(distances))
    return common + (sum(distances), sum(durations), used)

