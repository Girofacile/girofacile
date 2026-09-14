"""
Servizio geocodifica indirizzi.
Modalità Google-only: usa esclusivamente Google Maps Geocoding.
Geoapify e Nominatim sono disattivati per evitare fallback non desiderati.
"""
from datetime import datetime

import requests

from sqlalchemy.orm import Session

from ..services.platform_settings import google_geocoding_enabled, google_maps_api_key


def normalize_address(value: str) -> str:
    text_value = " ".join(str(value or "").replace("\n", " ").split()).strip()
    for old, new in [
        ("S.S.", "Strada Statale"),
        ("SS ", "Strada Statale "),
        ("Loc.", "Località"),
        ("C.da", "Contrada"),
    ]:
        text_value = text_value.replace(old, new)
    return text_value


def _google_geocode(query: str, limit: int = 5, db: Session | None = None) -> list:
    """Esegue una richiesta Google Geocoding e normalizza i risultati."""
    api_key = google_maps_api_key(db)
    if not google_geocoding_enabled(db) or not api_key:
        print("[GEOCODING] Google disattivato o chiave Google mancante")
        return []

    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": query,
                "region": "it",
                "language": "it",
                "key": api_key,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status != "OK":
            print(f"[GEOCODING] Google status={status} query={query}")
            return []

        results = []
        for item in data.get("results", [])[:limit]:
            geometry = item.get("geometry") or {}
            loc = geometry.get("location") or {}
            location_type = (geometry.get("location_type") or "").upper()
            if loc.get("lat") is None or loc.get("lng") is None:
                continue

            if location_type == "ROOFTOP":
                confidence = 0.98
            elif location_type == "RANGE_INTERPOLATED":
                confidence = 0.90
            elif location_type == "GEOMETRIC_CENTER":
                confidence = 0.78
            else:
                confidence = 0.50

            components = item.get("address_components") or []
            comune = ""
            provincia = ""
            for comp in components:
                types = comp.get("types") or []
                if "locality" in types or "postal_town" in types or "administrative_area_level_3" in types:
                    comune = comune or comp.get("long_name", "")
                if "administrative_area_level_2" in types:
                    provincia = provincia or comp.get("long_name", "")

            results.append({
                "lat": loc.get("lat"),
                "lon": loc.get("lng"),
                "formatted": item.get("formatted_address"),
                "source": "google",
                "confidence": confidence,
                "place_id": item.get("place_id"),
                "location_type": location_type,
                "comune": comune,
                "provincia": provincia,
            })
        print(f"[GEOCODING] Google risultati={len(results)} query={query}")
        return results
    except Exception as e:
        print(f"[GEOCODING] Errore Google: {e}")
        return []


def geocode_address(indirizzo: str, comune: str = "", provincia: str = "", db: Session | None = None) -> dict:
    """
    Geocodifica un indirizzo usando solo Google.
    Ritorna dict con: status, lat, lon, formatted, source, confidence.
    """
    query = ", ".join(
        x for x in [normalize_address(indirizzo), comune, provincia, "Italia"] if x
    )

    results = _google_geocode(query, limit=5, db=db)
    if not results:
        return {"status": "non_trovato", "source": "google"}

    best = results[0]
    try:
        conf = float(best.get("confidence") or 0.5)
    except Exception:
        conf = 0.5

    status = "verificato" if conf >= 0.55 else "da_verificare"
    return {
        "status": status,
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
        "formatted": best.get("formatted"),
        "source": "google",
        "confidence": round(conf, 3),
        "place_id": best.get("place_id"),
        "location_type": best.get("location_type"),
    }


def geocode_customer(customer, db: Session | None = None) -> dict:
    return geocode_address(
        customer.indirizzo or "",
        customer.comune or "",
        customer.provincia or "",
        db=db,
    )


def apply_geocode(customer, result: dict):
    customer.stato_geocodifica = result.get("status", "non_trovato")
    customer.lat = result.get("lat")
    customer.lon = result.get("lon")
    customer.indirizzo_geocodificato = result.get("formatted")
    customer.fonte_geocodifica = result.get("source")
    customer.google_place_id = result.get("place_id")
    customer.affidabilita_geocodifica = result.get("confidence")
    customer.geocodificato_il = datetime.utcnow()


def search_address_autocomplete(
    q: str, comune: str = "", provincia: str = "", db: Session | None = None
) -> list:
    """Ricerca indirizzi per il frontend usando solo Google Geocoding."""
    query = (q or "").strip()
    if len(query) < 3:
        return []

    text_parts = [query]
    if comune and comune.lower() not in query.lower():
        text_parts.append(comune)
    if provincia and provincia.lower() not in query.lower():
        text_parts.append(provincia)
    text_parts.append("Italia")
    text = ", ".join(p for p in text_parts if p)

    google_results = _google_geocode(text, limit=7, db=db)
    results = []
    seen = set()
    for item in google_results:
        label = item.get("formatted") or ""
        if not label or label in seen:
            continue
        seen.add(label)
        results.append(
            {
                "label": label,
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "comune": item.get("comune") or "",
                "provincia": item.get("provincia") or "",
                "source": "google",
                "place_id": item.get("place_id"),
            }
        )
    return results
