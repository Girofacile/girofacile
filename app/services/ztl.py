"""Segnalazione informativa ZTL: esclusivamente perimetri OpenStreetMap locali.

Non e' una verifica legale dei permessi, degli orari o della completezza delle ZTL.
Il file GeoJSON viene aggiornato separatamente; nessuna chiamata API per consegna.
"""
import json
import math
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "ztl" / "ztl_osm.geojson"
WARNING = "Attenzione: consegna in zona ZTL. Verifica i permessi di accesso del tuo mezzo."


def _on_segment(x, y, ax, ay, bx, by):
    cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
    return abs(cross) < 1e-10 and min(ax, bx) <= x <= max(ax, bx) and min(ay, by) <= y <= max(ay, by)


def _in_ring(x, y, ring):
    """Ray casting, bordo incluso; GeoJSON usa coordinate [lon, lat]."""
    inside = False
    for index in range(len(ring)):
        ax, ay = ring[index - 1][:2]
        bx, by = ring[index][:2]
        if _on_segment(x, y, ax, ay, bx, by):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _in_polygon(lon, lat, polygon):
    return bool(polygon and _in_ring(lon, lat, polygon[0])
                and not any(_in_ring(lon, lat, hole) for hole in polygon[1:]))


@lru_cache(maxsize=4)
def _read_zones(filename, stamp):
    with open(filename, encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Archivio ZTL non valido: atteso FeatureCollection")
    zones = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        shape = geometry.get("type")
        coords = geometry.get("coordinates") or []
        if shape == "Polygon":
            polygons = [coords]
        elif shape == "MultiPolygon":
            polygons = coords
        else:
            continue
        for polygon in polygons:
            try:
                outer = polygon[0]
                if len(outer) < 4:
                    continue
                xs = [point[0] for point in outer]
                ys = [point[1] for point in outer]
                zones.append((min(xs), min(ys), max(xs), max(ys), polygon,
                              (feature.get("properties") or {}).get("name")))
            except (IndexError, ValueError, TypeError):
                continue
    return zones


def detect_ztl(lat, lon):
    """Tre stati: rilevata, non_rilevata, non_disponibile.

    'non_rilevata' NON prova che l'indirizzo sia fuori da ogni ZTL.
    Mantiene sempre la segnalazione manuale separata dal risultato automatico.
    """
    try:
        if lat is None or lon is None:
            return {"detected": False, "status": "non_disponibile", "zone": None}
        y, x = float(lat), float(lon)
        if not (math.isfinite(y) and math.isfinite(x) and -90 <= y <= 90 and -180 <= x <= 180):
            raise ValueError("Coordinate non valide")
        path = Path(os.environ.get("GIROFACILE_ZTL_GEOJSON") or DEFAULT_FILE)
        if not path.is_file():
            return {"detected": False, "status": "non_disponibile", "zone": None}
        stat = path.stat()
        zones = _read_zones(str(path), (stat.st_mtime_ns, stat.st_size))
        if not zones:
            return {"detected": False, "status": "non_disponibile", "zone": None}
        for west, south, east, north, polygon, name in zones:
            if west <= x <= east and south <= y <= north and _in_polygon(x, y, polygon):
                return {"detected": True, "status": "rilevata", "zone": name}
        return {"detected": False, "status": "non_rilevata", "zone": None}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"detected": False, "status": "non_disponibile", "zone": None}


def customer_ztl(customer):
    """Compatibilita': Customer.ztl rimane il segnale manuale preesistente."""
    automatic = detect_ztl(getattr(customer, "lat", None), getattr(customer, "lon", None))
    manual = bool(getattr(customer, "ztl", False))
    return {
        "ztl": manual or automatic["detected"],
        "ztl_manual": manual,
        "ztl_source": "manuale" if manual else ("osm" if automatic["detected"] else automatic["status"]),
        "ztl_zone": automatic["zone"] if automatic["detected"] else None,
    }
