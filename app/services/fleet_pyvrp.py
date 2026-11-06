"""Miglioramento del piano multi-mezzo con PyVRP (libreria locale e gratuita, licenza MIT).

Per «Riduci chilometri e tempi» e «Distribuisci il lavoro». Come OR-Tools, PyVRP propone
soltanto: fleet_planning rivaluta ogni giro con il calendario canonico e tiene la proposta
solo se è migliore secondo la strategia (prima consegne servite, poi punteggio o equilibrio).
Con «Distribuisci il lavoro» il costo è sulle ore (un minuto = 10 km) e un limite di durata
dei giri via via più stretto accorcia il giro più lungo. Misure su problemi pubblici di
Solomon e sui piani reali salvati: docs/motore-pyvrp-2026-11-05.md.

Il modello usa l'«orologio di lavoro» di ogni autista (fleet_working_clock): le pause fisse
sono tolte dal tempo, quindi la guida interrotta da una pausa si somma e gli inizi di scarico
ammessi escludono le pause (lo scarico non si interrompe). Una consegna con più fasce, o con
autisti dagli orari diversi, diventa più copie alternative dello stesso cliente: PyVRP ne
serve al massimo una. La partenza è libera da quella richiesta in poi, così le attese che
una partenza più tarda elimina non contano come ore (optimizer.departure_slack). Capacità
in kg e colli; sponda e ZTL incompatibili costano 20 km. Il costo è lo stesso punteggio del
calcolo canonico: km più ore di lavoro convertite in km (optimizer.KM_PER_HOUR). Una
consegna esclusa costa più di quanto possa mai costare servirla.

PyVRP parte da zero, non dal piano già trovato: partire da un piano debole lo intrappola,
e la scelta finale tiene comunque il migliore dei due. Tempo: 0,3 s per consegna, tra 1 s
e FLEET_PYVRP_SECONDS (predefinito 30 s; 0 lo spegne), condiviso tra costruzione,
ricerca e bilanciamento. Solo quando la ricerca non trova un piano valido, un secondo
tentativo con penalità più alte riceve al massimo il 35% in più (RETRY_SHARE). I modelli troppo grandi lasciano il piano già trovato:
FLEET_PYVRP_MAX_EDGES (250.000, al massimo 1.000.000) limita gli archi prima di allocarli.
"""
from __future__ import annotations

import math
import os
import warnings
from time import perf_counter

TIME_PER_MIN = 1000        # millesimi di minuto
WEIGHT_SCALE = 1000        # grammi
COST_PER_METER = 60        # costo intero: 60 per metro, round(60 × km/ora ÷ 60) per millesimo di minuto
MISMATCH_PENALTY_M = 20_000
BALANCE_KM_PER_MIN = 10    # «Distribuisci il lavoro»: un minuto di lavoro pesa come 10 km (come OR-Tools)
BALANCE_STEPS = 5          # dimezzamenti del limite di durata del giro
DEFAULT_MAX_MODEL_EDGES = 250_000
HARD_MAX_MODEL_EDGES = 1_000_000


RETRY_SHARE = 0.35         # tempo in più, solo per il secondo tentativo (quota di FLEET_PYVRP_SECONDS)


class _Deadline:
    """PyVRP controlla questo termine assoluto anche dopo il proprio setup."""
    def __init__(self, deadline):
        self.deadline = deadline

    def __call__(self, best_cost):
        return perf_counter() >= self.deadline


def available():
    try:
        import pyvrp  # noqa: F401
    except Exception:
        return False
    return True


def seconds_budget(stop_count):
    try:
        ceiling = max(0.0, min(120.0, float(os.getenv('FLEET_PYVRP_SECONDS', '30'))))
    except (TypeError, ValueError):
        ceiling = 30.0
    return min(ceiling, max(1.0, 0.3 * stop_count)) if ceiling else 0.0


def _max_model_edges():
    # Un Edge occupa già 64 byte, senza interi, liste e matrici del solutore.
    # Una configurazione sbagliata non deve poter rimuovere il tetto di memoria.
    try:
        requested = int(os.getenv('FLEET_PYVRP_MAX_EDGES', str(DEFAULT_MAX_MODEL_EDGES)))
    except (TypeError, ValueError):
        requested = DEFAULT_MAX_MODEL_EDGES
    return max(1_000, min(HARD_MAX_MODEL_EDGES, requested))


