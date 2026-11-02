"""Doppio passaggio Mapbox: il traffico corregge l'ordine delle fermate.

1. Il giro viene calcolato con i tempi stradali (OSRM, con il margine prudente).
2. Mapbox restituisce i tempi con il traffico tipico di quel giorno e di quell'ora.
3. Se qualche consegna finisce fuori fascia, dal giro stesso si ricava di quanto il
   traffico allunga i tempi; le fermate vengono riordinate con i tempi corretti e si
   chiede di nuovo Mapbox. Il nuovo ordine resta solo se ha meno ritardi.

Nessun dato viene salvato oltre al giro: il fattore vale solo per quel calcolo.
Senza un fornitore di traffico configurato nulla cambia.
"""
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
