"""Miglioramento del piano multi-mezzo con Google OR-Tools (libreria locale e gratuita).

GiroFacile costruisce un piano che serve tutte le consegne possibili; OR-Tools
parte da quel piano e cerca giri più corti. Il risultato è solo una proposta:
fleet_planning la rivaluta con il calendario canonico e la accetta soltanto se è
migliore secondo la strategia scelta. Il confronto su 47 problemi è in
docs/ortools-full-comparison-2026-11-02.md (da solo OR-Tools perde consegne nei
casi stretti; partendo dal piano di GiroFacile no).

Il modello segue le regole del calendario canonico: partenza comune, pause fisse
in cui la guida si ferma ma lo scarico non si interrompe, inizio dello scarico in
una fascia ridotta della sua durata, rientro entro fine turno e tempo disponibile,
capacità in kg e colli. Sponda e ZTL incompatibili costano come 20 km, una
consegna esclusa come 1.000 km. Tempi in secondi arrotondati per eccesso.

Modalità «efficient» (dal 5 novembre 2026): ogni tratta costa i km pesati con il carburante
del mezzo più le ore dell'autista per guida e scarico (services/route_costs.py), in metri
al costo predefinito di 0,20 €/km. Modalità «distance»: soli km, come prima. Le attese
non sono nel modello: le valuta il calendario canonico all'accettazione.

Tempo: 0,15 s per consegna, tra 1 s e FLEET_ORTOOLS_SECONDS (predefinito 10 s).
OR-Tools usa sempre tutto il tempo concesso. Senza OR-Tools installato, o con
FLEET_ORTOOLS_SECONDS=0, il piano resta quello del motore attuale.
"""
from __future__ import annotations

import math
import os
from time import perf_counter

SCALE = 60            # secondi
WEIGHT_SCALE = 1000   # grammi: pesi con decimali senza perdere capacità
DROP_PENALTY = 1_000_000   # metri: 1.000 km
MISMATCH_PENALTY = 20_000  # metri: 20 km
# «Distribuisci il lavoro»: un minuto sul giro più lungo pesa come circa 10 km.
BALANCE_PER_SECOND = 167


def seconds_budget(stop_count):
    try:
        ceiling = max(0.0, min(120.0, float(os.getenv('FLEET_ORTOOLS_SECONDS', '10'))))
    except (TypeError, ValueError):
        ceiling = 10.0
    return min(ceiling, max(1.0, 0.15 * stop_count)) if ceiling else 0.0


def available():
    try:
        from ortools.constraint_solver import pywrapcp  # noqa: F401
    except Exception:
        return False
    return True


