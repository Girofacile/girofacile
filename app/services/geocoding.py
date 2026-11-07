"""
Servizio geocodifica indirizzi.
Modalità Google-only: usa esclusivamente Google Maps Geocoding.
Geoapify e Nominatim sono disattivati per evitare fallback non desiderati.
"""
from datetime import datetime
from ..core.clock import utc_now

import re
import time
import unicodedata
import requests
from .api_usage import log_api_usage

from sqlalchemy.orm import Session

from ..services.platform_settings import google_geocoding_enabled, google_maps_api_key


class GeocodingUnavailable(RuntimeError):
    pass


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


def _google_geocode(query: str, limit: int = 5, db: Session | None = None, user_id=None, strict=False,
                   api_key: str | None = None, usage: list | None = None) -> list:
    """Esegue una richiesta Google Geocoding e normalizza i risultati.

    Per le verifiche in parallelo la chiave arriva già letta (api_key) e l'uso dell'API
    si annota in `usage` invece che nel database: lo registra poi il thread principale.
    """
    if api_key is None:
        api_key = google_maps_api_key(db) if google_geocoding_enabled(db) else ""
    if not api_key:
        print("[GEOCODING] Google disattivato o chiave Google mancante")
        if strict: raise GeocodingUnavailable('Servizio di verifica indirizzi non disponibile. Riprova più tardi.')
        return []

    started, outcome, message = time.perf_counter(), "failed", "Geocodifica non disponibile"
    try:
        r = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": query,
                "region": "it",
                "components": "country:IT",
                "language": "it",
                "key": api_key,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        message = str(status or "unknown")[:80]
        outcome = "success" if status in ("OK", "ZERO_RESULTS") else "failed"
        if strict and status not in ('OK','ZERO_RESULTS'):
            raise GeocodingUnavailable('Servizio di verifica indirizzi temporaneamente non disponibile. Riprova.')
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
            cap = ""
            places = []
            routes = []
            street_number = ""
            for comp in components:
                types = comp.get("types") or []
                if "route" in types:
                    routes += [comp.get("long_name", ""), comp.get("short_name", "")]
                if "street_number" in types:
                    street_number = street_number or comp.get("long_name", "")
                if "locality" in types or "postal_town" in types or "administrative_area_level_3" in types:
                    comune = comune or comp.get("long_name", "")
                    places.append(comp.get("long_name", ""))
                if "administrative_area_level_2" in types:
                    provincia = provincia or comp.get("long_name", "")
                if "postal_code" in types:
                    cap = cap or comp.get("long_name", "")

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
                "cap": cap,
                "places": [p for p in places if p],
                "routes": [r for r in routes if r],
                "street_number": street_number,
                "partial_match": bool(item.get("partial_match")),
            })
        print(f"[GEOCODING] Google risultati={len(results)} query={query}")
        return results
    except Exception as e:
        if strict: raise GeocodingUnavailable('Servizio di verifica indirizzi temporaneamente non disponibile. Riprova.') from e
        print(f"[GEOCODING] Errore Google: {type(e).__name__}")
        return []
    finally:
        entry = dict(user_id=user_id, provider="google", service="google_geocoding",
                     action="Geocodifica indirizzo", endpoint="/maps/api/geocode/json",
                     status=outcome, message=message, response_ms=int((time.perf_counter() - started) * 1000))
        if usage is not None:
            usage.append(entry)
        elif db is not None:
            log_api_usage(db, **entry)


def _plain(value: str) -> str:
    text_value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", text_value).split()) + " "


def matches_request(query: str, result: dict) -> bool:
    """Il risultato deve stare nel CAP o nel comune scritti dall'utente.

    Con un CAP nell'indirizzo basta che coincida il CAP oppure il comune (le grandi città
    hanno molti CAP). Senza CAP si accetta un comune citato o una corrispondenza completa.
    Un risultato senza comune vale solo se Google lo dà come corrispondenza completa: con
    corrispondenza parziale è una via omonima qualsiasi («Via Roma, Italia» per «Via Roma 10,
    Casoria» finiva nelle Marche e risultava verificato).
    """
    written = _plain(query)
    place_ok = any(_plain(place) in written for place in result.get("places") or [])
    caps = re.findall(r"(?<!\d)\d{5}(?!\d)", str(query or ""))
    if caps:
        return place_ok or (result.get("cap") or "") in caps
    if not result.get("places"):
        return not result.get("partial_match")
    return place_ok or not result.get("partial_match")


# Parole del tipo di strada e articoli: non distinguono una via dall'altra («V. Nazionale» = «Via Nazionale»).
_STREET_TYPES = set("""via v viale vle v le corso cso c so piazza pza p za pzza p zza piazzale largo lgo l go
    vico vicolo strada str contrada c da cda localita loc traversa trav rione borgo salita discesa
    lungomare circonvallazione parco frazione fraz statale provinciale comunale sp ss sr
    di de del della dello dei degli delle d la le lo il gli i l snc sn""".split())


def _street_tokens(value: str) -> list:
    return [t for t in _plain(value).split() if t not in _STREET_TYPES and not t.isdigit()]


