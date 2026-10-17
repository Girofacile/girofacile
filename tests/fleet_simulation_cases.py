"""Deterministic fleet simulations: fictional deliveries, frozen routing fixtures."""
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path
import random

START_MIN = 8 * 60
SMALL_FAMILIES = ("plain", "capacity", "windows", "breaks", "mixed", "double_windows")
ROAD_AREAS = ("urban", "provincial", "mixed")


def hhmm(minutes):
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def stop(index, weight=1, packages=1, service=0, **updates):
    row = {
        "customer_id": index + 1,
        "cliente_nome": f"Consegna dimostrativa {index + 1}",
        "indirizzo": f"Via Simulazione {index + 1}, localita fittizia",
        "lat": 45.40 + (index + 1) * 0.001,
        "lon": 9.12 + (index + 1) * 0.001,
        "peso_kg": weight, "colli": packages,
        "tempo_scarico_min": service, "ztl": False, "sponda": False,
    }
    row.update(updates)
    return row


def resource(capacity=1000, packages=1000, schedule=None, max_minutes=540, **updates):
    row = {
        "capacita_kg": capacity, "capacita_colli": packages,
        "ha_sponda": True, "accesso_ztl": True,
        "max_minutes": max_minutes, "driver_schedule": deepcopy(schedule or {}),
    }
    row.update(updates)
    return row


def uniform_matrix(n, km=1.0, minutes=10.0):
    return {
        (i, j): {"km": 0.0 if i == j else float(km),
                 "min": 0.0 if i == j else float(minutes)}
        for i in range(n + 1) for j in range(n + 1)
    }


def line_matrix(positions, minutes_per_km=2.0):
    points = [0.0, *positions]
    return {
        (i, j): {"km": abs(a - b), "min": abs(a - b) * minutes_per_km}
        for i, a in enumerate(points) for j, b in enumerate(points)
    }


def make_case(identifier, family, stops, matrix, resources, *, seed=0,
              returning=True, exact=True, witness=None, coordinates=None):
    result = {
        "id": identifier, "family": family, "seed": seed,
        "stops": stops, "matrix": matrix, "resources": resources,
        "return_depot": returning, "start_min": START_MIN, "exact": exact,
    }
    if witness is not None:
        result["witness"] = witness
    if coordinates is not None:
        result["coordinates"] = coordinates
    return result


def line_case(identifier, positions, weights, *, pauses=False):
    schedule = {"start": "08:00", "end": "17:00",
                "breaks": [{"start": "08:45", "end": "09:15"}] if pauses else []}
    rows = [stop(i, w, service=5 if pauses else 0) for i, w in enumerate(weights)]
    return make_case(identifier, "curated_clusters", rows, line_matrix(positions),
                     [resource(20, schedule=schedule), resource(20, schedule=schedule)],
                     witness=[[0, 2], [1, 3]])


def curated_cases():
    cases = [
        make_case("curated-capacity-repacking", "curated_capacity",
                  [stop(i, w) for i, w in enumerate((6, 5, 3, 2, 2, 2))],
                  uniform_matrix(6), [resource(10), resource(10)],
                  witness=[[0, 3, 4], [1, 2, 5]]),
        line_case("curated-opposite-clusters", [10, -10, 11, -11], [10] * 4),
        line_case("curated-opposite-clusters-breaks", [10, -10, 11, -11],
                  [10] * 4, pauses=True),
    ]
    pause = {"start": "08:00", "end": "17:00",
             "breaks": [{"start": "08:20", "end": "08:40"}]}
    no_pause = {"start": "08:00", "end": "17:00", "breaks": []}
    cases.append(make_case(
        "curated-break-window-reassignment", "curated_breaks_windows",
        [stop(0, 2, service=15, scarico_mattina_da="08:00", scarico_mattina_a="10:00"),
         stop(1, 1, service=10, scarico_mattina_da="08:15", scarico_mattina_a="08:35")],
        uniform_matrix(2), [resource(2, schedule=pause), resource(2, schedule=no_pause)],
        witness=[[0], [1]]))
    cases.append(make_case(
        "curated-late-driver-start", "curated_shift",
        [stop(0, 2, service=10), stop(1, 1, service=10)], uniform_matrix(2),
        [resource(10, schedule={"start": "09:00", "end": "17:00", "breaks": []}),
         resource(10, schedule=no_pause)], witness=[[], [0, 1]]))
    waiting_pause = {"start": "08:00", "end": "17:00",
                     "breaks": [{"start": "08:15", "end": "08:45"}]}
    cases.append(make_case(
        "curated-waiting-absorbs-break", "curated_waiting",
        [stop(i, service=10, scarico_mattina_da="09:00", scarico_mattina_a="11:00")
         for i in range(2)], uniform_matrix(2),
        [resource(10, schedule=waiting_pause), resource(10, schedule=no_pause)],
        witness=[[0], [1]]))
    cases.append(make_case(
        "curated-return-crosses-break", "curated_return",
        [stop(0), stop(1)], uniform_matrix(2),
        [resource(1, schedule=waiting_pause), resource(1, schedule=waiting_pause)],
        witness=[[0], [1]]))
    directed = uniform_matrix(2)
    for edge, values in {
        (0, 1): (5, 4), (1, 0): (5, 4), (0, 2): (8, 6),
        (2, 0): (7, 6), (1, 2): (5, 4), (2, 1): (2, 6),
    }.items():
        directed[edge] = {"km": float(values[0]), "min": float(values[1])}
    cases.append(make_case(
        "curated-km-time-tradeoff", "curated_objective",
        [stop(0, 2), stop(1, 1)], directed,
        [resource(100), resource(100)], witness=[[1, 0], []]))
    return cases


