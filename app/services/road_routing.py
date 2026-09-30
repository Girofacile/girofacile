"""OSRM for road data only. Ordering and delivery constraints belong to GiroFacile."""
from __future__ import annotations

import math
import requests

from . import distance_cache as dc
from .platform_settings import osrm_url, routing_number, routing_setting


class RoadMatrix(dict):
    def __init__(self, *args, source="osrm", **kwargs):
        super().__init__(*args, **kwargs)
        self.source = source


def estimated_leg(a, b):
    lat1, lat2 = math.radians(float(a["lat"])), math.radians(float(b["lat"]))
    dlat = lat2 - lat1
    dlon = math.radians(float(b["lon"]) - float(a["lon"]))
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    km = 6371 * 2 * math.asin(math.sqrt(min(1, max(0, h)))) * 1.25
    return {"km": km, "min": km / 45 * 60}


def _coordinates(points):
    clean = []
    for p in points:
        lat, lon = float(p["lat"]), float(p["lon"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Coordinate non valide")
        clean.append(f"{lon:.7f},{lat:.7f}")
    return ";".join(clean)


def _valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def osrm_table(points, *, pairs=None, db=None):
    """One Table request for normal tours; bounded rectangular blocks for larger ones."""
    pairs = list(pairs if pairs is not None else
                 ((i, j) for i in range(len(points)) for j in range(len(points)) if i != j))
    if not pairs:
        return {}
    url = osrm_url(db)
    limit = int(routing_number(db, "osrm_table_max_coordinates", 100, 2))
    origins, destinations = sorted({i for i, _ in pairs}), sorted({j for _, j in pairs})
    union = sorted(set(origins + destinations))
    blocks = [(origins, destinations)] if len(union) <= limit else [
        (origins[a:a + limit // 2], destinations[b:b + limit // 2])
        for a in range(0, len(origins), limit // 2)
        for b in range(0, len(destinations), limit // 2)]
    wanted, result = set(pairs), {}
    for sources, targets in blocks:
        if not any((i, j) in wanted for i in sources for j in targets):
            continue
        indices = sorted(set(sources + targets))
        local = {value: index for index, value in enumerate(indices)}
        try:
            response = requests.get(
                f"{url}/table/v1/driving/{_coordinates([points[i] for i in indices])}",
                params={"annotations": "distance,duration",
                        "sources": ";".join(str(local[i]) for i in sources),
                        "destinations": ";".join(str(local[j]) for j in targets)},
                timeout=routing_number(db, "routing_timeout_seconds", 15, 1))
            response.raise_for_status()
            data = response.json()
            if data.get("code") != "Ok":
                continue
            distances, durations = data["distances"], data["durations"]
            if len(distances) != len(sources) or len(durations) != len(sources):
                continue
            for a, i in enumerate(sources):
                if len(distances[a]) != len(targets) or len(durations[a]) != len(targets):
                    continue
                for b, j in enumerate(targets):
                    km, seconds = distances[a][b], durations[a][b]
                    if (i, j) in wanted and _valid_number(km) and _valid_number(seconds):
                        result[i, j] = {"km": float(km) / 1000, "min": float(seconds) / 60}
        except (requests.RequestException, ValueError, KeyError, TypeError):
            # Never replace the persistent road cache with approximate distances.
            continue
    return result


def build_matrix(db, user_id, points, keys):
    pairs = [(i, j) for i in range(len(points)) for j in range(len(points)) if i != j]
    version = routing_setting(db, "osrm_cache_version", "v1")
    keys = [f"{key}|base=osrm:{version}" for key in keys]
    key_pairs = [(keys[i], keys[j]) for i, j in pairs]
    cached = dc.get_pairs(db, user_id, key_pairs) if db is not None else {}
    matrix = RoadMatrix()
    missing = []
    for pair, key_pair in zip(pairs, key_pairs):
        if key_pair in cached:
            matrix[pair] = cached[key_pair]
        else:
            missing.append(pair)
    fresh = osrm_table(points, pairs=missing, db=db) if missing else {}
    if fresh and db is not None:
        dc.save_pairs(db, user_id, [
            (keys[i], keys[j], leg["km"], leg["min"]) for (i, j), leg in fresh.items()])
    matrix.update(fresh)
    fallback = 0
    for i, j in missing:
        if (i, j) not in matrix:
            matrix[i, j] = estimated_leg(points[i], points[j])
            fallback += 1
    matrix.source = ("estimated" if fallback == len(pairs) else "mixed") if fallback else "osrm"
    return matrix


def road_route(points, *, db=None):
    """Final ordered route geometry/OSM annotations for maps and toll estimation."""
    if len(points) < 2:
        return {"legs": [], "geometries": []}
    limit = int(routing_number(db, "osrm_route_max_coordinates", 100, 2))
    url = osrm_url(db)
    legs, geometries = [], []
    for start in range(0, len(points) - 1, limit - 1):
        chunk = points[start:start + limit]
        response = requests.get(
            f"{url}/route/v1/driving/{_coordinates(chunk)}",
            params={"steps": "true", "annotations": "nodes,distance,duration",
                    "overview": "full", "geometries": "polyline"},
            timeout=routing_number(db, "routing_timeout_seconds", 15, 1))
        response.raise_for_status()
        data = response.json()
        routes = data.get("routes") or []
        if data.get("code") != "Ok" or not routes or len(routes[0].get("legs", [])) != len(chunk) - 1:
            raise ValueError("Percorso OSRM incompleto")
        legs.extend(routes[0]["legs"])
        geometries.append(routes[0].get("geometry"))
    return {"legs": legs, "geometries": geometries}
