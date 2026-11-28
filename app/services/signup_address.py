"""Sede operativa nella registrazione: completamento indirizzi Google Places (API New).

Pagina pubblica (chi si iscrive non ha ancora un account): per questo un limite per visitatore e
nessun uso della quota di Geocoding, che serve alla verifica degli indirizzi dei clienti.
Il session token raggruppa suggerimenti e dettagli dello stesso indirizzo in un'unica sessione Google.
"""
import re
import threading
import time
from collections import OrderedDict, deque

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .api_usage import log_api_usage
from .platform_settings import google_maps_api_key

PLACES = "https://places.googleapis.com/v1"
SEARCHES_PER_WINDOW = 60
WINDOW_SECONDS = 600
MAX_TRACKED = 5000
_requests: "OrderedDict[str, deque[float]]" = OrderedDict()
_lock = threading.Lock()


def limit_visitor(ip: str) -> None:
    """Al massimo SEARCHES_PER_WINDOW richieste ogni WINDOW_SECONDS per indirizzo IP."""
    now = time.monotonic()
    with _lock:
        bucket = _requests.setdefault(ip, deque())
        _requests.move_to_end(ip)
        while bucket and bucket[0] <= now - WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= SEARCHES_PER_WINDOW:
            raise HTTPException(429, "Troppe ricerche di indirizzi. Riprova tra qualche minuto.")
        bucket.append(now)
        while len(_requests) > MAX_TRACKED:
            _requests.popitem(last=False)


def _session(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value or "") else ""


def _call(db: Session, method: str, url: str, action: str, **kwargs):
    key = google_maps_api_key(db)
    if not key:
        raise HTTPException(503, "Ricerca indirizzi non disponibile")
    started, outcome, message = time.perf_counter(), "failed", "Errore"
    try:
        headers = {"X-Goog-Api-Key": key, **kwargs.pop("headers", {})}
        response = requests.request(method, url, headers=headers, timeout=8, **kwargs)
        message = str(response.status_code)
        if not response.ok:
            raise HTTPException(503, "Ricerca indirizzi non disponibile")
        outcome = "success"
        return response.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Ricerca indirizzi non disponibile")
    finally:
        try:
            log_api_usage(db, user_id=None, provider="google", service="google_places", action=action,
                          endpoint=url.replace(PLACES, "/places/v1").split("?")[0][:120], status=outcome, message=message,
                          response_ms=int((time.perf_counter() - started) * 1000))
        except Exception:
            pass


def suggestions(db: Session, query: str, session: str = "") -> list:
    text = (query or "").strip()[:200]
    if len(text) < 4:
        return []
    body = {"input": text, "includedRegionCodes": ["it"], "languageCode": "it", "regionCode": "it"}
    if _session(session):
        body["sessionToken"] = session
    data = _call(db, "POST", f"{PLACES}/places:autocomplete", "Registrazione: suggerimenti sede", json=body)
    rows = []
    for item in data.get("suggestions") or []:
        prediction = item.get("placePrediction") or {}
        place_id, label = prediction.get("placeId"), ((prediction.get("text") or {}).get("text") or "").strip()
        if place_id and label:
            rows.append({"place_id": place_id, "label": label})
    return rows[:6]


def details(db: Session, place_id: str, session: str = "") -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,300}", place_id or ""):
        raise HTTPException(400, "Indirizzo non valido")
    params = {"languageCode": "it", "regionCode": "it"}
    if _session(session):
        params["sessionToken"] = session
    data = _call(db, "GET", f"{PLACES}/places/{place_id}", "Registrazione: dettagli sede", params=params,
                 headers={"X-Goog-FieldMask": "formattedAddress,addressComponents,location"})
    parts = {}
    for comp in data.get("addressComponents") or []:
        for kind in comp.get("types") or []:
            parts.setdefault(kind, comp.get("longText") or "")
            parts.setdefault(kind + ":short", comp.get("shortText") or "")
    street = ", ".join(p for p in (parts.get("route", ""), parts.get("street_number", "")) if p)
    city = parts.get("locality") or parts.get("administrative_area_level_3") or parts.get("postal_town") or ""
    location = data.get("location") or {}
    return {
        "address": (data.get("formattedAddress") or "").strip(),
        "street": street,
        "city": city,
        "zip": parts.get("postal_code", ""),
        "province": parts.get("administrative_area_level_2:short", ""),
        "country": parts.get("country") or "Italia",
        "has_street_number": bool(parts.get("street_number")),
        "lat": location.get("latitude"),
        "lon": location.get("longitude"),
    }
