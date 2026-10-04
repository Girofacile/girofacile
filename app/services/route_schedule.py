"""Shared operational schedule; GPS can later supply arrival estimates here.

Planned times roll forward across midnight. Operational timestamps in the
existing database are local wall times. Missing estimates remain unknown.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..core.config import LOCAL_TIMEZONE
from ..core.utils import minutes_from_hhmm

LOCAL = ZoneInfo(LOCAL_TIMEZONE)


def route_schedule_datetimes(plan, status_map=None):
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
    return {'deliveries': deliveries, 'return_at': returned + shift}


def live_route_schedule(plan, status_map=None):
    schedule = route_schedule_datetimes(plan, status_map)
    return {
        'delivery_times': {key: row['arrival'].strftime('%H:%M') if row['arrival'] else None
                           for key, row in schedule['deliveries'].items()},
        'rientro_stimato_aggiornato': schedule['return_at'].strftime('%H:%M'),
    }
