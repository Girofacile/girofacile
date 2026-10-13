"""Pause-aware arithmetic shared by optimization, traffic and route displays."""
from ..schemas.driver_schedule import DriverSchedule

def minutes(value):
    if hasattr(value,'hour'): return value.hour*60+value.minute
    h,m=str(value)[:5].split(':');return int(h)*60+int(m)

def clock(value):
    rounded=int(round(value));return f'{rounded//60:02d}:{rounded%60:02d}'

def resolved(override,driver):
    raw=override if override is not None else (getattr(driver,'work_schedule',None) or {})
    return DriverSchedule.model_validate(raw).model_dump(mode='json')

def intervals(schedule):
    return [(minutes(b['start']),minutes(b['end'])) for b in (schedule or {}).get('breaks',[])]

def travel_end(start,duration,pauses):
    cursor=float(start);remaining=float(duration)
    for opening,closing in pauses:
        if closing<=cursor: continue
        if cursor+remaining<=opening: return cursor+remaining
        remaining-=max(0,opening-cursor)
        cursor=max(cursor,closing)
    return cursor+remaining

def service_ready(start,duration,pauses):
    cursor=start
    for opening,closing in pauses:
        if cursor<closing and (cursor>=opening or cursor+duration>opening):
            cursor=closing
    return cursor

def shift_error(schedule,start,end):
    if not schedule or not schedule.get('start'): return None
    if start<minutes(schedule['start']) or end>minutes(schedule['end']):
        return f"Il giro non rientra nel turno dell'autista ({schedule['start']}–{schedule['end']}). Modifica il turno o le consegne."
    return None

def ensure_shift(schedule,start,total):
    error=shift_error(schedule,minutes(start),minutes(start)+float(total))
    if error: raise ValueError(error)

def events(pauses,start,end,departures):
    result=[]
    for opening,closing in pauses:
        if opening>=end or closing<=start: continue
        after=sum(1 for departure in departures if departure<=opening)
        result.append({'start':clock(max(opening,start)),'end':clock(min(closing,end)),
                       'after_order':after,'duration_min':min(closing,end)-max(opening,start)})
    return result

def metadata(plan):
    schedule=getattr(plan,'driver_schedule',None) or {}
    return {'driver_schedule':schedule,'driver_breaks':getattr(plan,'driver_breaks',None) or [],
            'driver_schedule_error':shift_error(schedule,minutes(plan.orario_partenza),minutes(plan.orario_partenza)+float(plan.totale_minuti or 0))}
