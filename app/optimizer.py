import math, os, time, requests
from itertools import permutations
from datetime import datetime, timedelta, timezone
from .core.utils import LOCAL_TZ, local_now, parse_date_value, parse_time_value
from urllib.parse import quote

from sqlalchemy.orm import Session

from .services.geocoding import geocode_address
from .services.platform_settings import google_geocoding_enabled, google_routes_enabled, google_maps_api_key
from .services import distance_cache as dc

OSRM_URL = os.getenv("OSRM_URL", "https://router.project-osrm.org").rstrip("/")
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")

# V3.2 - Motore percorso con priorità alle finestre orarie di scarico.
# Logica principale:
# 1) prima cerca consegne fattibili nella fascia oraria;
# 2) se arriva prima, calcola attesa;
# 3) se una consegna rischia di chiudere, la anticipa;
# 4) distanza e velocità vengono considerate solo dopo la fattibilità oraria;
# 5) segnala "Non fattibile" solo quando non riesce davvero a rispettare gli orari.

def parse_hhmm(value):
    if not value:
        return None
    try:
        if hasattr(value, "hour") and hasattr(value, "minute"):
            return int(value.hour) * 60 + int(value.minute)
        parts = str(value).split(":")
        h, m = parts[0], parts[1] if len(parts) > 1 else "0"
        return int(h) * 60 + int(m)
    except Exception:
        return None

def fmt_hhmm(total_min):
    total_min = int(round(total_min)) % (24 * 60)
    return f"{total_min // 60:02d}:{total_min % 60:02d}"

def delivery_windows(d):
    """Restituisce le finestre orarie valide ordinate: [(start_min, end_min), ...]."""
    out = []

    a = parse_hhmm(d.get("scarico_mattina_da"))
    b = parse_hhmm(d.get("scarico_mattina_a"))
    if a is not None and b is not None and b > a:
        out.append((a, b))

    a = parse_hhmm(d.get("scarico_pomeriggio_da"))
    b = parse_hhmm(d.get("scarico_pomeriggio_a"))
    if a is not None and b is not None and b > a:
        out.append((a, b))

    return sorted(out)

def haversine_km(a, b):
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lon"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lon"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))

def geocode(address, db: Session | None = None):
    """Geocodifica deposito o indirizzo mancante.

    Con Google attivo usa esclusivamente Google Geocoding, così anche il
    deposito viene gestito con la stessa precisione dei clienti verificati.
    Se Google non è configurato, mantiene il vecchio fallback Nominatim per
    non bloccare installazioni locali senza chiave.
    """
    if google_geocoding_enabled(db) and google_maps_api_key(db):
        result = geocode_address(address, db=db)
        if result.get("lat") is not None and result.get("lon") is not None:
            return {"lat": float(result["lat"]), "lon": float(result["lon"])}
        raise ValueError(f"Indirizzo non trovato con Google: {address}")

    r = requests.get(
        f"{NOMINATIM_URL}/search",
        params={"format": "json", "limit": 1, "q": address},
        headers={"User-Agent": "ToolConsegneAziendale/3.2"},
        timeout=15
    )
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Indirizzo non trovato: {address}")
    return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}


def geocode_deposit(db: Session, deposit):
    """Restituisce le coordinate del deposito geocodificandolo solo la prima volta.

    In questo modo il deposito non consuma una chiamata Google a ogni calcolo giro.
    Le coordinate restano salvate sul deposito finché l'indirizzo non viene modificato.
    """
    if deposit.lat is not None and deposit.lon is not None:
        return {"lat": float(deposit.lat), "lon": float(deposit.lon)}

    coord = geocode(deposit.indirizzo, db=db)
    deposit.lat = coord["lat"]
    deposit.lon = coord["lon"]
    db.commit()
    return coord


