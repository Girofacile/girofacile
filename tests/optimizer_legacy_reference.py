"""Frozen search control flow from 824816f (distance-first baseline).

Only unchanged scheduling/constraint primitives are shared with production.
The new search and its fast evaluator are never used by this reference.
"""
from itertools import permutations
from app.optimizer import (evaluate_candidate, solution_key, _evaluate_fixed_sequence,
    _matrix_leg, _start_clock, _earliest_feasible_candidate, road_routing)

def _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, best):
    """Exact feasibility DP for up to 15 selected stops, only if search found none.

    Earliest completion dominates later completion at the same (subset, last):
    waiting is allowed and matrix travel times are fixed. Retain parents to
    reconstruct a witness, not a claim of optimal duration/distance.
    """
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
        candidate = _evaluate_fixed_sequence(sequence[::-1], matrix, points, vehicle, return_depot, start_time, earliest_windows=True)
        if solution_key(candidate) < solution_key(best):
            best = candidate
    return best

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

def _local_optimize_sequence(initial_sequence, matrix, points, vehicle=None, return_depot=True, start_time="08:00", max_rounds=4, relocate=False):
    """Migliora un ordine provando scambi e inversioni senza nuove chiamate di routing."""
    best_sequence = initial_sequence[:]
    best_result = _evaluate_fixed_sequence(best_sequence, matrix, points, vehicle, return_depot, start_time, include_details=False)
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
                result = _evaluate_fixed_sequence(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
                if solution_key(result) < solution_key(best_result):
                    best_sequence = candidate
                    best_result = result
                    improved = True

        # 2-opt leggero: inverte segmenti consecutivi.
        for i in range(n - 2):
            for j in range(i + 2, n):
                candidate = best_sequence[:i] + list(reversed(best_sequence[i:j + 1])) + best_sequence[j + 1:]
                result = _evaluate_fixed_sequence(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
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
                    result = _evaluate_fixed_sequence(candidate, matrix, points, vehicle, return_depot, start_time, include_details=False)
                    if solution_key(result) < solution_key(best_result):
                        best_sequence = candidate
                        best_result = result
                        improved = True

    return _evaluate_fixed_sequence(best_sequence, matrix, points, vehicle, return_depot, start_time)

def _best_internal_sequence(deliveries, matrix, points, vehicle=None, return_depot=True, start_time="08:00"):
    """Sceglie il miglior ordine usando solo la matrice stradale già acquisita.

    - Fino a 8 consegne prova tutte le combinazioni: risultato quasi ottimale.
    - Oltre 8 consegne conserva il migliore tra ordini deterministici.
    - Per 9-15 consegne aggiunge rilocazioni e partenze multiple.
    """
    n = len(deliveries)
    if matrix is None:
        matrix = road_routing.build_matrix(None, 0, points, [str(i) for i in range(len(points))])
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
        return _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, best)

    initial = _greedy_sequence(deliveries, matrix, points, vehicle, start_time)
    result = _local_optimize_sequence(initial, matrix, points, vehicle, return_depot, start_time)
    # Keep the original heuristic as a candidate, even when new moves take a
    # different search path. Never rank worse than the operator under solution_key.
    operator = _evaluate_fixed_sequence(deliveries, matrix, points, vehicle, return_depot, start_time)
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
            candidate = _local_optimize_sequence(seed, matrix, points, vehicle, return_depot, start_time, relocate=True)
            if solution_key(candidate) < solution_key(result):
                result = candidate
    print(f"[OPTIMIZER] Ottimizzazione locale: fermate={n} tempo={result['total_min']} min km={result['total_km']}")
    return _feasible_fallback(deliveries, matrix, points, vehicle, return_depot, start_time, result)
