import math, os, time, requests
from itertools import permutations
from datetime import datetime, timedelta, timezone
from .core.utils import LOCAL_TZ, local_now, parse_date_value, parse_time_value
from urllib.parse import quote

from sqlalchemy.orm import Session

from .services.geocoding import geocode_address
from .services.platform_settings import google_geocoding_enabled, google_maps_api_key
from .services import road_routing
from .services import distance_cache as dc

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

def _start_clock(start_time):
    # Midnight is a valid zero; only a missing/unparseable value uses the fallback.
    parsed = parse_hhmm(start_time)
    return 8 * 60 if parsed is None else parsed


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

def geocode(address, db: Session | None = None, user_id=None):
    """Geocodifica deposito o indirizzo mancante.

    Con Google attivo usa esclusivamente Google Geocoding, così anche il
    deposito viene gestito con la stessa precisione dei clienti verificati.
    Se Google non è configurato, mantiene il vecchio fallback Nominatim per
    non bloccare installazioni locali senza chiave.
    """
    if google_geocoding_enabled(db) and google_maps_api_key(db):
        result = geocode_address(address, db=db, user_id=user_id)
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

    coord = geocode(deposit.indirizzo, db=db, user_id=deposit.user_id)
    deposit.lat = coord["lat"]
    deposit.lon = coord["lon"]
    db.commit()
    return coord


def build_distance_matrix(db: Session, user_id: int, points, keys, start_time="08:00", route_date=None):
    """A date-independent OSRM/cache matrix; every search uses these same legs."""
    return road_routing.build_matrix(db, user_id, points, keys)


def osrm_route(a, b):
    """Compatibility helper for callers outside the optimizer."""
    legs = road_routing.osrm_table([a, b], pairs=[(0, 1)])
    return legs.get((0, 1)) or road_routing.estimated_leg(a, b)


def _route_departure_time_iso(start_time="08:00", route_date=None):
    """Use the actual company-local departure, serialized as UTC for traffic providers."""
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


def _matrix_leg(matrix, points, origin_idx, dest_idx):
    if matrix is not None:
        leg = matrix.get((origin_idx, dest_idx))
        if leg:
            return leg
        raise ValueError("Matrice stradale incompleta. Verifica coordinate e copertura dell'indirizzo.")
    return road_routing.estimated_leg(points[origin_idx], points[dest_idx])

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


