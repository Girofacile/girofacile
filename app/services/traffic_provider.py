"""Replaceable final-route traffic providers. Never optimizes waypoint order."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import time
from typing import Protocol
import requests

from .api_usage import log_api_usage
from .platform_settings import mapbox_access_token, routing_number, traffic_provider_name


class TrafficUnavailable(Exception):
    pass


class TrafficProvider(Protocol):
    name: str
    def calculate(self, points, departure, *, db=None, user_id=None, route_id=None, advance_departure=None): ...


class NoTrafficProvider:
    name = "none"

    def calculate(self, points, departure, **kwargs):
        return None


class MapboxTrafficProvider:
    name = "mapbox"

    def calculate(self, points, departure, *, db=None, user_id=None, route_id=None, advance_departure=None):
        token = mapbox_access_token(db)
        if not token:
            raise TrafficUnavailable("Token Mapbox non configurato")
        # driving-traffic accepts at most 10 coordinates (including depot/return).
        limit = min(10, int(routing_number(db, "mapbox_max_coordinates", 10, 2)))
        legs, geometries = [], []
        segment_departure = departure
        for start in range(0, len(points) - 1, limit - 1):
            chunk = points[start:start + limit]
            coordinates = ";".join(f"{float(p['lon']):.7f},{float(p['lat']):.7f}" for p in chunk)
            endpoint = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coordinates}"
            started, outcome = time.perf_counter(), "failed"
            try:
                response = requests.get(endpoint, params={
                    "access_token": token, "depart_at": segment_departure,
                    "alternatives": "false", "overview": "full", "geometries": "polyline",
                    "steps": "true", "continue_straight": "true",
                }, timeout=routing_number(db, "routing_timeout_seconds", 15, 1))
                response.raise_for_status()
                data = response.json()
                routes = data.get("routes") or []
                if data.get("code") != "Ok" or not routes:
                    raise TrafficUnavailable("Mapbox non ha restituito un percorso")
                route = routes[0]
                segment_legs = route.get("legs") or []
                if len(segment_legs) != len(chunk) - 1:
                    raise TrafficUnavailable("Legs Mapbox incompleti")
                if any(not isinstance(leg.get("duration"), (int, float)) or
                       not math.isfinite(leg["duration"]) or leg["duration"] < 0
                       for leg in segment_legs):
                    raise TrafficUnavailable("Durate Mapbox non valide")
                # Preserve all provider legs, including the final depot return.
                legs.extend(segment_legs)
                geometries.append(route.get("geometry"))
                outcome = "success"
            except (requests.RequestException, ValueError, KeyError, TypeError, TrafficUnavailable) as exc:
                # Request exceptions may contain a URL with access_token: never log str(exc).
                raise TrafficUnavailable("Traffico Mapbox non disponibile") from exc
            finally:
                if db is not None:
                    log_api_usage(db, user_id=user_id, route_id=route_id, provider="mapbox",
                                  service="mapbox_traffic", action="ETA percorso definitivo",
                                  endpoint="/directions/v5/mapbox/driving-traffic",
                                  status=outcome, response_ms=int((time.perf_counter() - started) * 1000),
                                  estimated_cost_eur=routing_number(db, "mapbox_traffic_cost_eur", 0),
                                  meta={"segment_start": start, "coordinates": len(chunk)},
                                  commit=False)
            if start + len(chunk) < len(points):
                if advance_departure:
                    segment_departure = advance_departure(legs)
                else:
                    utc = datetime.fromisoformat(departure.replace("Z", "+00:00"))
                    segment_departure = (utc + timedelta(seconds=sum(x["duration"] for x in legs))).isoformat()
        return {"provider": self.name, "status": "updated", "legs": legs,
                "geometries": geometries, "departure_time": departure,
                "calculated_at": datetime.now(timezone.utc).isoformat(), "version": 1}


_PROVIDERS = {"mapbox": MapboxTrafficProvider, "none": NoTrafficProvider}


def get_traffic_provider(db=None) -> TrafficProvider:
    name = traffic_provider_name(db)
    if name not in _PROVIDERS:
        raise TrafficUnavailable("Provider traffico non supportato")
    return _PROVIDERS[name]()
