"""Configurable estimates from OSRM toll classes and local OSM edge metadata.

Standard OSRM does not expose every OSM tag. Unknown coverage is reported, never
silently converted to a zero toll. No scraping or network pricing API is used.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from .platform_settings import routing_setting

DEFAULT_RATES = {"A": 0.08, "B": 0.10, "3": 0.14, "4": 0.18, "5": 0.22}


class TollCalculator(Protocol):
    def estimate(self, road, vehicle_class="B", *, db=None) -> dict: ...


@lru_cache(maxsize=8)
def _read_dataset(path, modified):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _dataset(db):
    path = routing_setting(db, "toll_dataset_path")
    if not path:
        return {}
    file = Path(path)
    return _read_dataset(str(file), file.stat().st_mtime_ns)


def _amount(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("Tariffa pedaggio non valida")
    return number


def _segments(leg, dataset):
    explicit = leg.get("osm_segments")
    if explicit is not None:
        return explicit
    annotation = leg.get("annotation") or {}
    nodes, distances = annotation.get("nodes") or [], annotation.get("distance") or []
    edges = dataset.get("edges") or {}
    if distances and len(nodes) == len(distances) + 1:
        segments = []
        for a, b, distance in zip(nodes, nodes[1:], distances):
            metadata = edges.get(f"{a},{b}")
            segments.append({**(metadata or {}), "distance": distance})
        # Custom OSRM toll classes can complement an absent node dataset.
        if any(segment.get("tags") for segment in segments):
            return segments
    result = []
    for step in leg.get("steps") or []:
        classes = set(step.get("classes") or [])
        for intersection in step.get("intersections") or []:
            classes.update(intersection.get("classes") or [])
        tags = step.get("osm_tags") or {}
        if "toll" in classes:
            tags = {**tags, "toll": "yes"}
        result.append({"distance": step.get("distance") or 0, "tags": tags})
    return result or [{"distance": leg.get("distance") or 0}]


class InternalOSMTollCalculator:
    def estimate(self, road, vehicle_class="B", *, db=None):
        vehicle_class = str(vehicle_class or "B")
        if vehicle_class not in DEFAULT_RATES:
            vehicle_class = "B"
        rates = {**DEFAULT_RATES, **json.loads(routing_setting(db, "toll_rates_json", "{}"))}
        dataset = _dataset(db)
        total, toll_km, known_meters, unknown_meters = 0.0, 0.0, 0.0, 0.0
        known_segments, unknown_segments, previous_charge = 0, 0, None
        for leg in (road or {}).get("legs") or []:
            for segment in _segments(leg, dataset):
                distance = _amount(segment.get("distance") or 0)
                tags = segment.get("tags") or {}
                flag = tags.get("toll:hgv", tags.get("toll")) if vehicle_class in ("3", "4", "5") else tags.get("toll")
                if str(flag).lower() not in ("yes", "no", "1", "0", "true", "false"):
                    unknown_meters += distance
                    unknown_segments += 1
                    previous_charge = None
                    continue
                known_segments += 1
                known_meters += distance
                if str(flag).lower() in ("no", "0", "false"):
                    previous_charge = None
                    continue
                toll_km += distance / 1000
                fixed = segment.get("fixed_eur_by_class") or {}
                charge = segment.get("charge_id")
                if vehicle_class in fixed:
                    # A fixed tariff can cover multiple consecutive OSM edges.
                    if not charge or charge != previous_charge:
                        total += _amount(fixed[vehicle_class])
                else:
                    rate = (segment.get("eur_per_km_by_class") or {}).get(vehicle_class, rates[vehicle_class])
                    total += distance / 1000 * _amount(rate)
                previous_charge = charge
        available = bool(known_segments)
        status = "estimated" if available and not unknown_segments else ("partial" if available else "unavailable")
        return {"provider": "internal-osm", "status": status,
                "amount_eur": round(total, 2) if available else None,
                "toll_km": round(toll_km, 3), "vehicle_class": vehicle_class,
                "known_km": round(known_meters / 1000, 3),
                "unknown_km": round(unknown_meters / 1000, 3),
                "dataset_version": dataset.get("version"),
                "label": "Pedaggio stimato", "version": 1}


def get_toll_calculator(db=None) -> TollCalculator:
    return InternalOSMTollCalculator()
