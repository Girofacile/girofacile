"""Explicit grouping by verified destination and compatible operational constraints."""
from copy import deepcopy
from uuid import uuid5, NAMESPACE_URL
from .order_customers import normalize


def group_key(user_id, ids):
    return str(uuid5(NAMESPACE_URL, 'girofacile-order:' + str(user_id) + ':' + ','.join(map(str,sorted(ids)))))


def destination(row):
    op = row.get('order_operational') or {}
    return (normalize(row.get('cliente_nome')), normalize(row.get('indirizzo')),
            round(float(row.get('lat',0)),7),round(float(row.get('lon',0)),7),
            row.get('sponda'),row.get('ztl'),op.get('pallet_truck'),normalize(op.get('requirements')))


def windows(row):
    intervals=[]
    for prefix in ('scarico_mattina','scarico_pomeriggio'):
        start,end=row.get(prefix+'_da'),row.get(prefix+'_a')
        if start and end:
            def minute(value):
                parts=str(value).split(':');return int(parts[0])*60+int(parts[1])
            intervals.append((minute(start),minute(end)))
    return intervals or [(0,1440)]


def compatible(rows):
    if len({destination(r) for r in rows}) != 1: return None
    overlap=windows(rows[0])
    for row in rows[1:]:
        overlap=[(max(a,c),min(b,d)) for a,b in overlap for c,d in windows(row) if max(a,c)<min(b,d)]
    overlap=sorted(set(overlap))
    # The existing engine represents up to two daily service windows.
    return overlap if 0 < len(overlap) <= 2 else None


def merge(user_id, rows):
    result=deepcopy(rows[0]);overlap=compatible(rows)
    if not overlap: raise ValueError('Ordini con destinazioni, orari o requisiti incompatibili.')
    result['order_refs']=sorted([ref for row in rows for ref in row['order_refs']],key=lambda r:r['id'])
    result['order_numbers']=[number for row in rows for number in row['order_numbers']]
    result['order_stop_key']=group_key(user_id,[r['id'] for r in result['order_refs']])
    for field in ('peso_kg','colli'): result[field]=sum(row.get(field) or 0 for row in rows)
    result['tempo_scarico_min']=max(row.get('tempo_scarico_min') or 10 for row in rows)
    result['note']='\n'.join(f"{', '.join(row['order_numbers'])}: {row['note']}" for row in rows if row.get('note')) or None
    for key in ('pallets','volume_m3'):
        values=[row['order_operational'].get(key) for row in rows]
        result['order_operational'][key]=sum(values) if all(v is not None for v in values) else None
    for prefix in ('scarico_mattina','scarico_pomeriggio'):
        result[prefix+'_da']=result[prefix+'_a']=None
    if overlap != [(0,1440)]:
        for prefix,(start,end) in zip(('scarico_mattina','scarico_pomeriggio'),overlap):
            result[prefix+'_da']=f'{start//60:02}:{start%60:02}'
            result[prefix+'_a']=f'{end//60:02}:{end%60:02}'
    return result


def group_stops(user_id, rows):
    buckets={}
    for row in rows: buckets.setdefault(destination(row),[]).append(row)
    result=[]
    for bucket in buckets.values():
        groups=[]
        for row in bucket:
            for group in groups:
                if compatible(group+[row]): group.append(row);break
            else: groups.append([row])
        result.extend(merge(user_id,group) if len(group)>1 else group[0] for group in groups)
    return result
