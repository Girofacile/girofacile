"""Deterministic directed fixtures and independent single-window simulation."""
from optimizer_benchmark import deliveries, reference_cost


def directed_case(n, windows=False):
    rows = deliveries(n)
    matrix = {(i, j): {"km": 1 + (i * 7 + j * 11 + i * j) % 23,
                       "min": 2 + (i * 13 + j * 5 + i * j * 3) % 19}
              for i in range(n + 1) for j in range(n + 1) if i != j}
    if windows:
        clock, previous = 480, 0
        for row in rows:
            node = row["customer_id"]
            arrival = clock + matrix[previous, node]["min"]
            opening = arrival + (7 if node % 3 == 1 else 0)
            service = 3 + node % 5
            closing = opening + service + 10 + node % 4
            row.update(tempo_scarico_min=service,
                       scarico_mattina_da=f"{opening // 60:02}:{opening % 60:02}",
                       scarico_mattina_a=f"{closing // 60:02}:{closing % 60:02}")
            clock, previous = opening + service, node
    return rows, matrix


def reordered(rows, order):
    if order == "reverse":
        return list(reversed(rows))
    if order == "interleaved":
        return rows[::2] + rows[1::2]
    return rows[:]


def independent_window_reference(rows, matrix, return_depot=True):
    """Known feasible witness, NOT an optimum. No production evaluator used.

    Only one same-day window per stop; verify service completion independently.
    The score includes the existing wait-warning cost, without changing it.
    """
    def minutes(text):
        h, m = map(int, text.split(":"))
        return 60 * h + m
    clock, wait, warnings, violations, previous, km = 480, 0, 0, 0, 0, 0
    for row in rows:
        node = row["customer_id"]
        leg = matrix[previous, node]
        km += leg["km"]
        arrival = clock + leg["min"]
        opening = minutes(row["scarico_mattina_da"])
        closing = minutes(row["scarico_mattina_a"])
        delay = max(0, opening - arrival)
        clock = arrival + delay + row["tempo_scarico_min"]
        wait += delay
        warnings += int(delay > 0 or clock > closing)
        violations += int(clock > closing)
        previous = node
    if return_depot:
        km += matrix[previous, 0]["km"]
        clock += matrix[previous, 0]["min"]
    duration = clock - 480
    return dict(total_km=km, total_min=duration, total_wait=wait,
                violations=violations,
                score=violations * 100000 + duration * 10 + wait * 1.5 + warnings * 25 + km)
