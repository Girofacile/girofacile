"""Punto 1: deterministic characterization, no production algorithm changes."""
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from itertools import permutations
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")

import pytest

from app import optimizer as opt
from optimizer_benchmark import deliveries, exact_reference, metric_matrix, quality, reference_cost


# Fixed prefix family, selected offline for a local minimum at 9 stops.
# Manhattan distances satisfy triangle inequality; no random search runs in CI.
GRID = [(0, 0), (7, 11), (16, 7), (13, 14), (20, 6), (21, 7),
        (23, 14), (18, 8), (6, 22), (15, 14), (13, 23), (9, 13),
        (8, 23), (24, 12), (16, 2), (11, 22)]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Optimizer tests must never access external services")
    monkeypatch.setattr(opt.requests.sessions.Session, "request", forbidden)
    for name in ("osrm_route", "geocode", "google_route_matrix", "google_route_polyline"):
        monkeypatch.setattr(opt, name, forbidden)


def constant_matrix(n, km=1, minutes=5):
    return {(i, j): {"km": km, "min": minutes}
            for i in range(n+1) for j in range(n+1) if i != j}


def ids(result):
    return [d["customer_id"] for d in result["ordered"]]


@pytest.mark.parametrize("n,expected,reference", [
    (5, 70, 70), (8, 96, 96), (9, 108, 96),
    (10, 110, 98), (12, 110, 102), (15, 110, 106),
])
def test_quality_against_exact_reference(n, expected, reference, record_property):
    rows, matrix = deliveries(n), metric_matrix(GRID[:n+1])
    original = deepcopy(rows)
    result = opt._best_internal_sequence(rows, matrix, [])
    baseline = exact_reference(n, matrix)
    report = quality(result, baseline)
    record_property("quality", json.dumps(report, sort_keys=True))
    print(f"BENCHMARK n={n}: {json.dumps(report, sort_keys=True)}")
    assert rows == original
    assert sorted(ids(result)) == list(range(1, n+1))
    assert result["total_km"] == expected  # characterization, not arbitrary quality threshold
    assert baseline["total_km"] == reference
    assert result["total_min"] == expected * 2
    assert report["violations"] == report["wait_min"] == 0
    assert report["delta_km"] == expected-reference
    assert report["gap_km_pct"] == pytest.approx(100*(expected-reference)/reference)
    assert report["gap_min_pct"] == report["gap_km_pct"]
    initial = opt._evaluate_fixed_sequence(rows, matrix, [])
    assert result["score"] <= initial["score"]
    if n <= 8:
        assert result["score"] == baseline["score"]
    else:
        assert opt._best_internal_sequence(rows, matrix, []) == result


@pytest.mark.parametrize("return_depot", [False, True])
def test_exact_oracle_matches_independent_brute_force(return_depot):
    # Asymmetric matrix with independent minutes/km also validates oracle objective.
    matrix = {(i, j): {"km": (i*7+j*3) % 11+1, "min": (i*3+j*7) % 13+1}
              for i in range(5) for j in range(5) if i != j}
    costs = [reference_cost(p, matrix, return_depot) for p in permutations(range(1, 5))]
    best = min(10*c["total_min"]+c["total_km"] for c in costs)
    assert exact_reference(4, matrix, return_depot)["score"] == best
    assert opt._best_internal_sequence(deliveries(4), matrix, [], return_depot=return_depot)["score"] == best


def test_unique_small_optimum():
    rows, matrix = deliveries(4), constant_matrix(4, 50, 100)
    route = [0, 3, 1, 4, 2, 0]
    for a, b in zip(route, route[1:]):
        matrix[a, b] = {"km": 1, "min": 2}
    result = opt._best_internal_sequence(rows, matrix, [])
    assert ids(result) == route[1:-1]
    assert (result["total_km"], result["total_min"], result["return_time"]) == (5, 10, "08:10")