def build_distance_matrix(db: Session, user_id: int, points, keys, start_time="08:00", route_date=None):
    """Costruisce la matrice tempi/distanze usando cache persistente.

    Google Routes viene chiamato solo per le coppie non ancora presenti in cache.
    Se tutte le coppie deposito/clienti sono già note, il calcolo non effettua
    alcuna nuova richiesta Google.
    """
    if not google_routes_enabled(db) or not google_maps_api_key(db):
        return None

    n = len(points)
    if n < 2:
        return {}

    departure = _route_departure_time_iso(start_time, route_date)
    keys = [f"{key}|departure={departure}" for key in keys]
    needed_pairs = [(i, j) for i in range(n) for j in range(n) if i != j]
    key_pairs = [(keys[i], keys[j]) for i, j in needed_pairs]
    cached = dc.get_pairs(db, user_id, key_pairs)

    index_matrix = {}
    missing = []
    for (i, j), key_pair in zip(needed_pairs, key_pairs):
        hit = cached.get(key_pair)
        if hit:
            index_matrix[(i, j)] = hit
        else:
            missing.append((i, j))

    if not missing:
        print(f"[ROUTES] Matrice interamente da cache: punti={n} tratte={len(needed_pairs)} chiamate_google=0")
        return index_matrix

    # Richiediamo a Google solo il sottoinsieme di punti coinvolti in tratte mancanti.
    origin_subset = sorted({i for i, _ in missing})
    dest_subset = sorted({j for _, j in missing})
    global_indices = origin_subset + [j for j in dest_subset if j not in origin_subset]
    sub_points = [points[i] for i in global_indices]
    local_of_global = {g: local for local, g in enumerate(global_indices)}

    sub_matrix = google_route_matrix(sub_points, start_time=start_time, db=db, route_date=route_date)
    if sub_matrix is None:
        return None

    to_save = []
    for gi in origin_subset:
        for gj in dest_subset:
            if gi == gj:
                continue
            local_leg = sub_matrix.get((local_of_global[gi], local_of_global[gj]))
            if not local_leg:
                continue
            index_matrix[(gi, gj)] = local_leg
            to_save.append((keys[gi], keys[gj], local_leg["km"], local_leg["min"]))

    dc.save_pairs(db, user_id, to_save)

    reused = len(needed_pairs) - len(missing)
    print(
        f"[ROUTES] Matrice parziale: punti_totali={n} punti_richiesti_a_google={len(sub_points)} "
        f"tratte_da_cache={reused} tratte_da_google={len(to_save)} chiamate_google=1"
    )

    for i, j in needed_pairs:
        if (i, j) not in index_matrix:
            raise ValueError("Google Routes non ha restituito una tratta necessaria. Verifica coordinate e copertura dell'indirizzo.")

    return index_matrix