def _scaled_domains(row, vehicle, start, limit):
    from .fleet_working_clock import TIME_SCALE, service_domains
    domains, horizon = service_domains(row, vehicle, start, limit)
    ratio = TIME_SCALE // TIME_PER_MIN
    out = []
    for lo, hi in domains:
        lo, hi = -(-lo // ratio), hi // ratio   # per eccesso / per difetto: mai più largo del vero
        if lo <= hi:
            out.append((lo, hi))
    return tuple(out), horizon // ratio


def improve(rows, vehicles, matrix, start_time, return_depot, limits, initial, seconds, strategy='efficient'):
    """Nuovi ordini (indici di rows) per mezzo, oppure None; stessa interfaccia di fleet_ortools."""
    clock_started = perf_counter()
    budget = max(0.0, float(seconds))
    deadline = clock_started + budget
    # Solo il secondo tentativo, quando il primo non trova un piano valido, può andare oltre:
    # al massimo il 35% del tempo in più (fino a 40,5 s con il predefinito di 30 s).
    hard_deadline = deadline + RETRY_SHARE * budget

    def remaining():
        return max(0.0, deadline - perf_counter())

    def skipped(status, **details):
        return None, {'engine': 'pyvrp', 'status': status, 'seeded': False,
                      'feasible': False, 'attempts': 0,
                      'seconds': round(perf_counter() - clock_started, 2), **details}

    if not remaining():
        return skipped('time-limit')
    from pyvrp import Model, PenaltyParams, Route, Solution, SolveParams, solve
    from pyvrp.exceptions import PenaltyBoundWarning
    from .. import optimizer as opt

    start = opt.parse_hhmm(start_time)
    n, count = len(rows), len(vehicles)
    # Orologio di ogni mezzo: inizi di scarico ammessi per consegna e fine del lavoro.
    clocks, signature_of = [], []
    for v, vehicle in enumerate(vehicles):
        if not remaining():
            return skipped('time-limit')
        per_row = [_scaled_domains(row, vehicle or {}, start, limits[v]) for row in rows]
        signature = tuple(domains for domains, _ in per_row)
        horizon = min((h for _, h in per_row), default=0) if rows else 0
        if signature not in clocks:
            clocks.append(signature)
        signature_of.append((clocks.index(signature), horizon))

    # Ogni copia cliente compare in una matrice densa per ciascun profilo.
    # Contare prima: 100 consegne × 10 orari × 2 fasce arrivano a 40 milioni
    # di Edge, anche quando la ricerca è limitata a pochi secondi.
    copy_count = sum(len(domains) for signature in clocks for domains in signature)
    profile_count = len({(signature_of[v][0], bool((vehicle or {}).get('ha_sponda')),
                         bool((vehicle or {}).get('accesso_ztl')))
                        for v, vehicle in enumerate(vehicles)})
    model_edges = (copy_count + 1) ** 2 * profile_count
    dimensions = {'copies': copy_count, 'clocks': len(clocks), 'profiles': profile_count,
                  'model_edges': model_edges, 'max_model_edges': _max_model_edges()}
    if model_edges > dimensions['max_model_edges']:
        return skipped('model-size-limit', **dimensions)
    if not remaining():
        return skipped('time-limit', **dimensions)

    def mismatches(vehicle, row):
        return (int(bool(row.get('sponda')) and not (vehicle or {}).get('ha_sponda', False))
                + int(bool(row.get('ztl')) and not (vehicle or {}).get('accesso_ztl', False)))

    # Consegna esclusa: almeno 100.000 km, e comunque più di quanto possa mai costare servirla
    # (andata e ritorno sulla tratta più lunga, due incompatibilità di attrezzatura e un'intera
    # giornata di lavoro). Servire viene prima del risparmio, come nel calcolo canonico; con un
    # valore più basso PyVRP rinuncia alle consegne difficili (Solomon r1: da 1 a 3 escluse).
    longest = max((float(value.get('km') or 0) * 1000 for value in matrix.values()), default=0.0)
    efficient, balanced = strategy == 'efficient', strategy == 'balanced'

    def rates(vehicle):
        per_km, per_min = opt.cost_rates(vehicle)
        if balanced:
            return 1.0, float(BALANCE_KM_PER_MIN)
        return (per_km, per_min) if efficient else (1.0, 0.0)

    hourly = max((rates(vehicle)[1] for vehicle in vehicles), default=0.0)
    day = max((h for _, h in signature_of), default=0)
    prize = COST_PER_METER * math.ceil(2 * longest + 2 * MISMATCH_PENALTY_M) + math.ceil(COST_PER_METER * hourly) * day
    prize = max(2 * prize + 1, COST_PER_METER * 100_000_000)

    model = Model()
    depot_location = model.add_location(0, 0)
    depot = model.add_depot(depot_location)
    # Copie: (riga, orologio, inizio ammesso minimo, massimo).
    copies, locations = [], [depot_location]
    for i, row in enumerate(rows):
        if not remaining():
            return skipped('time-limit', **dimensions)
        options = [(c, lo, hi) for c, signature in enumerate(clocks) for lo, hi in signature[i]]
        if not options:
            continue
        group = model.add_client_group(required=False) if len(options) > 1 else None
        weight = math.ceil(float(row.get('peso_kg') or 0) * WEIGHT_SCALE)
        parcels = math.ceil(float(row.get('colli') or 0))
        service = math.ceil(float(row.get('tempo_scarico_min') or 0) * TIME_PER_MIN)
        for c, lo, hi in options:
            location = model.add_location(0, 0)
            model.add_client(location, delivery=[weight, parcels], service_duration=service,
                             tw_early=lo, tw_late=hi, required=False,
                             prize=prize, group=group)
            copies.append((i, c))
            locations.append(location)
    if not copies:
        return skipped('no-feasible-copy', **dimensions)

    def leg(a, b):
        if a == b or (b == 0 and not return_depot):
            return 0, 0
        value = matrix.get((a, b)) or {}
        return round(float(value.get('km') or 0) * 1000), math.ceil(float(value.get('min') or 0) * TIME_PER_MIN)

    nodes = [None] + copies   # nodo 0 = deposito
    forbidden = max((h for _, h in signature_of), default=0) + 1
    profiles = {}
    for v, vehicle in enumerate(vehicles):
        clock, _ = signature_of[v]
        key = (clock, int(bool((vehicle or {}).get('ha_sponda'))), int(bool((vehicle or {}).get('accesso_ztl'))))
        if key in profiles:
            continue
        profile = model.add_profile()
        profiles[key] = profile
        for a, frm in enumerate(nodes):
            if not remaining():
                return skipped('time-limit', **dimensions)
            ia = 0 if frm is None else frm[0] + 1
            for b, to in enumerate(nodes):
                ib = 0 if to is None else to[0] + 1
                meters, duration = leg(ia, ib)
                if a == b:
                    meters, duration = 0, 0   # PyVRP vuole tratte nulle da un punto a sé stesso
                elif to is not None:
                    if to[1] != clock:
                        # Copia di un altro orologio: la tratta dura più dell'intera giornata
                        # di lavoro, quindi nessun giro valido la usa. Valori enormi invece
                        # falserebbero la taratura delle penalità di PyVRP.
                        duration = forbidden
                    else:
                        meters += mismatches(vehicle, rows[to[0]]) * MISMATCH_PENALTY_M
                model.add_edge(locations[a], locations[b], distance=meters, duration=duration, profile=profile)
    # Mezzi identici (stesso orologio, attrezzatura, capacità e costi) formano un solo tipo:
    # PyVRP li scambia liberamente e la ricerca è molto più efficace.
    types, members = {}, {}
    for v, vehicle in enumerate(vehicles):
        clock, horizon = signature_of[v]
        if not any(clock == c for _, c in copies) or horizon <= 0:
            continue   # mezzo senza alcuna consegna possibile (turno che inizia dopo la partenza)
        caps = tuple(math.floor(float(vehicle[k]) * s) if (vehicle or {}).get(k) is not None else 10 ** 12
                     for k, s in (('capacita_kg', WEIGHT_SCALE), ('capacita_colli', 1)))
        profile_key = (clock, int(bool((vehicle or {}).get('ha_sponda'))), int(bool((vehicle or {}).get('accesso_ztl'))))
        per_km, per_min = rates(vehicle)
        costs = (round(COST_PER_METER * per_km), round(COST_PER_METER * per_min))
        members.setdefault((profile_key, caps, costs, horizon), []).append(v)
    if not members:
        return skipped('no-usable-vehicle', **dimensions)
    type_of = {}
    for t, ((profile_key, caps, costs, horizon), group) in enumerate(members.items()):
        model.add_vehicle_type(
            num_available=len(group), capacity=list(caps), start_depot=depot, end_depot=depot,
            # Partenza libera tra quella richiesta e la fine del lavoro: come nel calcolo canonico
            # (optimizer.departure_slack), le attese che una partenza più tarda elimina non sono ore.
            tw_early=0, tw_late=horizon, profile=profiles[profile_key],
            unit_distance_cost=costs[0], unit_duration_cost=costs[1])
        for v in group:
            type_of[v] = t
    groups = list(members.values())
    if not remaining():
        return skipped('time-limit', **dimensions)
    data = model.data()
    seed = None
    # Di norma PyVRP parte da zero: partire da un piano debole lo intrappola (rc203: 10% contro 1%).
    # La scelta finale tiene comunque il migliore tra il piano attuale e quello di PyVRP.
    if os.getenv('FLEET_PYVRP_SEED', '0') == '1':
        try:
            # Piano di partenza: ogni consegna sulla prima copia dell'orologio del suo mezzo.
            # Nei giri di PyVRP i clienti sono numerati da 0, i depositi a parte.
            index = {}
            for k, (i, c) in enumerate(copies):
                index.setdefault((i, c), k)
            seed_routes = []
            for v, t in type_of.items():
                visits = [index[(i, signature_of[v][0])] for i in (initial[v] if v < len(initial) else ())
                          if (i, signature_of[v][0]) in index]
                if visits:
                    seed_routes.append(Route(data, visits, t))
            seed = Solution(data, seed_routes) if seed_routes else None
        except Exception:
            seed = None
    def run(problem, limit, start_from=None, retry=True):
        # Prima la ricerca con le impostazioni normali di PyVRP, per tutto il tempo della fase:
        # sui problemi con fasce strette il piano valido arriva tardi (Solomon r104: con il 65%
        # del tempo 3 consegne escluse, con il 100% nessuna; dipende dalla velocità del server).
        # Solo se alla fine non c'è un piano valido (giorni in cui non tutto è servibile: piano
        # reale 50, 30 consegne su 54) si ripete con il tetto delle penalità per sovraccarico e
        # ritardo sopra il costo di una consegna esclusa, altrimenti PyVRP preferisce sforare;
        # quel tetto alto, sempre attivo, peggiora i casi con fasce strette (r104, r110).
        phase_deadline = min(deadline, perf_counter() + max(0.0, limit))
        result, attempts = None, 0
        if phase_deadline > perf_counter():
            result = _solve(problem, PenaltyParams(), phase_deadline, start_from)
            attempts = 1
        if retry and (result is None or not result.is_feasible()):
            retry_deadline = min(hard_deadline, perf_counter() + RETRY_SHARE * budget)
            if retry_deadline > perf_counter():
                result = _solve(problem, PenaltyParams(max_penalty=float(max(100_000, prize + 1))),
                                retry_deadline, start_from)
                attempts += 1
        return result, attempts

    def _solve(problem, penalty, until, start_from):
        with warnings.catch_warnings():
            # Penalità che toccano il tetto sono previste (consegne non servibili): niente avvisi nei log.
            warnings.simplefilter('ignore', PenaltyBoundWarning)
            return solve(problem, stop=_Deadline(until), seed=1, display=False, collect_stats=False,
                         initial_solution=start_from, params=SolveParams(penalty=penalty))

    def served(solution):
        return sum(route.num_clients() for route in solution.routes())

    def longest(solution):
        return max((route.duration() for route in solution.routes()), default=0)

    # «Distribuisci il lavoro»: prima un piano libero, poi si dimezza la distanza tra la
    # durata del giro più lungo trovata e la media per mezzo, imponendo a ogni giro di non
    # superarla (vincolo rigido di PyVRP). Si tiene il limite più basso che serve ancora
    # le stesse consegne; il giudizio finale resta della chiave «Distribuisci il lavoro».
    result, attempts = run(data, remaining() * (0.35 if balanced else 1.0), seed)
    feasible = result is not None and result.is_feasible()
    report = {'engine': 'pyvrp', 'seeded': seed is not None, 'feasible': bool(feasible),
              'attempts': attempts, **dimensions, 'vehicle_types': len(groups)}
    if result is None:
        report['status'] = 'time-limit'
    best = result.best if feasible else None
    if balanced and best is not None and best.routes():
        target = served(best)
        usable = sum(len(group) for group in groups)
        high = longest(best)
        low = int(0.9 * sum(route.duration() for route in best.routes()) / max(1, usable))
        steps = []
        for _ in range(BALANCE_STEPS):
            if not remaining() or high - low <= TIME_PER_MIN:   # meno di un minuto: inutile stringere ancora
                break
            limit = (low + high) // 2
            tight = data.replace(vehicle_types=[vt.replace(shift_duration=limit) for vt in data.vehicle_types()])
            # Il piano migliore finora come punto di partenza: PyVRP vuole giri legati ai nuovi dati.
            start_from = Solution(tight, [Route(tight, [a.idx for a in route if a.is_client()], route.vehicle_type())
                                          for route in best.routes()])
            # Un limite troppo stretto si scarta e si prova quello successivo: nessun secondo tentativo.
            trial, trial_attempts = run(tight, remaining() / (BALANCE_STEPS - len(steps)), start_from, retry=False)
            report['attempts'] += trial_attempts
            if trial is None:
                break
            ok = trial.is_feasible() and served(trial.best) >= target
            steps.append((round(limit / TIME_PER_MIN), bool(ok)))
            if ok:
                best, high = trial.best, min(limit, longest(trial.best))
            else:
                low = limit
        report['balance'] = {'longest_min': round(longest(best) / TIME_PER_MIN, 1), 'steps': steps}
    report['seconds'] = round(perf_counter() - clock_started, 2)
    report['budget_exhausted'] = not remaining()
    if best is None:
        return None, report
    orders = [()] * count
    free = [list(group) for group in groups]
    for route in best.routes():
        v = free[route.vehicle_type()].pop(0)
        orders[v] = tuple(copies[a.idx][0] for a in route if a.is_client())
    return tuple(orders), report
