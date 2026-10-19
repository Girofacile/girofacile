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
    planned = {}

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
        planned[delivery.id] = {'arrival': arrival, 'departure': departure, 'previous_departure': cursor}
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
    if shift or source == 'execution':
        _project_shift(plan, statuses, result, start, started, planned, returned)
    _apply_gps(plan, statuses, result, now or datetime.now(LOCAL))
    return result


def _project_shift(plan, statuses, result, start, started, planned, planned_return):
    """Reapply opening waits and fixed breaks after actual execution."""
    import json
    from ..optimizer import _evaluate_fixed_sequence
    from .driver_schedule import travel_end, intervals

    cursor = started.replace(tzinfo=LOCAL) if plan.status == 'in_corso' and started else start
    changed = cursor if plan.status == 'in_corso' and started else None
    previous_departure = start
    for delivery in sorted(plan.deliveries or [], key=lambda d: (d.ordine or 0, d.id or 0)):
        baseline = planned[delivery.id]
        previous_departure = baseline['departure'] or baseline['arrival'] or previous_departure
        status = statuses.get(delivery.id)
        if status and status.status in ('completata', 'mancata') and status.completata_il:
            cursor = status.completata_il.replace(tzinfo=LOCAL)
            changed = cursor
            continue
        if not changed:
            continue
        travel = float(delivery.minuti_tappa or 0)
        if not travel and baseline['arrival']:
            details = json.loads(delivery.optimizer_details or '{}')
            elapsed = (baseline['arrival'] - baseline['previous_departure']).total_seconds() / 60
            travel = max(0, elapsed - float(delivery.attesa_min or 0) - float(details.get('pause_travel_min') or 0))
        if not baseline['arrival'] and not travel:
            break
        schedule = (getattr(plan, 'driver_schedule', None) or {}) if cursor.date() == plan.data_giro else {}
        row = {field: getattr(delivery, field) for field in (
            'tempo_scarico_min', 'scarico_mattina_da', 'scarico_mattina_a',
            'scarico_pomeriggio_da', 'scarico_pomeriggio_a')}
        row['_matrix_index'] = 1
        projection_start = cursor.replace(second=0, microsecond=0)
        leg_minutes = travel + (cursor - projection_start).total_seconds() / 60
        evaluation = _evaluate_fixed_sequence(
            [row], {(0, 1): {'km': delivery.km_tappa or 0, 'min': leg_minutes}}, [],
            {'driver_schedule': schedule}, False, projection_start.strftime('%H:%M'))
        timing = evaluation['ordered'][0]
        arrival = projection_start + timedelta(minutes=leg_minutes + float(timing.get('pause_travel_min') or 0)
                                               + float(timing.get('attesa_min') or 0))
        result['deliveries'][delivery.id] = {'arrival': arrival, 'source': 'execution', 'updated_at': changed}
        cursor = projection_start + timedelta(minutes=evaluation['total_min'])
    else:
        if changed:
            if plan.rientro_deposito:
                snapshot = json.loads(plan.routing_snapshot_json or '{}')
                traffic = json.loads(plan.traffic_result_json or '{}')
                legs = traffic.get('legs') or []
                base_legs = snapshot.get('base_legs') or []
                if legs:
                    back = float(legs[-1]['duration']) / 60
                elif base_legs:
                    back = float(base_legs[-1].get('min') or 0)
                else:
                    back = max(0, (planned_return - previous_departure).total_seconds() / 60)
                minute = cursor.hour * 60 + cursor.minute + cursor.second / 60
                pauses = intervals(getattr(plan, 'driver_schedule', None)) if cursor.date() == plan.data_giro else []
                cursor += timedelta(minutes=travel_end(minute, back, pauses) - minute)
            result['return_at'] = cursor


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
    from .driver_schedule import intervals,travel_end,service_ready
    pauses=intervals(getattr(plan,"driver_schedule",None))
    if pauses and updated.date()==plan.data_giro:
        minute=updated.hour*60+updated.minute+updated.second/60
        drive=(arrival-updated).total_seconds()/60
        arrival=updated+timedelta(minutes=travel_end(minute,drive,pauses)-minute)
    last_old = last_new = None
    for index, delivery in enumerate(pending):
        if index:
            # Use persisted legs, excluding waits so opening times are applied below.
            minutes = delivery.minuti_tappa
            if minutes is None:
                break
            minute=arrival.hour*60+arrival.minute+arrival.second/60
            active_pauses=pauses if arrival.date()==plan.data_giro else []
            arrival += timedelta(minutes=travel_end(minute,max(0,float(minutes)),active_pauses)-minute)
        minute=arrival.hour*60+arrival.minute+arrival.second/60
        active_pauses=pauses if arrival.date()==plan.data_giro else []
        arrival+=timedelta(minutes=service_ready(minute,float(delivery.tempo_scarico_min or 0),active_pauses)-minute)
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
            minute=arrival.hour*60+arrival.minute+arrival.second/60
            arrival+=timedelta(minutes=service_ready(minute,float(delivery.tempo_scarico_min or 0),active_pauses)-minute)
            if active_pauses and not any(start<=arrival and arrival+timedelta(minutes=float(delivery.tempo_scarico_min or 0))<=end for start,end in windows):
                for rest in pending[index:]:result['deliveries'][rest.id]={'arrival':None,'source':None,'updated_at':updated}
                break
        last_old = result['deliveries'][delivery.id]['arrival']
        last_new = arrival
        result['deliveries'][delivery.id] = {'arrival': arrival, 'source': 'gps', 'updated_at': updated}
        arrival += timedelta(minutes=max(0, delivery.tempo_scarico_min or 0))
    if last_old and last_new:
        if pauses:
            import json
            if plan.rientro_deposito:
                snapshot=json.loads(plan.routing_snapshot_json or '{}');traffic=json.loads(plan.traffic_result_json or '{}')
                legs=traffic.get('legs') or []
                back=float(legs[-1]['duration'])/60 if legs else float((snapshot.get('base_legs') or [{}])[-1].get('min') or 0)
                minute=arrival.hour*60+arrival.minute+arrival.second/60
                arrival+=timedelta(minutes=travel_end(minute,back,pauses if arrival.date()==plan.data_giro else [])-minute)
            result['return_at']=arrival
        else:
            result['return_at'] += last_new - last_old


def live_route_schedule(plan, status_map=None):
    schedule = route_schedule_datetimes(plan, status_map)
    return {
        'delivery_times': {key: row['arrival'].strftime('%H:%M') if row['arrival'] else None
                           for key, row in schedule['deliveries'].items()},
        'rientro_stimato_aggiornato': schedule['return_at'].strftime('%H:%M'),
    }
