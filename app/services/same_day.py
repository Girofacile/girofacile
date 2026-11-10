"""Clienti che hanno già una consegna in un altro giro dello stesso giorno (doppioni da segnalare)."""
from ..models import Delivery, RoutePlan

ACTIVE = ('programmato', 'in_corso')


def already_planned(db, user_id, day, customer_ids, exclude_route_ids=()):
    ids = sorted({int(c) for c in customer_ids if c})
    if not day or not ids:
        return []
    rows = (db.query(Delivery.customer_id, Delivery.cliente_nome, RoutePlan.id, RoutePlan.nome, RoutePlan.orario_partenza)
            .join(RoutePlan, RoutePlan.id == Delivery.route_plan_id)
            .filter(RoutePlan.user_id == user_id, RoutePlan.data_giro == day, RoutePlan.status.in_(ACTIVE),
                    ~RoutePlan.id.in_(list(exclude_route_ids) or [0]), Delivery.customer_id.in_(ids))
            .order_by(Delivery.cliente_nome).all())
    seen, out = set(), []
    for customer_id, name, route_id, route_name, start in rows:
        if (customer_id, route_id) in seen:
            continue
        seen.add((customer_id, route_id))
        out.append({'customer_id': customer_id, 'cliente_nome': name, 'route_id': route_id, 'route_nome': route_name,
                    'orario_partenza': start.strftime('%H:%M') if start else None})
    return out
