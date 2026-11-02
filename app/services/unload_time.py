"""Tempo di scarico di una fermata, in ordine di priorità.

1. Tempo scritto dall'operatore sul cliente o sulla fermata.
2. Tempo imparato dalle consegne reali del cliente (route_execution).
3. Stima dai colli, con la formula dell'azienda: minuti fissi + secondi per collo.
4. 10 minuti.

Il calcolo degli orari esige che lo scarico finisca entro la fascia: con 15 minuti
e chiusura alle 12:00 l'arrivo deve avvenire entro le 11:45.
Dieci minuti senza misure reali sono il valore predefinito, non una scelta: in quel
caso, e quando la fermata è già stata stimata, si usa la stima dai colli.
"""
import math

DEFAULT_MINUTES = 10
DEFAULTS = {'unload_base_min': 4, 'unload_seconds_per_package': 15, 'unload_max_min': 30}
LIMITS = {'unload_base_min': (0, 120), 'unload_seconds_per_package': (0, 600), 'unload_max_min': (1, 240)}


def settings(user):
    values = {}
    for key, default in DEFAULTS.items():
        value = getattr(user, key, None)
        values[key] = int(value) if value is not None else default
    return values


def estimate(packages, user):
    """Minuti stimati dai colli, oppure None senza colli."""
    try:
        packages = int(packages or 0)
    except (TypeError, ValueError):
        return None
    if packages <= 0:
        return None
    rule = settings(user)
    minutes = math.ceil(rule['unload_base_min'] + packages * rule['unload_seconds_per_package'] / 60)
    return max(1, min(rule['unload_max_min'], minutes))


def customer_known(customer):
    """Tempo del cliente scritto a mano o imparato dalle consegne."""
    measured = int(getattr(customer, 'tempo_scarico_rilevazioni', 0) or 0) > 0
    value = getattr(customer, 'tempo_scarico_min', None)
    return measured or (value is not None and int(value) != DEFAULT_MINUTES)


def apply(delivery, user, customer=None):
    """Aggiorna la fermata prima del calcolo, senza toccare i tempi decisi dall'operatore."""
    if customer is not None and customer_known(customer):
        return
    current = delivery.get('tempo_scarico_min')
    automatic = bool(delivery.get('tempo_scarico_auto'))
    if not automatic and current not in (None, DEFAULT_MINUTES):
        return
    minutes = estimate(delivery.get('colli'), user)
    if minutes is None:
        if automatic:
            delivery['tempo_scarico_min'] = DEFAULT_MINUTES
            delivery['tempo_scarico_auto'] = False
        return
    delivery['tempo_scarico_min'] = minutes
    delivery['tempo_scarico_auto'] = True


def for_order(order):
    """(minuti, stimato) per la fermata di un ordine: cliente collegato, poi colli."""
    from sqlalchemy.orm import object_session
    from sqlalchemy.orm.exc import UnmappedInstanceError
    from ..models import Customer, User
    try:
        db = object_session(order)
    except UnmappedInstanceError:
        db = None  # ordine non salvato: solo i colli
    if db is not None and getattr(order, 'customer_id', None):
        customer = db.get(Customer, order.customer_id)
        if customer is not None and customer_known(customer):
            return int(customer.tempo_scarico_min), False
    user = db.get(User, order.user_id) if db is not None else None
    minutes = estimate((order.operational_data or {}).get('packages'), user)
    return (minutes, True) if minutes is not None else (DEFAULT_MINUTES, False)
