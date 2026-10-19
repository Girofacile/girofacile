"""Aggiorna l'archivio ZTL dal solo OpenStreetMap (query Overpass, non runtime).

Eseguire da cron settimanale: python -m scripts.update_ztl_osm
Evitare richieste frequenti agli endpoint pubblici. Il vecchio file resta intatto
quando la sorgente non risponde o il nuovo estratto non contiene geometrie valide.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from app.services.ztl import DEFAULT_FILE, _in_ring

OVERPASS_URL = os.environ.get("GF_ZTL_OVERPASS_URL", "https://overpass-api.de/api/interpreter")
QUERY = """[out:json][timeout:240];
area["ISO3166-1"="IT"]["admin_level"="2"]->.italy;
(
  way["boundary"="limited_traffic_zone"](area.italy);
  relation["boundary"="limited_traffic_zone"](area.italy);
);
out geom;"""


def points(member):
    return [[float(p["lon"]), float(p["lat"])] for p in member.get("geometry", [])
            if "lat" in p and "lon" in p]


def assemble_rings(parts):
    pending = [list(p) for p in parts if len(p) > 1]
    closed = []
    while pending:
        ring = pending.pop(0)
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, part in enumerate(pending):
                if ring[-1] == part[0]:
                    ring.extend(part[1:])
                elif ring[-1] == part[-1]:
                    ring.extend(reversed(part[:-1]))
                elif ring[0] == part[-1]:
                    ring = part[:-1] + ring
                elif ring[0] == part[0]:
                    ring = list(reversed(part[1:])) + ring
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            closed.append(ring)
    return closed


def geometries(element):
    if element.get("type") == "way":
        ring = points(element)
        return [[ring]] if len(ring) >= 4 and ring[0] == ring[-1] else []
    if element.get("type") != "relation":
        return []
    members = [m for m in element.get("members", []) if m.get("type") == "way"]
    outers = assemble_rings([points(m) for m in members if m.get("role") in ("outer", "")])
    inners = assemble_rings([points(m) for m in members if m.get("role") == "inner"])
    polygons = [[outer] for outer in outers]
    for inner in inners:
        # Un foro appartiene all'anello esterno che lo contiene.
        for polygon in polygons:
            if _in_ring(inner[0][0], inner[0][1], polygon[0]):
                polygon.append(inner)
                break
    return polygons


def build_features(elements):
    features = []
    for e in elements:
        tags = e.get("tags") or {}
        if tags.get("boundary") != "limited_traffic_zone":
            continue
        polygons = geometries(e)
        if not polygons:
            continue
        features.append({
            "type": "Feature",
            "properties": {"osm_type": e.get("type"), "osm_id": e.get("id"),
                           "name": tags.get("name") or tags.get("ref")},
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
        })
    return features


def main():
    response = requests.post(
        OVERPASS_URL, data={"data": QUERY}, timeout=300,
        headers={"User-Agent": os.environ.get("GF_ZTL_USER_AGENT", "GiroFacile-ZTL-OSM-Updater/1.0")},
    )
    response.raise_for_status()
    payload = response.json()
    features = build_features(payload.get("elements") or [])
    if not features:
        raise RuntimeError("Nessun perimetro ZTL valido da OpenStreetMap; archivio esistente mantenuto")
    data = {
        "type": "FeatureCollection",
        "metadata": {"source": "OpenStreetMap contributors", "license": "ODbL 1.0",
                     "source_url": "https://www.openstreetmap.org/copyright",
                     "updated_at": datetime.now(timezone.utc).isoformat(), "count": len(features)},
        "features": features,
    }
    target = Path(os.environ.get("GIROFACILE_ZTL_GEOJSON") or DEFAULT_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="ztl-", suffix=".geojson", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"Archivio ZTL aggiornato: {len(features)} aree, file {target}")


if __name__ == "__main__":
    main()