def improve(rows, vehicles, matrix, start_time, return_depot, limits, initial, seconds, strategy='efficient'):
    """Nuovi ordini (indici di rows) per mezzo partendo da ``initial``, oppure None.

    ``rows[i]`` è il nodo i+1 della matrice; ``limits`` sono i minuti disponibili
    per mezzo. Nessuna chiamata esterna: solo la matrice già calcolata.
    """
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    from .. import optimizer as opt
    from . import driver_schedule as shifts

    n, count = len(rows), len(vehicles)
    start = opt.parse_hhmm(start_time)
    horizon = 24 * 60 * SCALE
    manager = pywrapcp.RoutingIndexManager(n + 1, count, 0)
    routing = pywrapcp.RoutingModel(manager)
    service = [0] + [math.ceil(float(row.get('tempo_scarico_min') or 0) * SCALE) for row in rows]

    def leg(i, j):
        if i == j or (j == 0 and not return_depot):
            return 0, 0
        value = matrix.get((i, j)) or {}
        return round(float(value.get('km') or 0) * 1000), math.ceil(float(value.get('min') or 0) * SCALE)

    def mismatches(vehicle, node):
        if node == 0:
            return 0
        row = rows[node - 1]
        return (int(bool(row.get('sponda')) and not vehicle.get('ha_sponda', False))
                + int(bool(row.get('ztl')) and not vehicle.get('accesso_ztl', False)))

    from .route_costs import DEFAULT_COST_PER_KM
    for v, vehicle in enumerate(vehicles):
        # Efficient: metri pesati con il costo al km del mezzo (unità: metri a 0,20 €/km).
        per_km, per_min = opt.cost_rates(vehicle)
        factor = per_km / DEFAULT_COST_PER_KM if strategy == 'efficient' else 1.0
        # Ore dell'autista sulla tratta (guida più scarico): stessa unità dei metri.
        per_second = per_min / SCALE / (DEFAULT_COST_PER_KM / 1000) if strategy == 'efficient' else 0.0
        def cost(a, b, vehicle=vehicle, factor=factor, per_second=per_second):
            i, j = manager.IndexToNode(a), manager.IndexToNode(b)
            meters, seconds = leg(i, j)
            return round(meters * factor + (seconds + service[i]) * per_second) + mismatches(vehicle, j) * MISMATCH_PENALTY
        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost), v)

    def transit(a, b):
        i, j = manager.IndexToNode(a), manager.IndexToNode(b)
        return service[i] + leg(i, j)[1]
    routing.AddDimension(routing.RegisterTransitCallback(transit), horizon, horizon, False, 'Time')
    time = routing.GetDimensionOrDie('Time')
    if strategy == 'balanced':
        # Durata del giro più lungo: OR-Tools cerca giri equilibrati tra gli autisti.
        time.SetGlobalSpanCostCoefficient(BALANCE_PER_SECOND)
    visit = [service[manager.IndexToNode(index)] for index in range(routing.Size())]
    unusable = set()
    for v, vehicle in enumerate(vehicles):
        schedule = (vehicle or {}).get('driver_schedule') or {}
        shift_start = opt.parse_hhmm(schedule.get('start'))
        shift_end = opt.parse_hhmm(schedule.get('end'))
        departure = opt.vehicle_start_clock(start, vehicle)
        if shift_start is not None and shift_start > departure:
            unusable.add(v)
        end = departure + max(0, int(limits[v]))
        if shift_end is not None:
            end = min(end, shift_end)
        time.CumulVar(routing.Start(v)).SetRange(int(departure * SCALE), int(departure * SCALE))
        time.CumulVar(routing.End(v)).SetMax(int(max(departure, end) * SCALE))
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.End(v)))
        pauses = [(a, b) for a, b in shifts.intervals(schedule) if b > departure]
        breaks = [routing.solver().FixedDurationIntervalVar(int(a * SCALE), int(a * SCALE), int((b - a) * SCALE), False, f'pausa-{v}-{k}')
                  for k, (a, b) in enumerate(pauses)]
        if breaks:
            time.SetBreakIntervalsOfVehicle(breaks, v, visit)
    for field, capacity, scale in (('peso_kg', 'capacita_kg', WEIGHT_SCALE), ('colli', 'capacita_colli', 1)):
        def demand(a, field=field, scale=scale):
            node = manager.IndexToNode(a)
            return math.ceil(float(rows[node - 1].get(field) or 0) * scale) if node else 0
        caps = [math.floor(float(vehicle[capacity]) * scale) if (vehicle or {}).get(capacity) is not None else 10 ** 12
                for vehicle in vehicles]
        routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(demand), 0, caps, True, field)
    for i, row in enumerate(rows):
        index = manager.NodeToIndex(i + 1)
        routing.AddDisjunction([index], DROP_PENALTY)
        for v in unusable:
            routing.VehicleVar(index).RemoveValue(v)
        windows = opt.delivery_windows(row)
        if not windows:
            time.CumulVar(index).SetRange(start * SCALE, horizon)
            continue
        # Inizio dello scarico ammesso: unione di [apertura, chiusura - scarico].
        allowed = [(int(a * SCALE), int(b * SCALE) - service[i + 1]) for a, b in windows
                   if int(b * SCALE) - service[i + 1] >= max(a, start) * SCALE]
        if not allowed:
            routing.ActiveVar(index).SetValue(0)
            continue
        time.CumulVar(index).SetRange(max(start * SCALE, allowed[0][0]), allowed[-1][1])
        for (_, gap_start), (gap_end, _) in zip(allowed, allowed[1:]):
            if gap_end - 1 >= gap_start + 1:
                time.CumulVar(index).RemoveInterval(gap_start + 1, gap_end - 1)
    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameters.time_limit.FromMilliseconds(max(1, round(seconds * 1000)))
    clock = perf_counter()
    routing.CloseModelWithParameters(parameters)
    seed = routing.ReadAssignmentFromRoutes([[manager.NodeToIndex(i + 1) for i in order] for order in initial], True)
    # Con il piano di partenza rifiutato (arrotondamenti al limite di una fascia) si cerca da zero:
    # l'accettazione finale protegge comunque le consegne servite.
    solution = (routing.SolveFromAssignmentWithParameters(seed, parameters) if seed
                else routing.SolveWithParameters(parameters))
    report = {'seeded': seed is not None, 'status': int(routing.status()),
              'seconds': round(perf_counter() - clock, 2)}
    if solution is None:
        return None, report
    orders = []
    for v in range(count):
        index, order = routing.Start(v), []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node:
                order.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        orders.append(tuple(order))
    return tuple(orders), report
