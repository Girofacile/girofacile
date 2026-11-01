"""Consegne oltre il mare: clienti raggiungibili dal deposito solo in traghetto.

Fino alla V1 il routing non conosce orari delle corse, imbarco e biglietti:
OSRM tratta le linee dei traghetti come strade sempre aperte e i tempi
risultano senza senso. Queste consegne restano quindi fuori dai giri e
compaiono negli avvisi. Controllo geometrico locale, senza chiamate API.

I contorni (OpenStreetMap, semplificati) sono in app/data/isole_traghetto.geojson.
Le isole collegate da ponte stradale (Ortigia, Sant'Antioco, Caprera, Mazzorbo)
condividono il gruppo della terra a cui sono unite.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

from .ztl import _in_polygon

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "isole_traghetto.geojson"
# Margine per i contorni semplificati: copre le banchine dei porti, resta molto
# sotto lo Stretto di Messina (~3 km) e i canali della laguna di Venezia.
TOLERANCE_M = 150


@lru_cache(maxsize=1)
def _islands():
    with open(DATA_FILE, encoding="utf-8") as handle:
        data = json.load(handle)
    islands = []
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        for polygon in polygons:
            xs = [point[0] for point in polygon[0]]
            ys = [point[1] for point in polygon[0]]
            islands.append((min(xs), min(ys), max(xs), max(ys), polygon, feature["properties"]["group"]))
    return islands


def _distance_to_ring_m(lon, lat, ring):
    """Distanza minima dal contorno, in metri, con proiezione locale equirettangolare."""
    kx = 111320 * math.cos(math.radians(lat))
    ky = 110540
    best = float("inf")
    for index in range(len(ring)):
        ax, ay = (ring[index - 1][0] - lon) * kx, (ring[index - 1][1] - lat) * ky
        bx, by = (ring[index][0] - lon) * kx, (ring[index][1] - lat) * ky
        dx, dy = bx - ax, by - ay
        t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best


def landmass(lat, lon):
    """Nome dell'isola (gruppo) che contiene il punto, oppure None per il continente."""
    try:
        y, x = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(y) and math.isfinite(x)):
        return None
    margin_x = TOLERANCE_M / (111320 * max(0.1, math.cos(math.radians(y))))
    margin_y = TOLERANCE_M / 110540
    near = []
    for west, south, east, north, polygon, group in _islands():
        if west - margin_x <= x <= east + margin_x and south - margin_y <= y <= north + margin_y:
            if _in_polygon(x, y, polygon):
                return group
            distance = _distance_to_ring_m(x, y, polygon[0])
            if distance <= TOLERANCE_M:
                near.append((distance, group))
    return min(near)[1] if near else None


def ferry_reason(depot, delivery):
    """Motivo dell'esclusione se deposito e cliente non sono sulla stessa terra."""
    coord = delivery.get("coord") or delivery
    if not depot or coord.get("lat") is None or coord.get("lon") is None:
        return None
    origin = landmass(depot.get("lat"), depot.get("lon"))
    target = landmass(coord.get("lat"), coord.get("lon"))
    if origin == target:
        return None
    if target:
        return f"Consegna non programmabile: il cliente si trova su un'isola ({target}), raggiungibile solo in traghetto."
    return f"Consegna non programmabile: il cliente si trova fuori dall'isola del deposito ({origin}), raggiungibile solo in traghetto."


def ferry_exclusions(depot, deliveries):
    """{indice: motivo} delle consegne che richiederebbero un traghetto."""
    reasons = {}
    for index, delivery in enumerate(deliveries):
        reason = ferry_reason(depot, delivery)
        if reason:
            reasons[index] = reason
    return reasons


def excluded_delivery(delivery, reason):
    """Riepilogo della consegna esclusa, mostrato negli avvisi del giro."""
    return {
        "customer_id": delivery.get("customer_id"),
        "cliente_nome": delivery.get("cliente_nome") or "Cliente senza nome",
        "indirizzo": delivery.get("indirizzo") or "",
        "order_refs": delivery.get("order_refs") or [],
        "motivo": reason,
    }


def warning(names):
    if len(names) == 1:
        return (f"1 consegna esclusa dal giro ({names[0]}): il cliente è raggiungibile "
                "solo in traghetto. Pianificala a parte.")
    return (f"{len(names)} consegne escluse dai giri ({', '.join(names)}): i clienti sono "
            "raggiungibili solo in traghetto. Pianificale a parte.")
