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
PEDESTRIAN_FILE = DEFAULT_FILE.with_name("pedestrian_osm.geojson")
OFFICIAL_ZTL_FILE = DEFAULT_FILE.with_name("ztl_official.geojson")
OFFICIAL_PEDESTRIAN_FILE = DEFAULT_FILE.with_name("pedestrian_official.geojson")
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


def _detect_area(lat, lon, path):
    """Controllo geometrico locale: nessuna chiamata API e nessun vincolo al routing."""
    try:
        if lat is None or lon is None:
            return {"detected": False, "status": "non_disponibile", "zone": None}
        y, x = float(lat), float(lon)
        if not (math.isfinite(y) and math.isfinite(x) and -90 <= y <= 90 and -180 <= x <= 180):
            raise ValueError("Coordinate non valide")
        if not path.is_file():
            return {"detected": False, "status": "non_disponibile", "zone": None}
        stamp = path.stat()
        zones = _read_zones(str(path), (stamp.st_mtime_ns, stamp.st_size))
        if not zones:
            return {"detected": False, "status": "non_disponibile", "zone": None}
        for west, south, east, north, polygon, name in zones:
            if west <= x <= east and south <= y <= north and _in_polygon(x, y, polygon):
                return {"detected": True, "status": "rilevata", "zone": name}
        return {"detected": False, "status": "non_rilevata", "zone": None}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {"detected": False, "status": "non_disponibile", "zone": None}


def _sources(lat, lon, official_env, official_file, osm_env, osm_file):
    # GeoJSON ufficiali locali solo se esplicitamente forniti e licenziati.
    # Una mancata corrispondenza nel Comune NON esclude una zona OSM.
    official = _detect_area(lat, lon, Path(os.environ.get(official_env) or official_file))
    if official["detected"]:
        return official, "comunale"
    osm = _detect_area(lat, lon, Path(os.environ.get(osm_env) or osm_file))
    if osm["detected"]:
        return osm, "osm"
    return (official if osm["status"] == "non_disponibile" else osm), None


def detect_ztl(lat, lon):
    """ZTL comunale se presente, altrimenti OSM; non rilevata NON implica accesso libero."""
    return _sources(lat, lon, "GIROFACILE_ZTL_OFFICIAL_GEOJSON", OFFICIAL_ZTL_FILE,
                    "GIROFACILE_ZTL_GEOJSON", DEFAULT_FILE)[0]


def detect_pedestrian(lat, lon):
    """Aree pedonali poligonali ufficiali e OSM; niente comuni marciapiedi."""
    return _sources(lat, lon, "GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON", OFFICIAL_PEDESTRIAN_FILE,
                    "GIROFACILE_PEDESTRIAN_GEOJSON", PEDESTRIAN_FILE)[0]


def customer_ztl(customer):
    """Compatibilita': Customer.ztl rimane il segnale manuale preesistente."""
    lat, lon = getattr(customer, "lat", None), getattr(customer, "lon", None)
    automatic, ztl_source = _sources(lat, lon, "GIROFACILE_ZTL_OFFICIAL_GEOJSON", OFFICIAL_ZTL_FILE,
                                      "GIROFACILE_ZTL_GEOJSON", DEFAULT_FILE)
    pedestrian, pedestrian_source = _sources(lat, lon, "GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON",
                                             OFFICIAL_PEDESTRIAN_FILE, "GIROFACILE_PEDESTRIAN_GEOJSON", PEDESTRIAN_FILE)
    manual = bool(getattr(customer, "ztl", False))
    return {
        "ztl": manual or automatic["detected"],
        "ztl_manual": manual,
        "ztl_source": "manuale" if manual else (ztl_source if automatic["detected"] else automatic["status"]),
        "ztl_zone": automatic["zone"] if automatic["detected"] else None,
        "pedestrian_area": pedestrian["detected"],
        "pedestrian_source": pedestrian_source if pedestrian["detected"] else pedestrian["status"],
        "pedestrian_zone": pedestrian["zone"] if pedestrian["detected"] else None,
    }
