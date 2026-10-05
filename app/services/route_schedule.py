"""Shared operational schedule; GPS can later supply arrival estimates here.

Planned times roll forward across midnight. Operational timestamps in the
existing database are local wall times. Missing estimates remain unknown.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..core.config import LOCAL_TIMEZONE
from ..core.utils import minutes_from_hhmm

LOCAL = ZoneInfo(LOCAL_TIMEZONE)


def route_schedule_datetimes(plan, status_map=None, now=None):
    statuses = status_map or {}
    start_min = minutes_from_hhmm(plan.orario_partenza) or 0
    midnight = datetime.combine(plan.data_giro, datetime.min.time(), LOCAL)
    start = midnight + timedelta(minutes=start_min)
    cursor = start
    shift = timedelta()
    updated = None
    source = 'planned'
    started = getattr(plan, 'started_at', None)
    if plan.status == 'in_corso' and started:
        updated = started.replace(tzinfo=LOCAL)
        shift = updated - start
        source = 'execution'
    deliveries = {}

    def next_time(value, after):
        minutes = minutes_from_hhmm(value)
        if minutes is None:
            return None
        result = midnight + timedelta(minutes=minutes)
        while result < after:
            result += timedelta(days=1)
        return result

    for delivery in sorted(plan.deliveries or [], key=lambda d: (d.ordine or 0, d.id or 0)):
        arrival = next_time(delivery.arrivo_stimato, cursor)
        departure = next_time(delivery.partenza_stimata or delivery.arrivo_stimato, arrival or cursor)
        ds = statuses.get(delivery.id)
        closed = ds and ds.status in ('completata', 'mancata') and ds.completata_il
        if closed:
            actual = ds.completata_il.replace(tzinfo=LOCAL)
            deliveries[delivery.id] = {'arrival': actual, 'source': 'execution', 'updated_at': actual}
            if departure:
                shift = actual - departure
                source, updated = 'execution', actual
        else:
            deliveries[delivery.id] = {'arrival': arrival + shift if arrival else None,
                                       'source': source, 'updated_at': updated}
        cursor = departure or arrival or cursor
    returned = next_time(plan.orario_rientro_stimato, cursor)
    if returned is None:
        returned = start + timedelta(minutes=float(plan.totale_minuti or 0))
    result = {'deliveries': deliveries, 'return_at': returned + shift}
    _apply_gps(plan, statuses, result, now or datetime.now(LOCAL))
    return result


def _apply_gps(plan, statuses, result, now):
    """Read only projection: reuse the cached next-stop ETA, never call routing."""
    if plan.status != 'in_corso':
        return
    position = getattr(plan, 'position', None)
    if not position or position.driver_id != plan.driver_id or not position.eta_at:
        return
    utc = now.astimezone(timezone.utc).replace(tzinfo=None)
    if not 0 <= (utc - position.captured_at).total_seconds() <= 90:
        return
    if not position.eta_calculated_at or not 0 <= (utc - position.eta_calculated_at).total_seconds() <= 150:
        return
    pending = [d for d in sorted(plan.deliveries, key=lambda d: (d.ordine or 0, d.id))
               if not statuses.get(d.id) or statuses[d.id].status not in ('completata', 'mancata')]
    if not pending or pending[0].id != position.eta_delivery_id:
        return
    arrival = position.eta_at.replace(tzinfo=timezone.utc).astimezone(LOCAL)
    # A passed prediction is not made live again by a more recent GPS upload.
    if arrival <= now:
        return
    updated = position.eta_calculated_at.replace(tzinfo=timezone.utc).astimezone(LOCAL)
    last_old = last_new = None
    for index, delivery in enumerate(pending):
        if index:
            # Use persisted legs, excluding waits so opening times are applied below.
            minutes = delivery.minuti_tappa
            if minutes is None:
                break
            arrival += timedelta(minutes=max(0, float(minutes)))
        windows = []
        for prefix in ('scarico_mattina', 'scarico_pomeriggio'):
            opening, closing = getattr(delivery, prefix + '_da'), getattr(delivery, prefix + '_a')
            if opening and closing:
                start = datetime.combine(arrival.date(), opening, LOCAL)
                end = datetime.combine(arrival.date(), closing, LOCAL)
                if end < start:
                    end += timedelta(days=1)
                windows.append((start, end))
        if windows:
            feasible = [max(arrival, start) for start, end in windows if max(arrival, start) <= end]
            if not feasible:
                # The remaining schedule is no longer feasible: avoid a GPS promise.
                for rest in pending[index:]:
                    result['deliveries'][rest.id] = {'arrival': None, 'source': None, 'updated_at': updated}
                break
            arrival = min(feasible)
        last_old = result['deliveries'][delivery.id]['arrival']
        last_new = arrival
        result['deliveries'][delivery.id] = {'arrival': arrival, 'source': 'gps', 'updated_at': updated}
        arrival += timedelta(minutes=max(0, delivery.tempo_scarico_min or 0))
    if last_old and last_new:
        result['return_at'] += last_new - last_old


def live_route_schedule(plan, status_map=None):
    schedule = route_schedule_datetimes(plan, status_map)
    return {
        'delivery_times': {key: row['arrival'].strftime('%H:%M') if row['arrival'] else None
                           for key, row in schedule['deliveries'].items()},
        'rientro_stimato_aggiornato': schedule['return_at'].strftime('%H:%M'),
    }