def test_nine_stops_are_trapped_in_a_local_minimum():
    rows, matrix = deliveries(9), metric_matrix(GRID[:10])
    greedy = opt._greedy_sequence(rows, matrix, [])
    before = opt._evaluate_fixed_sequence(greedy, matrix, [])
    local = opt._local_optimize_sequence(greedy, matrix, [])
    assert local["score"] <= before["score"]
    assert opt._best_internal_sequence(rows, matrix, []) == local
    lookup = {d["customer_id"]: d for d in rows}
    sequence = [lookup[i] for i in ids(local)]
    # Exhaust the actual neighborhood to distinguish a local minimum from the round cap.
    for i in range(8):
        for j in range(i+1, 9):
            swap = sequence[:]
            swap[i], swap[j] = swap[j], swap[i]
            reverse = sequence[:i] + sequence[i:j+1][::-1] + sequence[j+1:]
            for candidate in (swap, reverse):
                assert opt._evaluate_fixed_sequence(candidate, matrix, [])["score"] >= local["score"]
    assert opt._local_optimize_sequence(sequence, matrix, [], max_rounds=20) == local
    # Explicit witness: 12 km and 24 minutes less, with the same nine customers.
    witness = reference_cost([1, 8, 3, 9, 6, 5, 4, 7, 2], matrix)
    assert witness == {"total_km": 96, "total_min": 192}
    assert local["total_km"] == 108


def test_feasible_window_beats_shorter_route():
    rows, matrix = deliveries(2), constant_matrix(2)
    rows[1].update(scarico_mattina_da="08:00", scarico_mattina_a="08:15", tempo_scarico_min=5)
    matrix[1, 2] = {"km": 1, "min": 20}
    matrix[0, 2] = {"km": 8, "min": 5}
    short = opt._evaluate_fixed_sequence(rows, matrix, [])
    best = opt._best_internal_sequence(rows, matrix, [])
    assert short["violations"] == 1
    assert ids(best) == [2, 1]
    assert best["violations"] == 0
    assert best["total_km"] > short["total_km"]
    assert best["score"] < short["score"]


@pytest.mark.parametrize("clock,start,wait,end", [
    (480, 485, 0, 540), (545, 840, 290, 900), (830, 840, 5, 900),
])
def test_two_windows_choose_usable_slot(clock, start, wait, end):
    row = dict(scarico_mattina_da="08:00", scarico_mattina_a="09:00",
               scarico_pomeriggio_da="14:00", scarico_pomeriggio_a="15:00", tempo_scarico_min=10)
    ev = opt.evaluate_candidate(clock, {"km": 1, "min": 5}, row)
    assert ev["feasible"]
    assert (ev["service_start"], ev["wait"], ev["window_end"]) == (start, wait, end)


def test_afternoon_used_when_morning_cannot_fit_unloading():
    row = dict(scarico_mattina_da="08:00", scarico_mattina_a="09:00",
               scarico_pomeriggio_da="14:00", scarico_pomeriggio_a="15:00", tempo_scarico_min=20)
    ev = opt.evaluate_candidate(520, {"km": 1, "min": 5}, row)
    assert ev["feasible"]
    assert (ev["service_start"], ev["wait"], ev["window_end"]) == (840, 315, 900)


def test_twelve_stops_with_windows_and_unloading_are_stable():
    rows, matrix = deliveries(12), constant_matrix(12, 2, 5)
    for row in rows:
        row.update(tempo_scarico_min=10, scarico_mattina_da="08:00", scarico_mattina_a="12:00")
    first = opt._best_internal_sequence(rows, matrix, [])
    assert opt._best_internal_sequence(rows, matrix, []) == first
    # Every edge is equal; all permutations attain the same proven lower bound.
    report = quality(first, {"total_km": 26, "total_min": 185})
    assert report["gap_km_pct"] == report["gap_min_pct"] == 0
    assert report["violations"] == report["wait_min"] == 0
    assert first["ordered"][-1]["partenza_stimata"] == "11:00"
    assert first["return_time"] == "11:05"


