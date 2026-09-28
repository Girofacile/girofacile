"""Offline quality helpers. Exact oracle applies ONLY without time windows.

Held-Karp minimizes the existing additive 10 * minutes + km objective, not
the optimizer's permutations, greedy choices or local moves. No production
code is used to calculate reference costs. Runtime is O(n**2 * 2**n).
"""
from functools import lru_cache


def deliveries(n):
    return [dict(customer_id=i, _matrix_index=i, cliente_nome=f"C{i}",
                 indirizzo=f"Via {i}", lat=45 + i / 1000, lon=9,
                 tempo_scarico_min=0, peso_kg=0, colli=0)
            for i in range(1, n + 1)]


def metric_matrix(coords):
    """Manhattan road grid: 1 km corresponds to 2 minutes, depot at index 0."""
    return {(i, j): {"km": abs(a[0]-b[0]) + abs(a[1]-b[1]),
                     "min": 2 * (abs(a[0]-b[0]) + abs(a[1]-b[1]))}
            for i, a in enumerate(coords) for j, b in enumerate(coords) if i != j}


def reference_cost(order, matrix, return_depot=True):
    route = [0, *order] + ([0] if return_depot and order else [])
    legs = [matrix[a, b] for a, b in zip(route, route[1:])]
    return {"total_km": sum(x["km"] for x in legs),
            "total_min": sum(x["min"] for x in legs)}


def exact_reference(n, matrix, return_depot=True):
    @lru_cache(None)
    def solve(current, remaining):
        if not remaining:
            back = matrix[current, 0] if return_depot and current else {"km": 0, "min": 0}
            return 10 * back["min"] + back["km"], ()
        best = None
        for node in range(1, n + 1):
            bit = 1 << (node - 1)
            if remaining & bit:
                cost, suffix = solve(node, remaining ^ bit)
                leg = matrix[current, node]
                candidate = (10 * leg["min"] + leg["km"] + cost, (node, *suffix))
                if best is None or candidate < best:
                    best = candidate
        return best

    score, order = solve(0, (1 << n) - 1)
    result = dict(reference_cost(order, matrix, return_depot), order=order, score=score)
    solve.cache_clear()
    return result


def quality(actual, reference):
    report = {"violations": actual["violations"], "wait_min": actual["total_wait"]}
    for unit in ("km", "min"):
        value, base = actual[f"total_{unit}"], reference[f"total_{unit}"]
        report.update({f"actual_{unit}": value, f"reference_{unit}": base,
                       f"delta_{unit}": value - base,
                       f"gap_{unit}_pct": 100 * (value - base) / base if base else None})
    return report