def evaluate_candidate(current_clock, leg, d, *, windows=None):
    """
    Valuta una possibile prossima consegna.

    Ritorna:
    {
      feasible: bool,
      score: float (historical diagnostic),
      priority: tuple (feasibility, distance, duration, waiting),
      service_start: minuti assoluti del giorno,
      wait: minuti attesa,
      warning: testo,
      window_end: fine finestra usata o None
    }
    """
    travel_arrival = current_clock + leg["min"]
    service_min = float(d.get("tempo_scarico_min") or 0)
    windows = delivery_windows(d) if windows is None else windows

    # Se il cliente non ha finestre orarie, lo considero sempre fattibile.
    if not windows:
        return {
            "feasible": True,
            "score": leg["min"] + leg["km"] * 1.15,
            "priority": (False, 0, leg["km"], leg["min"], 0, math.inf),
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
                # Historical diagnostic; the explicit priority below selects
                # feasible candidates by distance, then time and waiting.
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
                # Historical diagnostic only, not the feasible search key.
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

        # For a fixed leg, earliest feasible service dominates later service.
        candidate["priority"] = (not feasible, 0 if feasible else score,
                                 leg["km"], leg["min"] + wait, wait, end)
        if best is None or candidate["priority"] < best["priority"]:
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

    # Preserve the historical score for infeasible candidates/diagnostics only.
    best["score"] -= float(d.get("peso_kg") or 0) * 0.01
    best["score"] -= float(d.get("colli") or 0) * 0.03

    if not best["feasible"]:
        best["priority"] = (True, best["score"], leg["km"], leg["min"] + best["wait"], best["wait"], best["window_end"])
    return best

def _coord_from_delivery(delivery):
    try:
        if delivery.get("lat") is not None and delivery.get("lon") is not None:
            return {"lat": float(delivery["lat"]), "lon": float(delivery["lon"])}
    except Exception:
        pass
    return None


def _has_strong_constraints(deliveries):
    """Identify constraints for the historical diagnostic score only."""
    for d in deliveries:
        if delivery_windows(d):
            return True
        if float(d.get("tempo_scarico_min") or 0) > 0:
            return True
        if truthy_flag(d.get("ztl")) or truthy_flag(d.get("sponda")):
            return True
    return False


def _earliest_feasible_candidate(clock, leg, delivery):
    """Earliest feasible service for the exact feasibility fallback (same-day windows)."""
    windows = delivery_windows(delivery)
    arrival = clock + leg["min"]
    service = float(delivery.get("tempo_scarico_min") or 0)
    slots = [(max(arrival, a), b) for a, b in windows if max(arrival, a) + service <= b]
    if not windows or not slots:
        return evaluate_candidate(clock, leg, delivery)
    start, end = min(slots)
    wait = start - arrival
    return {"feasible": True, "service_start": start, "wait": wait, "window_end": end,
            "warning": f"Arrivo prima dell'apertura: attesa {int(round(wait))} min" if wait else ""}


def _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, best, evaluator=None):
    """Exact feasibility DP for up to 15 selected stops, only if search found none.

    Earliest completion dominates later completion at the same (subset, last):
    waiting is allowed and matrix travel times are fixed. Retain parents to
    reconstruct a witness, not a claim of optimal duration/distance.
    """
    evaluate = evaluator or _evaluate_fixed_sequence
    n = len(deliveries)
    if not best["violations"] or n > 15 or not n:
        return best
    states = {(0, -1): (_start_clock(start_time), None)}
    for mask in range(1 << n):
        for last in range(-1, n):
            state = states.get((mask, last))
            if state is None:
                continue
            clock = state[0]
            origin = 0 if last == -1 else deliveries[last]["_matrix_index"]
            for nxt, delivery in enumerate(deliveries):
                bit = 1 << nxt
                if mask & bit:
                    continue
                leg = _matrix_leg(matrix, points, origin, delivery["_matrix_index"])
                ev = _earliest_feasible_candidate(clock, leg, delivery)
                if not ev["feasible"]:
                    continue
                end = ev["service_start"] + float(delivery.get("tempo_scarico_min") or 0)
                key = (mask | bit, nxt)
                if key not in states or end < states[key][0]:
                    states[key] = (end, (mask, last))
    terminals = [key for key in states if key[0] == (1 << n) - 1]
    if not terminals:
        return best  # Still return the least-late searched route; never block planning.
    for key in terminals:
        sequence = []
        while key[1] != -1:
            sequence.append(deliveries[key[1]])
            key = states[key][1]
        candidate = evaluate(sequence[::-1], matrix, points, vehicle, return_depot, start_time, earliest_windows=True)
        if solution_key(candidate) < solution_key(best):
            best = candidate
    return best


def solution_key(result):
    """Absolute feasibility, then distance, duration, waiting and warnings.

    Infeasible routes retain the historical lateness/count/score ordering.
    Constant vehicle consumption is proportional to km, not a separate weight.
    Raw totals avoid letting display rounding override a distance improvement.
    """
    violations = result["violations"]
    if violations:
        return (True, result["total_lateness_min"], violations, result["score"])
    return (False, *result.get("_objective", (
        result["total_km"], result["total_min"], result.get("total_wait", 0), 0)))