def test_wait_and_unloading_propagate_to_next_stop():
    rows, matrix = deliveries(2), constant_matrix(2, 2, 10)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=20)
    rows[1]["tempo_scarico_min"] = 15
    result = opt._evaluate_fixed_sequence(rows, matrix, [])
    first, second = result["ordered"]
    assert (first["attesa_min"], first["arrivo_stimato"], first["partenza_stimata"]) == (50, "09:00", "09:20")
    assert (second["attesa_min"], second["arrivo_stimato"], second["partenza_stimata"]) == (0, "09:30", "09:45")
    assert result["total_wait"] == 50
    assert (result["total_min"], result["return_time"]) == (115, "09:55")
    assert result["violations"] == 0


@pytest.mark.parametrize("reverse,second_arrival", [(False, "08:40"), (True, "08:30")])
def test_unloading_for_equal_travel_sequences(reverse, second_arrival):
    rows, matrix = deliveries(2), constant_matrix(2)
    rows[0]["tempo_scarico_min"], rows[1]["tempo_scarico_min"] = 30, 20
    result = opt._evaluate_fixed_sequence(rows[::-1] if reverse else rows, matrix, [])
    assert result["ordered"][1]["arrivo_stimato"] == second_arrival
    assert (result["total_km"], result["total_min"], result["return_time"]) == (3, 65, "09:05")


@pytest.mark.parametrize("clock,service,feasible,warning", [
    (480, 10, True, ""), (480, 11, False, "dopo la chiusura"),
    (470, 20, False, "non completabile"), (496, 0, False, "Non fattibile"),
])
def test_window_requires_service_completion(clock, service, feasible, warning):
    row = dict(scarico_mattina_da="08:00", scarico_mattina_a="08:15", tempo_scarico_min=service)
    ev = opt.evaluate_candidate(clock, {"km": 1, "min": 5}, row)
    assert ev["feasible"] is feasible
    assert warning in ev["warning"]


def test_impossible_route_is_returned_with_warning_and_penalty():
    rows, matrix = deliveries(1), constant_matrix(1, 2, 20)
    rows[0].update(scarico_mattina_da="08:00", scarico_mattina_a="08:10")
    result = opt._best_internal_sequence(rows, matrix, [])
    assert result["violations"] == 1
    assert "Non fattibile" in result["ordered"][0]["warning"]
    assert result["score"] == 100000 + 40*10 + 25 + 4
    assert result["total_wait"] == 0


@pytest.mark.parametrize("return_depot,km,minutes,end", [(False, 4, 20, "08:20"), (True, 11, 35, "08:35")])
def test_return_depot_totals(return_depot, km, minutes, end):
    matrix = constant_matrix(2, 2, 10)
    matrix[2, 0] = {"km": 7, "min": 15}
    result = opt._evaluate_fixed_sequence(deliveries(2), matrix, [], return_depot=return_depot)
    assert (result["total_km"], result["total_min"], result["return_time"]) == (km, minutes, end)