def osrm_route(a, b):
    try:
        r = requests.get(
            f"{OSRM_URL}/route/v1/driving/{a['lon']},{a['lat']};{b['lon']},{b['lat']}",
            params={"overview": "false"},
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        if data.get("routes"):
            route = data["routes"][0]
            return {"km": route["distance"] / 1000, "min": route["duration"] / 60}
    except Exception:
        pass

    # Fallback: stima semplice se OSRM non risponde.
    km = haversine_km(a, b) * 1.25
    return {"km": km, "min": (km / 45) * 60}


def _google_duration_to_min(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return float(text) / 60.0
    except Exception:
        return None


def _route_departure_time_iso(start_time="08:00", route_date=None):
    """Use the actual company-local departure, serialized as UTC for Google."""
    day = parse_date_value(route_date) if route_date is not None else local_now().date()
    clock = parse_time_value(start_time)
    if day is None or clock is None:
        raise ValueError("Data o orario di partenza non valido")
    departure = datetime.combine(day, clock, tzinfo=LOCAL_TZ)
    utc = departure.astimezone(timezone.utc)
    if utc.astimezone(LOCAL_TZ).replace(tzinfo=None) != departure.replace(tzinfo=None):
        raise ValueError("Orario inesistente per il cambio dell'ora: scegli un altro orario")
    if utc <= local_now().astimezone(timezone.utc):
        raise ValueError("L'orario di partenza è già passato: scegli un orario futuro")
    return utc.isoformat().replace("+00:00", "Z")


def validate_vehicle_load(deliveries, vehicle=None):
    total_kg = 0.0
    total_packages = 0
    for delivery in deliveries:
        kg = float(delivery.get("peso_kg") or 0)
        packages = float(delivery.get("colli") or 0)
        if not math.isfinite(kg) or not math.isfinite(packages) or kg < 0 or packages < 0 or not packages.is_integer():
            raise ValueError("Peso e colli devono essere valori validi e non negativi; i colli devono essere interi")
        total_kg += kg
        total_packages += int(packages)
    if not vehicle:
        return
    for total, field, label in [(total_kg, "capacita_kg", "kg"), (total_packages, "capacita_colli", "colli")]:
        capacity = vehicle.get(field)
        if capacity is not None and total > float(capacity):
            raise ValueError(f"Capacità mezzo superata: {total:g} {label}, massimo {float(capacity):g}. Riduci il carico o scegli un altro mezzo.")


def google_route_matrix(points, start_time="08:00", db: Session | None = None, route_date=None):
    """Calcola una matrice tempi/distanze con Google Routes.

    Ritorna dict (origin_index, destination_index) -> {km, min}.
    Ogni punto deve avere lat/lon. Include anche deposito->clienti,
    cliente->cliente e cliente->deposito in una singola chiamata Google.
    """
    api_key = google_maps_api_key(db)
    if not google_routes_enabled(db) or not api_key:
        return None
    if len(points) < 2:
        return {}

    waypoints = []
    for p in points:
        waypoints.append({
            "waypoint": {
                "location": {
                    "latLng": {
                        "latitude": float(p["lat"]),
                        "longitude": float(p["lon"]),
                    }
                }
            }
        })

    body = {
        "origins": waypoints,
        "destinations": waypoints,
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": _route_departure_time_iso(start_time, route_date),
    }
    try:
        r = requests.post(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status,condition",
            },
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        rows = r.json()
        matrix = {}
        for item in rows:
            oi = item.get("originIndex")
            di = item.get("destinationIndex")
            if oi is None or di is None or oi == di:
                continue
            status = item.get("status") or {}
            if status and status.get("code") not in (0, None):
                continue
            minutes = _google_duration_to_min(item.get("duration"))
            meters = item.get("distanceMeters")
            if minutes is None or meters is None:
                continue
            matrix[(int(oi), int(di))] = {"km": float(meters) / 1000.0, "min": float(minutes)}
        print(f"[ROUTES] Google matrix OK punti={len(points)} archi={len(matrix)}")
        return matrix
    except Exception as e:
        print(f"[ROUTES] Errore Google Routes: {e}")
        raise ValueError("Google Routes non disponibile o non configurato correttamente. Controlla API key, Routes API e fatturazione Google Cloud.")




def google_route_polyline(points, return_depot=True, start_time="08:00", db: Session | None = None, route_date=None):
    """Restituisce la polyline stradale reale del giro usando Google Routes API.

    A differenza della vecchia linea tra coordinate, questa funzione chiede a
    Google il percorso DRIVE effettivo e ritorna l'encoded polyline da disegnare
    sulla mappa. L'ordine delle fermate NON viene ottimizzato qui: viene usato
    esattamente l'ordine gia' calcolato e salvato da GiroFacile.
    """
    api_key = google_maps_api_key(db)
    if not google_routes_enabled(db) or not api_key:
        return None
    if not points or len(points) < 2:
        return None

    clean_points = []
    for p in points:
        if p.get("lat") is None or p.get("lon") is None:
            return None
        clean_points.append({"lat": float(p["lat"]), "lon": float(p["lon"])})

    origin = clean_points[0]
    if return_depot:
        destination = clean_points[0]
        intermediate_points = clean_points[1:]
    else:
        destination = clean_points[-1]
        intermediate_points = clean_points[1:-1]

    def waypoint(p):
        return {
            "location": {
                "latLng": {
                    "latitude": p["lat"],
                    "longitude": p["lon"],
                }
            }
        }

    try:
        departure = _route_departure_time_iso(start_time, route_date)
    except ValueError:
        departure = None
    body = {
        "origin": waypoint(origin),
        "destination": waypoint(destination),
        "intermediates": [waypoint(p) for p in intermediate_points],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE" if departure else "TRAFFIC_UNAWARE",
        "computeAlternativeRoutes": False,
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
        **({"departureTime": departure} if departure else {}),
    }

    try:
        r = requests.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "routes.polyline.encodedPolyline,routes.distanceMeters,routes.duration",
            },
            json=body,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        encoded = ((routes[0].get("polyline") or {}).get("encodedPolyline"))
        if not encoded:
            return None
        return {
            "encoded_polyline": encoded,
            "distance_meters": routes[0].get("distanceMeters"),
            "duration": routes[0].get("duration"),
        }
    except Exception as e:
        print(f"[ROUTES] Errore polyline Google Routes: {e}")
        return None


def _matrix_leg(matrix, points, origin_idx, dest_idx):
    if matrix is not None:
        leg = matrix.get((origin_idx, dest_idx))
        if leg:
            return leg
        raise ValueError("Google Routes non ha restituito una tratta necessaria. Verifica coordinate e copertura dell'indirizzo.")
    return osrm_route(points[origin_idx], points[dest_idx])

def build_google_maps_url(depot_address, deliveries, return_depot):
    stops = [depot_address] + [d["indirizzo"] for d in deliveries]
    if return_depot:
        stops.append(depot_address)
    return "https://www.google.com/maps/dir/" + "/".join(quote(x) for x in stops)

def truthy_flag(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ["1", "true", "si", "sì", "yes", "y", "vero"]


def delivery_warnings(selected, vehicle=None):
    warnings = []
    if truthy_flag(selected.get("sponda")):
        if vehicle and not truthy_flag(vehicle.get("ha_sponda")):
            warnings.append("Serve sponda ma il mezzo selezionato non la possiede")
        else:
            warnings.append("Sponda richiesta")
    if truthy_flag(selected.get("ztl")):
        if vehicle and not truthy_flag(vehicle.get("accesso_ztl")):
            warnings.append("Cliente in ZTL: verificare accesso mezzo")
        else:
            warnings.append("Cliente in ZTL")
    return warnings


def evaluate_candidate(current_clock, leg, d):
    """
    Valuta una possibile prossima consegna.

    Ritorna:
    {
      feasible: bool,
      score: float,
      service_start: minuti assoluti del giorno,
      wait: minuti attesa,
      warning: testo,
      window_end: fine finestra usata o None
    }
    """
    travel_arrival = current_clock + leg["min"]
    service_min = float(d.get("tempo_scarico_min") or 0)
    windows = delivery_windows(d)

    # Se il cliente non ha finestre orarie, lo considero sempre fattibile.
    if not windows:
        return {
            "feasible": True,
            "score": leg["min"] + leg["km"] * 1.15,
            "service_start": travel_arrival,
            "wait": 0,
            "warning": "",
            "window_end": None,
        }

    best = None

    for start, end in windows:
        # Caso 1: arrivo prima dell'apertura -> posso aspettare.
        if travel_arrival < start:
            service_start = start
            wait = start - travel_arrival
            service_end = service_start + service_min
            feasible = service_end <= end
            slack = max(0, end - service_end)
            window_width = end - start

            if feasible:
                warning = f"Arrivo prima dell'apertura: attesa {int(round(wait))} min" if wait > 0 else ""
                # Score: finestre orarie prima, distanza dopo.
                # - attesa: costa, ma è accettabile
                # - slack basso: cliente rischia di chiudere, quindi va anticipato
                # - finestra stretta: va gestita prima
                score = (
                    wait * 1.6
                    + leg["min"] * 0.85
                    + leg["km"] * 1.05
                    + slack * 0.08
                    + window_width * 0.03
                )
            else:
                # Anche aspettando, lo scarico finirebbe dopo chiusura.
                late = service_end - end
                warning = "Scarico non completabile entro la fascia oraria"
                score = 50000 + late * 20 + leg["min"] + leg["km"]

        # Caso 2: arrivo durante la fascia.
        elif start <= travel_arrival <= end:
            service_start = travel_arrival
            wait = 0
            service_end = service_start + service_min
            feasible = service_end <= end
            slack = max(0, end - service_end)
            window_width = end - start

            if feasible:
                warning = ""
                # Cliente già aperto: molto preferibile.
                # Se sta per chiudere, lo score rimane basso per farlo prima.
                score = (
                    leg["min"] * 0.75
                    + leg["km"] * 1.0
                    + slack * 0.10
                    + window_width * 0.025
                )
            else:
                late = service_end - end
                warning = "Scarico terminerebbe dopo la chiusura"
                score = 40000 + late * 25 + leg["min"] + leg["km"]

        # Caso 3: sono già oltre questa fascia: provo la prossima.
        else:
            continue

        candidate = {
            "feasible": feasible,
            "score": score,
            "service_start": service_start,
            "wait": wait,
            "warning": warning,
            "window_end": end,
        }

        if best is None or candidate["score"] < best["score"]:
            best = candidate

    # Se nessuna fascia futura è utile, il cliente è non fattibile con l'orario attuale.
    if best is None:
        last_end = max(end for _, end in windows)
        late = max(0, travel_arrival - last_end)
        best = {
            "feasible": False,
            "score": 90000 + late * 30 + leg["min"] + leg["km"],
            "service_start": travel_arrival,
            "wait": 0,
            "warning": "Non fattibile: arrivo dopo le fasce orarie di scarico",
            "window_end": last_end,
        }

    # Piccola priorità a consegne pesanti/colli, ma solo dopo la fattibilità oraria.
    best["score"] -= float(d.get("peso_kg") or 0) * 0.01
    best["score"] -= float(d.get("colli") or 0) * 0.03

    return best

def _coord_from_delivery(delivery):
    try:
        if delivery.get("lat") is not None and delivery.get("lon") is not None:
            return {"lat": float(delivery["lat"]), "lon": float(delivery["lon"])}
    except Exception:
        pass
    return None


def _has_strong_constraints(deliveries):
    """Indica se nel giro ci sono vincoli logistici reali oltre alla strada.

    Se non ci sono finestre orarie, scarichi, ZTL o sponda, il motore deve
    comportarsi come un navigatore: cerca il minor tempo totale. Se invece ci
    sono vincoli, il tempo totale resta importante ma viene dopo la fattibilità.
    """
    for d in deliveries:
        if delivery_windows(d):
            return True
        if float(d.get("tempo_scarico_min") or 0) > 0:
            return True
        if truthy_flag(d.get("ztl")) or truthy_flag(d.get("sponda")):
            return True
    return False


def _evaluate_fixed_sequence(sequence, matrix, points, vehicle=None, return_depot=True, start_time="08:00"):
    """Valuta un ordine già deciso usando una sola matrice Google.

    Questa funzione non richiama Google: usa soltanto i tempi/distanze già
    presenti nella matrice. Serve per provare molte combinazioni internamente
    senza aumentare le richieste Google.
    """
    ordered = []
    total_km = 0.0
    total_wait = 0.0
    violations = 0
    warning_count = 0
    start_clock = parse_hhmm(start_time) or 8 * 60
    current_clock = start_clock
    current_idx = 0

    for original in sequence:
        selected = dict(original)
        leg = _matrix_leg(matrix, points, current_idx, selected["_matrix_index"])
        ev = evaluate_candidate(current_clock, leg, selected)

        warnings = []
        if ev.get("warning"):
            warnings.append(ev["warning"])
        warnings.extend(delivery_warnings(selected, vehicle))

        if not ev.get("feasible", True):
            violations += 1
        if warnings:
            warning_count += len(warnings)

        service_start = ev["service_start"]
        service_end = service_start + float(selected.get("tempo_scarico_min") or 0)

        selected["ordine"] = len(ordered) + 1
        selected["km_tappa"] = round(leg["km"], 2)
        selected["minuti_tappa"] = round(leg["min"], 1)
        selected["attesa_min"] = round(ev.get("wait") or 0, 1)
        selected["arrivo_stimato"] = fmt_hhmm(service_start)
        selected["partenza_stimata"] = fmt_hhmm(service_end)
        selected["warning"] = "; ".join(warnings) if warnings else ""

        total_km += leg["km"]
        total_wait += float(ev.get("wait") or 0)
        current_clock = service_end
        current_idx = selected["_matrix_index"]
        ordered.append(selected)

    if return_depot and ordered:
        back = _matrix_leg(matrix, points, current_idx, 0)
        total_km += back["km"]
        current_clock += back["min"]

    total_min = current_clock - start_clock
    has_constraints = _has_strong_constraints(sequence)

    if has_constraints:
        # Prima la fattibilità, poi il tempo, poi attese/distanza.
        score = violations * 100000 + total_min * 10 + total_wait * 1.5 + warning_count * 25 + total_km
    else:
        # Senza vincoli il giro deve essere il più simile possibile a Maps:
        # tempo totale prima, km come secondo criterio.
        score = total_min * 10 + total_km

    for d in ordered:
        d.pop("_matrix_index", None)

    return {
        "ordered": ordered,
        "total_km": round(total_km, 2),
        "total_min": round(total_min, 1),
        "return_time": fmt_hhmm(current_clock),
        "score": score,
        "violations": violations,
        "total_wait": round(total_wait, 1),
    }


def _greedy_sequence(deliveries, matrix, points, vehicle=None, start_time="08:00"):
    """Crea un primo ordine rapido, utile come base per giri grandi."""
    remaining = deliveries[:]
    ordered = []
    current_idx = 0
    current_clock = parse_hhmm(start_time) or 8 * 60

    while remaining:
        best_idx = 0
        best_score = None
        best_eval = None
        best_leg = None
        for idx, d in enumerate(remaining):
            leg = _matrix_leg(matrix, points, current_idx, d["_matrix_index"])
            ev = evaluate_candidate(current_clock, leg, d)
            score = ev["score"]
            if best_score is None or score < best_score:
                best_idx = idx
                best_score = score
                best_eval = ev
                best_leg = leg
        selected = remaining.pop(best_idx)
        ordered.append(selected)
        service_start = best_eval["service_start"]
        current_clock = service_start + float(selected.get("tempo_scarico_min") or 0)
        current_idx = selected["_matrix_index"]

    return ordered


def _local_optimize_sequence(initial_sequence, matrix, points, vehicle=None, return_depot=True, start_time="08:00", max_rounds=4):
    """Migliora un ordine provando scambi e inversioni senza nuove chiamate Google."""
    best_sequence = initial_sequence[:]
    best_result = _evaluate_fixed_sequence(best_sequence, matrix, points, vehicle, return_depot, start_time)
    n = len(best_sequence)
    improved = True
    rounds = 0

    while improved and rounds < max_rounds:
        improved = False
        rounds += 1

        # Swap di due fermate.
        for i in range(n - 1):
            for j in range(i + 1, n):
                candidate = best_sequence[:]
                candidate[i], candidate[j] = candidate[j], candidate[i]
                result = _evaluate_fixed_sequence(candidate, matrix, points, vehicle, return_depot, start_time)
                if result["score"] + 0.0001 < best_result["score"]:
                    best_sequence = candidate
                    best_result = result
                    improved = True

        # 2-opt leggero: inverte segmenti consecutivi.
        for i in range(n - 2):
            for j in range(i + 2, n):
                candidate = best_sequence[:i] + list(reversed(best_sequence[i:j + 1])) + best_sequence[j + 1:]
                result = _evaluate_fixed_sequence(candidate, matrix, points, vehicle, return_depot, start_time)
                if result["score"] + 0.0001 < best_result["score"]:
                    best_sequence = candidate
                    best_result = result
                    improved = True

    return best_result


def _best_internal_sequence(deliveries, matrix, points, vehicle=None, return_depot=True, start_time="08:00"):
    """Sceglie il miglior ordine usando una sola chiamata Google Routes.

    - Fino a 8 consegne prova tutte le combinazioni: risultato quasi ottimale.
    - Oltre 8 consegne usa un ordine iniziale + miglioramento locale.
    """
    n = len(deliveries)
    if n == 0:
        return _evaluate_fixed_sequence([], matrix, points, vehicle, return_depot, start_time)

    if n <= 8:
        best = None
        checked = 0
        for seq in permutations(deliveries):
            checked += 1
            result = _evaluate_fixed_sequence(list(seq), matrix, points, vehicle, return_depot, start_time)
            if best is None or result["score"] < best["score"]:
                best = result
        print(f"[OPTIMIZER] Ottimizzazione completa: fermate={n} combinazioni={checked} tempo={best['total_min']} min km={best['total_km']}")
        return best

    initial = _greedy_sequence(deliveries, matrix, points, vehicle, start_time)
    result = _local_optimize_sequence(initial, matrix, points, vehicle, return_depot, start_time)
    print(f"[OPTIMIZER] Ottimizzazione locale: fermate={n} tempo={result['total_min']} min km={result['total_km']}")
    return result


def optimize_route(db: Session, deposit, deliveries, vehicle=None, return_depot=True, start_time="08:00", route_date=None):
    validate_vehicle_load(deliveries, vehicle)
    _route_departure_time_iso(start_time, route_date)
    depot_coord = geocode_deposit(db, deposit)

    missing = []
    for d in deliveries:
        saved = _coord_from_delivery(d)
        if saved:
            d["coord"] = saved
        else:
            missing.append(d.get("cliente_nome") or d.get("indirizzo") or "Cliente")
    if missing:
        raise ValueError("Clienti senza coordinate Google valide: " + ", ".join(missing[:8]) + ". Apri il cliente e usa “Verifica indirizzo con Google”.")

    points = [depot_coord] + [d["coord"] for d in deliveries]
    user_id = int(getattr(deposit, "user_id", 0) or 0)
    keys = [dc.deposit_key(deposit.id, user_id=user_id)] + [
        dc.point_key(customer_id=d.get("customer_id"), lat=d["coord"]["lat"], lon=d["coord"]["lon"], user_id=user_id)
        for d in deliveries
    ]
    for idx, d in enumerate(deliveries, start=1):
        d["_matrix_index"] = idx

    matrix = build_distance_matrix(db, user_id, points, keys, start_time=start_time, route_date=route_date)

    result = _best_internal_sequence(deliveries, matrix, points, vehicle, return_depot, start_time)

    for d in deliveries:
        d.pop("_matrix_index", None)

    result.pop("score", None)
    result.pop("violations", None)
    result.pop("total_wait", None)
    result["google_maps_url"] = build_google_maps_url(deposit.indirizzo, result["ordered"], return_depot)
    return result

def recalculate_manual_route(db: Session, deposit, deliveries, vehicle=None, return_depot=True, start_time="08:00", route_date=None):
    """Ricalcola km, tempi e orari rispettando l'ordine scelto manualmente dall'utente."""
    validate_vehicle_load(deliveries, vehicle)
    _route_departure_time_iso(start_time, route_date)
    depot_coord = geocode_deposit(db, deposit)
    missing = []
    for d in deliveries:
        saved = _coord_from_delivery(d)
        if saved:
            d["coord"] = saved
        else:
            missing.append(d.get("cliente_nome") or d.get("indirizzo") or "Cliente")
    if missing:
        raise ValueError("Clienti senza coordinate Google valide: " + ", ".join(missing[:8]) + ". Apri il cliente e usa “Verifica indirizzo con Google”.")

    points = [depot_coord] + [d["coord"] for d in deliveries]
    user_id = int(getattr(deposit, "user_id", 0) or 0)
    keys = [dc.deposit_key(deposit.id, user_id=user_id)] + [
        dc.point_key(customer_id=d.get("customer_id"), lat=d["coord"]["lat"], lon=d["coord"]["lon"], user_id=user_id)
        for d in deliveries
    ]
    for idx, d in enumerate(deliveries, start=1):
        d["_matrix_index"] = idx
    matrix = build_distance_matrix(db, user_id, points, keys, start_time=start_time, route_date=route_date)

    ordered = []
    total_km = 0.0
    start_clock = parse_hhmm(start_time) or 8 * 60
    current_clock = start_clock
    current_idx = 0

    for selected in deliveries:
        leg = _matrix_leg(matrix, points, current_idx, selected["_matrix_index"])
        ev = evaluate_candidate(current_clock, leg, selected)
        warnings = []
        if ev.get("warning"):
            warnings.append(ev["warning"])
        warnings.extend(delivery_warnings(selected, vehicle))

        service_start = ev["service_start"]
        service_end = service_start + float(selected.get("tempo_scarico_min") or 0)
        selected["ordine"] = len(ordered) + 1
        selected["km_tappa"] = round(leg["km"], 2)
        selected["minuti_tappa"] = round(leg["min"], 1)
        selected["attesa_min"] = round(ev.get("wait") or 0, 1)
        selected["arrivo_stimato"] = fmt_hhmm(service_start)
        selected["partenza_stimata"] = fmt_hhmm(service_end)
        selected["warning"] = "; ".join(warnings) if warnings else ""
        total_km += leg["km"]
        current_clock = service_end
        current_idx = selected["_matrix_index"]
        selected.pop("_matrix_index", None)
        ordered.append(selected)

    if return_depot and ordered:
        back = _matrix_leg(matrix, points, current_idx, 0)
        total_km += back["km"]
        current_clock += back["min"]

    total_min = current_clock - start_clock
    return {
        "ordered": ordered,
        "total_km": round(total_km, 2),
        "total_min": round(total_min, 1),
        "return_time": fmt_hhmm(current_clock),
        "google_maps_url": build_google_maps_url(deposit.indirizzo, ordered, return_depot),
    }
