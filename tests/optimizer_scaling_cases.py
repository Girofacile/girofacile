"""Fixed synthetic matrix families; never claim real-world fuel savings."""
import math
import random
from functools import lru_cache
from itertools import permutations
from optimizer_benchmark import deliveries
from optimizer_scenarios import directed_case


def scenario(n, kind):
    rows = deliveries(n)
    if kind == 'asymmetric':
        return directed_case(n)
    if kind == 'nearest_trap':
        matrix = {(i, j): {'km': 100 + (i * 7 + j * 3) % 11, 'min': 2 + (i + j) % 7}
                  for i in range(n + 1) for j in range(n + 1) if i != j}
        route = [0, *range(2, n + 1), 1, 0]
        for a, b in zip(route, route[1:]):
            matrix[a, b] = {'km': 1, 'min': 3}
        matrix[0, 1] = {'km': 0.5, 'min': 1}
        matrix[0, 2] = {'km': 2, 'min': 4}
        return rows, matrix
    rng = random.Random(61001 + n)
    centers = [(0, 0), (25, 4), (9, 32), (35, 30)]
    coordinates = [(0, 0)] + [(centers[i % 4][0] + rng.randrange(8),
                               centers[i % 4][1] + rng.randrange(8)) for i in range(n)]
    matrix = {}
    for i, a in enumerate(coordinates):
        for j, b in enumerate(coordinates):
            if i != j:
                km = round(math.hypot(a[0] - b[0], a[1] - b[1]) + 1 + (i * 3 + j * 7) % 5, 3)
                matrix[i, j] = {'km': km, 'min': 1 + int(km / 8) + (i * 7 + j * 3) % 4}
    if kind == 'windows':
        witness = sorted(rows, key=lambda d: ((d['customer_id'] - 1) % 4, d['customer_id']))
        clock, previous = 480, 0
        for row in witness:
            node = row['_matrix_index']
            opening = clock + matrix[previous, node]['min'] + 3
            closing = opening + 25
            row.update(tempo_scarico_min=2,
                scarico_mattina_da=f'{opening // 60:02}:{opening % 60:02}',
                scarico_mattina_a=f'{closing // 60:02}:{closing % 60:02}')
            clock, previous = opening + 2, node
    return rows, matrix


def exact_distance_reference(rows, matrix, back=True):
    """Independent lexicographic Held-Karp for unconstrained routes, no production code."""
    @lru_cache(None)
    def visit(previous, mask):
        if mask == 0:
            leg = matrix[previous, 0] if back else {'km': 0, 'min': 0}
            return leg['km'], leg['min']
        return min((matrix[previous, i]['km'] + visit(i, mask ^ (1 << (i-1)))[0],
                    matrix[previous, i]['min'] + visit(i, mask ^ (1 << (i-1)))[1])
                   for i in range(1, len(rows) + 1) if mask & (1 << (i-1)))
    result = visit(0, (1 << len(rows)) - 1)
    visit.cache_clear()
    return {'total_km': round(result[0], 2), 'total_min': round(result[1], 1), 'kind': 'exact_distance_time'}


def exact_window_reference(rows, matrix, back=True):
    """Independent brute-force feasible schedules for the single-window fixtures."""
    def minute(value):
        h, m = map(int, value.split(':'))
        return h * 60 + m
    best = None
    for order in permutations(rows):
        clock, km, wait, previous = 480, 0, 0, 0
        for row in order:
            node = row['_matrix_index']
            leg = matrix[previous, node]
            km += leg['km']
            arrival = clock + leg['min']
            start = max(arrival, minute(row['scarico_mattina_da']))
            wait += start - arrival
            clock, previous = start + row['tempo_scarico_min'], node
            if clock > minute(row['scarico_mattina_a']):
                break
        else:
            if back:
                km += matrix[previous, 0]['km']
                clock += matrix[previous, 0]['min']
            key = (km, clock - 480, wait)
            if best is None or key < best:
                best = key
    assert best is not None
    return {'total_km': round(best[0], 2), 'total_min': round(best[1], 1), 'kind': 'exact_feasible_distance_time'}