@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
@pytest.mark.parametrize("return_depot", [False, True])
def test_public_entrypoints_use_one_stub_matrix(monkeypatch, entrypoint, return_depot):
    rows, matrix = deliveries(2), constant_matrix(2, 2, 10)
    for row in rows:
        row.pop("_matrix_index")
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=20)
    calls = []
    def stub(db, user_id, points, keys, **kwargs):
        calls.append((user_id, points, keys, kwargs))
        return matrix
    monkeypatch.setattr(opt, "build_distance_matrix", stub)
    monkeypatch.setattr(opt, "local_now", lambda: datetime(2029, 1, 1, tzinfo=timezone.utc))
    deposit = SimpleNamespace(id=1, user_id=7, lat=45, lon=9, indirizzo="Deposito")
    result = entrypoint(None, deposit, rows, return_depot=return_depot, route_date="2030-01-15")
    assert len(calls) == 1
    assert calls[0][0] == 7 and len(calls[0][1]) == 3
    assert calls[0][3] == {"start_time": "08:00", "route_date": "2030-01-15"}
    assert sorted(ids(result)) == [1, 2]
    # Replay chosen order through internal evaluator for public/internal agreement.
    indexed = {d["customer_id"]: dict(d, _matrix_index=d["customer_id"]) for d in rows}
    expected = opt._evaluate_fixed_sequence([indexed[i] for i in ids(result)], matrix, [], return_depot=return_depot)
    for field in ("total_km", "total_min", "return_time"):
        assert result[field] == expected[field]
    assert all("_matrix_index" not in d for d in result["ordered"])
    assert "score" not in result and "violations" not in result
    assert result["google_maps_url"].endswith("/Deposito") is return_depot
    if entrypoint is opt.recalculate_manual_route:
        assert ids(result) == [1, 2]


@pytest.mark.parametrize("vehicle", [None, {}, {"capacita_kg": None, "capacita_colli": None},
                                        {"capacita_kg": 100, "capacita_colli": 5}])
def test_capacity_at_limit_or_unspecified(vehicle):
    opt.validate_vehicle_load([{"peso_kg": 40, "colli": 2}, {"peso_kg": 60, "colli": 3}], vehicle)


@pytest.mark.parametrize("field,amount,capacity", [("peso_kg", 101, "capacita_kg"), ("colli", 101, "capacita_colli")])
@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
def test_overload_rejected_before_routing(monkeypatch, field, amount, capacity, entrypoint):
    monkeypatch.setattr(opt, "build_distance_matrix", lambda *a, **k: pytest.fail("overload reached routing"))
    with pytest.raises(ValueError, match="Capacità mezzo superata"):
        entrypoint(None, None, [{field: amount}], {capacity: 100})


@pytest.mark.parametrize("row", [{"peso_kg": -1}, {"peso_kg": float("nan")}, {"peso_kg": float("inf")},
                                {"colli": -1}, {"colli": 1.5}, {"colli": float("inf")}])
def test_invalid_cargo(row):
    with pytest.raises(ValueError, match="Peso e colli"):
        opt.validate_vehicle_load([row])


def test_ztl_and_tail_lift_remain_warnings():
    rows = deliveries(1)
    rows[0].update(ztl=True, sponda=True)
    result = opt._best_internal_sequence(rows, constant_matrix(1), [],
                                         vehicle={"ha_sponda": False, "accesso_ztl": False})
    assert result["violations"] == 0
    assert "sponda" in result["ordered"][0]["warning"]
    assert "ZTL" in result["ordered"][0]["warning"]
    assert result["score"] == 10*10 + 2*25 + 2


def test_time_and_km_are_weighted_not_lexicographic():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 20, "min": 1}
    matrix[0, 2] = {"km": 1, "min": 2}
    result = opt._best_internal_sequence(rows, matrix, [])
    faster = opt._evaluate_fixed_sequence(rows, matrix, [])
    assert ids(result) == [2, 1]
    assert result["total_min"] == 4 > faster["total_min"]
    assert result["score"] == 43 < faster["score"]


def test_empty_route_and_zero_reference():
    result = opt._best_internal_sequence([], {}, [])
    assert result["ordered"] == []
    assert result["total_km"] == result["total_min"] == 0
    assert result["return_time"] == "08:00"
    report = quality(result, {"total_km": 0, "total_min": 0})
    assert report["gap_km_pct"] is report["gap_min_pct"] is None
    assert report["delta_km"] == report["delta_min"] == 0


@pytest.mark.xfail(strict=True, reason="Known bug: parse_hhmm('00:00') is falsy and falls back to 08:00")
def test_midnight_departure_is_preserved():
    result = opt._evaluate_fixed_sequence(deliveries(1), constant_matrix(1), [], start_time="00:00")
    assert result["return_time"] == "00:10"
