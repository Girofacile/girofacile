"""Tempo di scarico di una fermata, in ordine di priorità.

1. Tempo scritto dall'operatore sul cliente o sulla fermata.
2. Tempo imparato dalle consegne reali del cliente (route_execution).
3. Stima dai colli, solo se l'azienda la attiva: minuti fissi + secondi per collo.
4. 10 minuti.

Il calcolo degli orari esige che lo scarico finisca entro la fascia: con 15 minuti
e chiusura alle 12:00 l'arrivo deve avvenire entro le 11:45.
False indica una scelta manuale, True una stima ricalcolabile, None una
provenienza non specificata. I tempi salvati sul cliente sono conservati anche
quando valgono 10 minuti: non è possibile dedurne la provenienza dal numero.
"""
import math

DEFAULT_MINUTES = 10
DEFAULTS = {'unload_base_min': 4, 'unload_seconds_per_package': 15}
LIMITS = {'unload_base_min': (0, 120), 'unload_seconds_per_package': (0, 600)}
# Nessun massimo scelto dall'azienda: solo il limite tecnico di una fermata (24 ore, come nello schema).
TECHNICAL_MAX_MIN = 1440


def settings(user):
    values = {}
    for key, default in DEFAULTS.items():
        value = getattr(user, key, None)
        values[key] = int(value) if value is not None else default
    values['unload_by_packages'] = bool(getattr(user, 'unload_by_packages', False))
    return values


def estimate(packages, user):
    """Minuti stimati dai colli, oppure None senza colli o con la stima spenta."""
    if not getattr(user, 'unload_by_packages', False):
        return None
    try:
        packages = int(packages or 0)
    except (TypeError, ValueError):
        return None
    if packages <= 0:
        return None
    rule = settings(user)
    minutes = math.ceil(rule['unload_base_min'] + packages * rule['unload_seconds_per_package'] / 60)
    return max(1, min(TECHNICAL_MAX_MIN, minutes))


def customer_known(customer):
    """Tempo del cliente scritto a mano o imparato dalle consegne."""
    value = getattr(customer, 'tempo_scarico_min', None)
    return value is not None


def apply(delivery, user, customer=None):
    """Aggiorna la fermata prima del calcolo, senza toccare i tempi decisi dall'operatore."""
    current = delivery.get('tempo_scarico_min')
    provenance = delivery.get('tempo_scarico_auto')
    automatic = provenance is True
    if provenance is False or (not automatic and current not in (None, DEFAULT_MINUTES)):
        return
    if customer is not None and customer_known(customer):
        delivery['tempo_scarico_min'] = int(customer.tempo_scarico_min)
        if automatic:
            delivery['tempo_scarico_auto'] = False
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