def _synthetic_geometry(rng, n, spread=14.0):
    # Directed metric with a Lipschitz potential and positive off-diagonal work.
    xy = [(0.0, 0.0)]
    xy.extend((rng.uniform(-spread, spread), rng.uniform(-spread, spread))
              for _ in range(n))
    matrix = {}
    for i, (x1, y1) in enumerate(xy):
        for j, (x2, y2) in enumerate(xy):
            distance = math.hypot(x2 - x1, y2 - y1)
            matrix[(i, j)] = {
                "km": 0.0 if i == j else 0.5 + 1.08 * distance + 0.12 * (x2 - x1),
                "min": 0.0 if i == j else 0.8 + distance * 60 / 38 + 0.10 * (y2 - y1),
            }
    coordinates = [{"lat": 45.4 + y / 111, "lon": 9.12 + x / 78}
                   for x, y in xy]
    return matrix, coordinates


def _schedule(index, seed, *, pauses, variable=False):
    end = (14 * 60 + (seed + index) % 4 * 60) if variable else 17 * 60
    breaks = []
    if pauses:
        first = 8 * 60 + 40 + (index * 25 + seed * 7) % 110
        breaks.append({"start": hhmm(first), "end": hhmm(first + 15 + seed % 3 * 10)})
        if seed % 3 == 0:
            second = 12 * 60 + index * 10
            breaks.append({"start": hhmm(second), "end": hhmm(second + 30)})
    return {"start": "08:00", "end": hhmm(end), "breaks": breaks}


def _set_window(row, rng, *, double=False, impossible=False):
    if impossible:
        row.update(scarico_mattina_da="07:00", scarico_mattina_a="07:30")
        return
    opening = 8 * 60 + rng.randrange(0, 181, 15)
    closing = min(12 * 60, opening + rng.choice((30, 45, 60, 120)))
    row.update(scarico_mattina_da=hhmm(opening), scarico_mattina_a=hhmm(closing))
    if double:
        opening = 13 * 60 + rng.randrange(0, 61, 15)
        row.update(scarico_pomeriggio_da=hhmm(opening),
                   scarico_pomeriggio_a=hhmm(opening + rng.choice((30, 60, 120))))


def small_synthetic_cases():
    cases = []
    for family_index, family in enumerate(SMALL_FAMILIES):
        for seed in range(20):
            rng = random.Random(11000 + family_index * 100 + seed)
            n, count = 3 + seed % 4, 2 + seed % 2
            matrix, coordinates = _synthetic_geometry(rng, n)
            rows = [stop(i, rng.randint(1, 12), rng.randint(1, 4),
                         rng.choice((0, 5, 10, 15, 20)),
                         lat=coordinates[i + 1]["lat"], lon=coordinates[i + 1]["lon"])
                    for i in range(n)]
            if family in ("windows", "mixed", "double_windows"):
                for index, row in enumerate(rows):
                    if family != "mixed" or rng.random() < 0.8:
                        _set_window(row, rng, double=family == "double_windows",
                                    impossible=(seed % 9 == 0 and index == n - 1))
            if family == "mixed":
                for row in rows:
                    row.update(ztl=rng.random() < 0.25, sponda=rng.random() < 0.25)
            total = sum(row["peso_kg"] for row in rows)
            packages = sum(row["colli"] for row in rows)
            resources = []
            for index in range(count):
                constrained = family in ("capacity", "mixed")
                factor = (0.65, 0.90, 1.20, 1.75)[(seed + index) % 4]
                capacity = max(1, math.ceil(total / count * factor)) if constrained else total + 10
                package_limit = max(1, math.ceil(packages / count * factor)) if constrained else packages + 10
                schedule = _schedule(index, seed, pauses=family in ("breaks", "mixed"),
                                     variable=family in ("breaks", "mixed", "double_windows"))
                item = resource(capacity, package_limit, schedule=schedule,
                                max_minutes=540,
                                ha_sponda=family != "mixed" or (seed + index) % 3 != 0,
                                accesso_ztl=family != "mixed" or (seed + index) % 4 != 0)
                if family == "mixed" and seed % 4 == 1:
                    item["available_minutes"] = 90 + index * 60
                resources.append(item)
            cases.append(make_case(
                f"small-{family}-{seed:02d}", f"small_{family}", rows, matrix,
                resources, seed=seed, returning=seed % 2 == 0, coordinates=coordinates))
    return cases