def stop_timing_details(delivery, arrival, service_start, service_end, window_end=None):
    windows = delivery_windows(delivery)
    if window_end is None and windows:
        # Reconstruct saved schedules from their persisted leg/wait/service times.
        eligible = [(a, b) for a, b in windows if a <= service_start]
        window_end = max(b for a, b in (eligible or windows[:1]))
    chosen = next(((a, b) for a, b in windows if b == window_end), None)
    lateness = max(0.0, service_end - window_end) if window_end is not None else 0.0
    detail = {
        "customer_id": delivery.get("customer_id"), "cliente_nome": delivery.get("cliente_nome"),
        "ordine": delivery.get("ordine"),
        "requested_windows": [{"start": fmt_hhmm(a), "end": fmt_hhmm(b)} for a, b in windows],
        "window": {"start": fmt_hhmm(chosen[0]), "end": fmt_hhmm(chosen[1])} if chosen else None,
        "arrivo_fisico": fmt_hhmm(arrival), "inizio_servizio": fmt_hhmm(service_start),
        "fine_servizio": fmt_hhmm(service_end), "lateness_min": lateness,
        "warning": f"Finestra oraria non rispettata: scarico oltre la chiusura di {lateness:.1f} min" if lateness else "",
    }
    return {"arrivo_fisico": detail["arrivo_fisico"], "inizio_servizio": detail["inizio_servizio"],
            "lateness_min": lateness, "time_window_violation": detail if lateness > 0 else None}


def window_summary(ordered):
    violations = [d["time_window_violation"] for d in ordered if d.get("time_window_violation")]
    return {"violations_count": len(violations),
            "total_lateness_min": sum(v["lateness_min"] for v in violations),
            "total_wait_min": round(sum(float(d.get("attesa_min") or 0) for d in ordered), 1),
            "time_window_violations": violations}


def enrich_saved_schedule(ordered, start_time):
    """Reconstruct legacy diagnostics without routing, at stored precision."""
    clock = _start_clock(start_time)
    for d in ordered:
        arrival = clock + float(d.get("minuti_tappa") or 0)
        start = arrival + float(d.get("attesa_min") or 0)
        clock = start + float(d.get("tempo_scarico_min") or 0)
        d.update(stop_timing_details(d, arrival, start, clock))
    return window_summary(ordered)


def _evaluate_fixed_sequence(sequence, matrix, points, vehicle=None, return_depot=True, start_time="08:00", include_details=True, earliest_windows=False):
    """Valuta un ordine già deciso usando la matrice stradale OSRM/cache.

    arrivo_stimato rappresenta l'inizio servizio dopo l'eventuale attesa.

    Questa funzione non richiama provider: usa soltanto i tempi/distanze già
    presenti nella matrice. Serve per provare molte combinazioni internamente
    senza nuove richieste di routing.
    """
    ordered = []
    total_km = 0.0
    total_wait = 0.0
    total_lateness = 0.0
    violations = 0
    warning_count = 0
    start_clock = _start_clock(start_time)
    current_clock = start_clock
    current_idx = 0

    for original in sequence:
        selected = dict(original)
        leg = _matrix_leg(matrix, points, current_idx, selected["_matrix_index"])
        ev = (_earliest_feasible_candidate if earliest_windows else evaluate_candidate)(current_clock, leg, selected)

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
        if ev.get("window_end") is not None:
            total_lateness += max(0.0, service_end - ev["window_end"])
        if include_details:
            selected.update(stop_timing_details(selected, current_clock + leg["min"], service_start, service_end, ev.get("window_end")))

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
        # Historical diagnostic only; solution_key controls the search.
        score = violations * 100000 + total_min * 10 + total_wait * 1.5 + warning_count * 25 + total_km
    else:
        # Retained for historical benchmark comparisons, never feasible ranking.
        score = total_min * 10 + total_km

    for d in ordered:
        d.pop("_matrix_index", None)

    return {
        "ordered": ordered,
        "total_km": round(total_km, 2),
        "total_min": round(total_min, 1),
        "return_time": fmt_hhmm(current_clock),
        "score": score,
        "_objective": (total_km, total_min, total_wait, warning_count),
        "violations": violations,
        "total_wait": round(total_wait, 1),
        **(window_summary(ordered) if include_details else {"total_lateness_min": total_lateness}),
    }