def parse_address(query: str) -> dict:
    """Via, civico, CAP e comune da un indirizzo su una riga («Via Roma 10, 80026 Casoria NA»)."""
    parts = [p.strip() for p in str(query or "").split(",") if p.strip()]
    parts = [p for p in parts if _plain(p).strip() not in ("italia", "italy")]
    caps = re.findall(r"(?<!\d)\d{5}(?!\d)", str(query or ""))
    street = parts[0] if parts else ""
    number = None
    match = re.match(r"^(.*?)[\s,]+(\d+\s*[a-zA-Z]?(?:\s*/\s*\w+)?)$", street)
    # Civico seguito dal comune senza virgola: «piazza giovanni leone 22 pomigliano».
    middle = None if match else re.match(r"^(.*?\D)\s+(\d+\s*[a-zA-Z]?(?:\s*/\s*\w+)?)\s+([^\d].*)$", street)
    if match:
        street, number = match.group(1).strip(), match.group(2)
    elif middle:
        street, number = middle.group(1).strip(), middle.group(2)
        parts = parts[:1] + [middle.group(3)] + parts[1:]
    elif len(parts) > 1 and re.fullmatch(r"\d+\s*[a-zA-Z]?(?:\s*/\s*\w+)?", parts[1]):
        number = parts[1]
    town = ""
    for part in parts[1:]:
        if re.fullmatch(r"\d+\s*[a-zA-Z]?(?:\s*/\s*\w+)?", part):
            continue
        text = re.sub(r"(?<!\d)\d{5}(?!\d)", " ", part)
        text = re.sub(r"\s+[A-Z]{2}$", "", text.strip())  # sigla della provincia
        if text.strip():
            town = text.strip()
    return {"street": street, "number": number, "cap": caps[0] if caps else None, "town": town}


def _same_street(written: str, routes: list) -> bool:
    """Le parole significative della via scritta stanno nella via di Google (o viceversa)."""
    mine = _street_tokens(written)
    if not mine:
        return False
    for route in routes:
        theirs = _street_tokens(route)
        if not theirs:
            continue
        small, large = (mine, theirs) if len(mine) <= len(theirs) else (theirs, mine)
        def found(token):
            return any(token == other or (len(token) == 1 and other.startswith(token))
                       or (len(other) == 1 and token.startswith(other)) for other in large)
        if all(found(token) for token in small):
            return True
    return False


def _same_number(written, found) -> bool:
    digits = lambda value: (re.match(r"\d+", str(value or "").strip()) or [None])[0]
    return bool(digits(written)) and digits(written) == digits(found)


def check_result(query: str, result: dict):
    """Motivo per cui il risultato NON va verificato da solo; None se coincide tutto.

    Verificato solo se: comune (o CAP) scritto e ritrovato, stessa via, stesso civico quando
    c'è, posizione sul civico o interpolata. Altrimenti decide una persona sulla mappa.
    """
    written = parse_address(query)
    if not (written["town"] or written["cap"]) or not result.get("places") or not matches_request(query, result):
        return "altro_comune"
    if not result.get("routes"):
        return "approssimativo"  # Google ha trovato solo il comune o la zona
    if not _same_street(written["street"], result["routes"]):
        return "via_diversa"
    if written["number"] and not _same_number(written["number"], result.get("street_number")):
        return "via_diversa"
    if not written["number"] or result.get("location_type") not in ("ROOFTOP", "RANGE_INTERPOLATED"):
        return "approssimativo"
    return None


def geocode_address(indirizzo: str, comune: str = "", provincia: str = "", db: Session | None = None, user_id=None, strict=False,
                    api_key: str | None = None, usage: list | None = None) -> dict:
    """
    Geocodifica un indirizzo usando solo Google.
    Ritorna dict con: status, lat, lon, formatted, source, confidence.
    """
    query = ", ".join(
        x for x in [normalize_address(indirizzo), comune, provincia, "Italia"] if x
    )

    options={'strict':True} if strict else {}
    if api_key is not None: options['api_key']=api_key
    if usage is not None: options['usage']=usage
    results = _google_geocode(query, limit=5, db=db, user_id=user_id, **options)
    if not results:
        return {"status": "non_trovato", "source": "google"}

    # Verificato solo il risultato che coincide in tutto con quanto scritto (comune o CAP, via,
    # civico, precisione). Google può restituire la stessa via in un altro comune (Brusciano →
    # Orosei) o una via omonima senza comune («Via Roma, Italia» per Casoria): restano da verificare.
    checks = [(item, check_result(query, item)) for item in results]
    exact = next((item for item, problem in checks if problem is None), None)
    if exact is not None:
        best, reason = exact, None
    else:
        # Proposta da mostrare: prima un risultato nel comune giusto, poi il primo.
        order = ("via_diversa", "approssimativo", "altro_comune")
        best, reason = min(checks, key=lambda pair: order.index(pair[1]))
    try:
        conf = float(best.get("confidence") or 0.5)
    except Exception:
        conf = 0.5
    status = "verificato" if reason is None else "da_verificare"
    return {
        "status": status,
        "reason": reason,
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
        db=db, user_id=getattr(customer, "user_id", None),
    )


def apply_geocode(customer, result: dict):
    customer.stato_geocodifica = result.get("status", "non_trovato")
    customer.lat = result.get("lat")
    customer.lon = result.get("lon")
    customer.indirizzo_geocodificato = result.get("formatted")
    customer.fonte_geocodifica = result.get("source")
    customer.google_place_id = result.get("place_id")
    customer.affidabilita_geocodifica = result.get("confidence")
    customer.geocodificato_il = utc_now()
    # L’avviso pedonale si registra assieme alla posizione confermata.
    # Il controllo usa solo l’archivio locale: nessuna chiamata Google aggiuntiva.
    from .ztl import detect_pedestrian
    customer.pedestrian_area = (result.get("status") == "verificato"
                                and detect_pedestrian(customer.lat, customer.lon)["detected"])


def geocoding_key(db: Session | None = None) -> str:
    """Chiave Google da usare, oppure "" se la geocodifica è spenta."""
    return google_maps_api_key(db) if google_geocoding_enabled(db) else ""


def search_address_autocomplete(
    q: str, comune: str = "", provincia: str = "", db: Session | None = None, user_id=None
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

    google_results = _google_geocode(text, limit=7, db=db, user_id=user_id)
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