@lru_cache(maxsize=1)
def _road_pools():
    data = json.loads((Path(__file__).parent / "fixtures" / "road_margin_matrices.json").read_text(encoding="utf-8"))
    if data["schema_version"] != 1:
        raise ValueError("Unsupported frozen road matrix schema")
    return data["pools"]


def _road_case(area, n, count, seed, *, stress=False):
    pool = _road_pools()[area]
    rng = random.Random(71000 + ROAD_AREAS.index(area) * 1000 + seed)
    indexes = [0, *rng.sample(range(1, len(pool["coordinates"])), n)]
    coordinates = [{"lat": pool["coordinates"][i][1], "lon": pool["coordinates"][i][0]}
                   for i in indexes]
    matrix = {
        (i, j): {"km": pool["distance_m"][a][b] / 1000,
                 "min": pool["duration_s"][a][b] / 60}
        for i, a in enumerate(indexes) for j, b in enumerate(indexes)
    }
    rows = [stop(i, rng.randint(2, 20), rng.randint(1, 4),
                 rng.choice((3, 5, 8)) if stress else rng.choice((0, 5, 10)),
                 lat=coordinates[i + 1]["lat"], lon=coordinates[i + 1]["lon"])
            for i in range(n)]
    if not stress and seed % 3 == 2:
        for row in rows:
            _set_window(row, rng, double=seed % 2 == 0)
    total = sum(row["peso_kg"] for row in rows)
    packages = sum(row["colli"] for row in rows)
    resources = [
        resource(max(max(row["peso_kg"] for row in rows),
                     math.ceil(total / count * (1.20 if stress else 1.45))),
                 max(5, math.ceil(packages / count * (1.30 if stress else 1.60))),
                 schedule=_schedule(index, seed, pauses=True), max_minutes=540)
        for index in range(count)
    ]
    prefix = "stress-road" if stress else "small-road"
    result = make_case(f"{prefix}-{area}-n{n}-m{count}-{seed:02d}",
                       f"{prefix.replace('-', '_')}_{area}", rows, matrix, resources,
                       seed=seed, returning=seed % 2 == 0, exact=not stress,
                       coordinates=coordinates)
    result["road_fixture"] = {"area": area, "indexes": indexes,
                              "path": "tests/fixtures/road_margin_matrices.json"}
    return result


def small_road_cases():
    return [_road_case(area, 5 + seed % 3, 2 + seed % 2, seed)
            for area in ROAD_AREAS for seed in range(6)]


def stress_synthetic_cases():
    cases = []
    for n in (15, 30, 50, 100):
        for count in (2, 3, 5, 10):
            for returning in (False, True):
                seed = n * 100 + count * 10 + int(returning)
                rng = random.Random(seed)
                matrix, coordinates = _synthetic_geometry(rng, n, spread=20)
                rows = [stop(i, rng.randint(2, 12), rng.randint(1, 3),
                             rng.choice((2, 3, 5)),
                             lat=coordinates[i + 1]["lat"], lon=coordinates[i + 1]["lon"])
                        for i in range(n)]
                total = sum(row["peso_kg"] for row in rows)
                packages = sum(row["colli"] for row in rows)
                resources = [
                    resource(max(15, math.ceil(total / count * 1.25)),
                             max(5, math.ceil(packages / count * 1.25)),
                             schedule=_schedule(index, seed, pauses=True), max_minutes=540)
                    for index in range(count)
                ]
                cases.append(make_case(
                    f"stress-synthetic-n{n}-m{count}-return{int(returning)}",
                    "stress_synthetic", rows, matrix, resources, seed=seed,
                    returning=returning, exact=False, coordinates=coordinates))
    return cases


def stress_road_cases():
    return [_road_case(area, n, count, 100 + n + count, stress=True)
            for area in ROAD_AREAS for n in (15, 30, 50) for count in (3, 5)]


def all_cases():
    """Return 196 distinct cases; 146 have exhaustive-size references."""
    result = (curated_cases() + small_synthetic_cases() + small_road_cases()
              + stress_synthetic_cases() + stress_road_cases())
    assert len(result) == 196
    assert len({item["id"] for item in result}) == len(result)
    assert sum(item["exact"] for item in result) == 146
    return result