def _greedy_sequence(deliveries, matrix, points, vehicle=None, start_time="08:00"):
    """Crea un primo ordine rapido, utile come base per giri grandi."""
    remaining = deliveries[:]
    ordered = []
    current_idx = 0
    current_clock = _start_clock(start_time)

    while remaining:
        best_idx = 0
        best_score = None
        best_eval = None
        best_leg = None
        for idx, d in enumerate(remaining):
            leg = _matrix_leg(matrix, points, current_idx, d["_matrix_index"])
            ev = evaluate_candidate(current_clock, leg, d)
            score = ev["priority"]
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


def _local_optimize_sequence(initial_sequence, matrix, points, vehicle=None, return_depot=True, start_time="08:00", max_rounds=4, relocate=False, evaluator=None):
    """Migliora un ordine provando scambi e inversioni senza nuove chiamate di routing."""
    evaluate = evaluator or _evaluate_fixed_sequence
    best_sequence = initial_sequence[:]
    best_result = evaluate(best_sequence, matrix, points, vehicle, return_depot, start_time, include_details=False)
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
                result = evaluate(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
                if solution_key(result) < solution_key(best_result):
                    best_sequence = candidate
                    best_result = result
                    improved = True

        # 2-opt leggero: inverte segmenti consecutivi.
        for i in range(n - 2):
            for j in range(i + 2, n):
                candidate = best_sequence[:i] + list(reversed(best_sequence[i:j + 1])) + best_sequence[j + 1:]
                result = evaluate(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
                if solution_key(result) < solution_key(best_result):
                    best_sequence = candidate
                    best_result = result
                    improved = True

        if relocate:
            # Remove one stop and insert it at every other position. Evaluate the
            # entire directed route: symmetric 2-opt delta formulas are invalid here.
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    candidate = best_sequence[:]
                    stop = candidate.pop(i)
                    candidate.insert(j, stop)
                    result = evaluate(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
                    if solution_key(result) < solution_key(best_result):
                        best_sequence = candidate
                        best_result = result
                        improved = True

    return evaluate(best_sequence, matrix, points, vehicle, return_depot, start_time)


def _best_internal_sequence(deliveries, matrix, points, vehicle=None, return_depot=True, start_time="08:00", diagnostics=None):
    """Sceglie il miglior ordine usando solo la matrice stradale già acquisita.

    - Fino a 8 consegne prova tutte le combinazioni: risultato quasi ottimale.
    - Oltre 8 consegne conserva il migliore tra ordini deterministici.
    - Oltre 8: baseline garantita e multi-start con budget deterministico.
    """
    started_cpu, started_wall = time.process_time(), time.perf_counter()
    n = len(deliveries)
    if matrix is None:
        matrix = road_routing.build_matrix(None, 0, points, [str(i) for i in range(len(points))])
    if n <= 8 and diagnostics is not None:
        diagnostics.update(optimizer_strategy='exact-permutations', candidates_evaluated=math.factorial(n) + 1 if n else 1,
                           optimization_budget_exhausted=False, candidate_budget=None)
    if n == 0:
        return _evaluate_fixed_sequence([], matrix, points, vehicle, return_depot, start_time)

    if n <= 8:
        best = None
        checked = 0
        for seq in permutations(deliveries):
            checked += 1
            result = _evaluate_fixed_sequence(list(seq), matrix, points, vehicle, return_depot, start_time, include_details=False)
            if best is None or solution_key(result) < solution_key(best):
                best = result
                best_sequence = list(seq)
        best = _evaluate_fixed_sequence(best_sequence, matrix, points, vehicle, return_depot, start_time)
        print(f"[OPTIMIZER] Ottimizzazione completa: fermate={n} combinazioni={checked} tempo={best['total_min']} min km={best['total_km']}")
        result = _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, best)
        if diagnostics is not None:
            diagnostics.update(optimization_cpu_ms=(time.process_time()-started_cpu)*1000,
                               optimization_ms=(time.perf_counter()-started_wall)*1000)
        return result

    from .services.optimizer_search import search_large_route
    return search_large_route(deliveries, matrix, points, vehicle, return_depot, start_time, diagnostics)


def _legacy_internal_sequence(deliveries, matrix, points, vehicle=None, return_depot=True, start_time="08:00", evaluator=None):
    """The complete pre-multistart baseline, including its feasibility fallback."""
    n = len(deliveries)
    evaluate = evaluator or _evaluate_fixed_sequence
    initial = _greedy_sequence(deliveries, matrix, points, vehicle, start_time)
    result = _local_optimize_sequence(initial, matrix, points, vehicle, return_depot, start_time, evaluator=evaluator)
    # Keep the original heuristic as a candidate, even when new moves take a
    # different search path. Never rank worse than the operator under solution_key.
    operator = evaluate(deliveries, matrix, points, vehicle, return_depot, start_time)
    if solution_key(operator) < solution_key(result):
        result = operator
    if 9 <= n <= 15:
        seeds = [initial, deliveries, list(reversed(initial))]
        seen = set()
        for seed in seeds:
            key = tuple(d["_matrix_index"] for d in seed)
            if key in seen:
                continue
            seen.add(key)
            candidate = _local_optimize_sequence(seed, matrix, points, vehicle, return_depot, start_time, relocate=True, evaluator=evaluator)
            if solution_key(candidate) < solution_key(result):
                result = candidate
    print(f"[OPTIMIZER] Ottimizzazione locale: fermate={n} tempo={result['total_min']} min km={result['total_km']}")
    return _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, result, evaluator=evaluator)


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
    keys = [dc.point_key(deposit_id=deposit.id, lat=depot_coord["lat"], lon=depot_coord["lon"], user_id=user_id)] + [
        dc.point_key(customer_id=d.get("customer_id"), lat=d["coord"]["lat"], lon=d["coord"]["lon"], user_id=user_id)
        for d in deliveries
    ]
    for idx, d in enumerate(deliveries, start=1):
        d["_matrix_index"] = idx

    matrix = build_distance_matrix(db, user_id, points, keys, start_time=start_time, route_date=route_date)

    result = _best_internal_sequence(deliveries, matrix, points, vehicle, return_depot, start_time)

    for d in deliveries:
        d.pop("_matrix_index", None)

    result.pop("_objective", None)
    result.pop("score", None)
    result.pop("violations", None)
    result.pop("total_wait", None)

    result["base_routing_provider"] = getattr(matrix, "source", "osrm")
    result["depot_coord"] = depot_coord
    result["base_return_leg"] = {}
    if return_depot and result["ordered"]:
        last_index = points.index(result["ordered"][-1]["coord"])
        result["base_return_leg"] = dict(matrix.get((last_index, 0)) or {})

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
    keys = [dc.point_key(deposit_id=deposit.id, lat=depot_coord["lat"], lon=depot_coord["lon"], user_id=user_id)] + [
        dc.point_key(customer_id=d.get("customer_id"), lat=d["coord"]["lat"], lon=d["coord"]["lon"], user_id=user_id)
        for d in deliveries
    ]
    for idx, d in enumerate(deliveries, start=1):
        d["_matrix_index"] = idx
    matrix = build_distance_matrix(db, user_id, points, keys, start_time=start_time, route_date=route_date)

    result = _evaluate_fixed_sequence(deliveries, matrix, points, vehicle, return_depot, start_time)
    for delivery in deliveries:
        delivery.pop("_matrix_index", None)
    for key in ("_objective", "score", "violations", "total_wait"):
        result.pop(key, None)

    result["base_routing_provider"] = getattr(matrix, "source", "osrm")
    result["depot_coord"] = depot_coord
    result["base_return_leg"] = {}
    if return_depot and result["ordered"]:
        last_index = points.index(result["ordered"][-1]["coord"])
        result["base_return_leg"] = dict(matrix.get((last_index, 0)) or {})

    result["google_maps_url"] = build_google_maps_url(deposit.indirizzo, result["ordered"], return_depot)
    return result
