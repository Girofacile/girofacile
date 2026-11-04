"""Doppio passaggio Mapbox: il traffico corregge l'ordine delle fermate.

1. Il giro viene calcolato con i tempi stradali (OSRM, con il margine prudente).
2. Mapbox restituisce i tempi con il traffico tipico di quel giorno e di quell'ora.
3. Se qualche consegna finisce fuori fascia, dal giro stesso si ricava di quanto il
   traffico allunga i tempi; le fermate vengono riordinate con i tempi corretti e si
   chiede di nuovo Mapbox. Il nuovo ordine resta solo se ha meno ritardi.
4. Se resta un ritardo, si rifà il calcolo (nel multi-mezzo l'intera divisione tra i
   mezzi) con i tempi corretti e le finestre originali, poi Mapbox. Solo se restano
   ritardi si prova un margine: la puntualità conta prima dei chilometri. Nel
   multi-mezzo vale anche per un rientro oltre la fine del turno: la ricerca usa un
   turno più corto di qualche minuto.

Nessun dato viene salvato oltre al giro: il fattore vale solo per quel calcolo.
Senza un fornitore di traffico configurato nulla cambia.
"""
import math

from .road_routing import RoadMatrix

MAX_FACTOR = 3.0


def travel_factor(base_minutes, traffic_seconds):
    """Rapporto tra tempi con traffico e tempi usati nel calcolo, solo se il traffico allunga."""
    base = sum(float(value or 0) for value in base_minutes)
    traffic = sum(float(value or 0) for value in traffic_seconds) / 60
    if base <= 0 or traffic <= base:
        return None
    return min(MAX_FACTOR, traffic / base)


def scaled_matrix(matrix, factor):
    """Stessa matrice, con i minuti di guida moltiplicati per il fattore del traffico."""
    return RoadMatrix({key: {**leg, 'min': float(leg.get('min') or 0) * factor} for key, leg in matrix.items()},
                      source=getattr(matrix, 'source', 'osrm'))


def lateness(late):
    """Ordine dei ritardi: prima quante consegne fuori fascia, poi i minuti totali."""
    return (len(late), round(sum(float(item.get('lateness_min') or 0) for item in late), 1))


def buffered(row, minutes):
    """Copia della consegna con le fasce chiuse prima di ``minutes`` minuti, solo per la ricerca.

    Una fascia fattibile conserva spazio per lo scarico; una fascia già impossibile
    resta invariata. Il limite originale non viene mai esteso.
    """
    from ..optimizer import parse_hhmm
    copy = dict(row)
    service = float(row.get('tempo_scarico_min') or 0)
    for period in ('mattina', 'pomeriggio'):
        start, end = parse_hhmm(row.get(f'scarico_{period}_da')), parse_hhmm(row.get(f'scarico_{period}_a'))
        if start is None or end is None or end <= start:
            continue
        closing = min(end, max(end - max(0, minutes), math.ceil(start + service)))
        copy[f'scarico_{period}_a'] = f'{closing // 60:02d}:{closing % 60:02d}'
    return copy


def replan_buffer(late):
    """Margine del terzo passaggio: almeno 15 minuti, o il ritardo osservato, fino a 45."""
    return min(45, max(15, math.ceil(max(float(item.get('lateness_min') or 0) for item in late))))


def shift_buffer(overtime_min):
    """Margine sul turno quando il traffico porta il rientro oltre la fine: il ritardo più 10 minuti, fino a 60."""
    return min(60, max(10, math.ceil(float(overtime_min or 0)) + 10))


def shortened_shift(vehicle, minutes):
    """Copia del mezzo con il turno che finisce ``minutes`` minuti prima, solo per la ricerca.

    Il turno non si accorcia mai oltre la sua metà: un margine eccessivo svuoterebbe i giri.
    """
    from ..optimizer import parse_hhmm
    schedule = dict((vehicle or {}).get('driver_schedule') or {})
    start, end = parse_hhmm(schedule.get('start')), parse_hhmm(schedule.get('end'))
    if vehicle is None or start is None or end is None:
        return vehicle
    closing = max(end - minutes, start + (end - start) // 2)
    for pause in schedule.get('breaks') or []:
        closing = max(closing, parse_hhmm(pause['end']) or closing)  # le pause restano dentro il turno
    schedule['end'] = f'{closing // 60:02d}:{closing % 60:02d}'
    return {**vehicle, 'driver_schedule': schedule}
