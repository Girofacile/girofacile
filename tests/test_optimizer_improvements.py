"""Punto 2: midnight, deterministic multi-start and directed/window regressions."""
from copy import deepcopy
from datetime import time
from functools import lru_cache
from types import SimpleNamespace
import pytest
from app import optimizer as opt
from optimizer_benchmark import deliveries, exact_reference
from optimizer_scenarios import directed_case, reordered, independent_window_reference
from test_optimizer import offline, constant_matrix, ids


@lru_cache(None)
def directed_optimum(n, return_depot):
    return exact_reference(n, directed_case(n)[1], return_depot)


@pytest.mark.parametrize("n", [9, 10, 12, 15])
@pytest.mark.parametrize("return_depot", [False, True])
@pytest.mark.parametrize("order", ["forward", "reverse", "interleaved"])
@pytest.mark.parametrize("windows", [False, True])
def test_directed_scenarios(n, return_depot, order, windows):
    canonical, matrix = directed_case(n, windows)
    rows = reordered(canonical, order)
    original = deepcopy(rows)
    greedy = opt._greedy_sequence(rows, matrix, [])
    before = opt._local_optimize_sequence(greedy, matrix, [], return_depot=return_depot)
    operator = opt._evaluate_fixed_sequence(rows, matrix, [], return_depot=return_depot)
    after = opt._best_internal_sequence(rows, matrix, [], return_depot=return_depot)
    assert rows == original
    assert sorted(ids(after)) == list(range(1, n + 1))
    assert after == opt._best_internal_sequence(rows, matrix, [], return_depot=return_depot)
    assert after["score"] <= min(before["score"], operator["score"])
    assert after["violations"] <= before["violations"]
    if windows:
        reference = independent_window_reference(canonical, matrix, return_depot)
        assert reference["violations"] == 0
        assert reference["total_wait"] > 0
        lookup = {d["customer_id"]: d for d in canonical}
        replay = independent_window_reference([lookup[i] for i in ids(after)], matrix, return_depot)
        for key in ("total_km", "total_min", "total_wait", "violations", "score"):
            assert after[key] == replay[key]
        assert after["violations"] == 0
    else:
        assert after["score"] >= directed_optimum(n, return_depot)["score"]


@pytest.mark.parametrize("start,expected", [("00:00", "00:10"), (time(0, 0), "00:10"),
    (None, "08:10"), ("", "08:10"), ("bad", "08:10"), ("25:00", "01:10")])
def test_internal_start_fallback_unchanged(start, expected):
    # Internal parsing intentionally remains permissive for out-of-range strings.
    result = opt._evaluate_fixed_sequence(deliveries(1), constant_matrix(1), [], start_time=start)
    assert result["return_time"] == expected


@pytest.mark.parametrize("start", ["00:00", time(0, 0)])
def test_greedy_preserves_midnight(start):
    rows = deliveries(2)
    rows[1].update(scarico_mattina_da="00:00", scarico_mattina_a="00:06")
    result = opt._greedy_sequence(rows, constant_matrix(2), [], start_time=start)
    assert [d["customer_id"] for d in result] == [2, 1]


@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
@pytest.mark.parametrize("return_depot", [False, True])
@pytest.mark.parametrize("n", [1, 9])
def test_public_midnight(monkeypatch, entrypoint, return_depot, n):
    calls = []
    def matrix(*args, **kwargs):
        calls.append(kwargs)
        return constant_matrix(n)
    monkeypatch.setattr(opt, "build_distance_matrix", matrix)
    rows = deliveries(n)
    depot = SimpleNamespace(id=1, user_id=1, lat=45, lon=9, indirizzo="Deposito")
    result = entrypoint(None, depot, rows, start_time="00:00", return_depot=return_depot, route_date="2099-01-15")
    assert result["ordered"][0]["arrivo_stimato"] == "00:05"
    assert result["total_min"] == (n + int(return_depot)) * 5
    assert result["return_time"] == f"00:{(n + int(return_depot)) * 5:02}"
    assert len(calls) == 1 and calls[0]["start_time"] == "00:00"


@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
@pytest.mark.parametrize("start", [None, "", "bad", "25:00", "08:61"])
def test_public_invalid_start_still_rejected(entrypoint, start):
    with pytest.raises(ValueError, match="Data o orario"):
        entrypoint(None, None, [], start_time=start, route_date="2099-01-15")


def test_fallback_does_not_repeat_routing_calls(monkeypatch):
    rows, matrix = directed_case(9)
    calls = []
    def road(a, b):
        calls.append((a, b))
        return matrix[a, b]
    monkeypatch.setattr(opt, "osrm_route", road)
    result = opt._best_internal_sequence(rows, None, list(range(10)))
    assert len(calls) == len(set(calls)) <= 90
    assert result == opt._best_internal_sequence(rows, matrix, [])


def test_operator_order_is_candidate_above_fifteen():
    rows, matrix = directed_case(16)
    operator = opt._evaluate_fixed_sequence(rows, matrix, [])
    result = opt._best_internal_sequence(rows, matrix, [])
    assert result["score"] <= operator["score"]


def test_finite_penalty_can_prefer_infeasible_route():
    # Existing score limitation: reproduce without changing weights or constraints.
    rows, matrix = deliveries(2), constant_matrix(2, km=1, minutes=1)
    rows[1].update(scarico_mattina_da="08:00", scarico_mattina_a="08:01")
    matrix[0, 2]["km"] = 200000
    infeasible = opt._evaluate_fixed_sequence(rows, matrix, [])
    feasible = opt._evaluate_fixed_sequence(rows[::-1], matrix, [])
    assert feasible["violations"] == 0 and infeasible["violations"] == 1
    assert infeasible["score"] < feasible["score"]
    assert opt._best_internal_sequence(rows, matrix, [])["violations"] == 1

def test_fallback_uses_no_additional_road_pairs(monkeypatch):
    rows, matrix = directed_case(9)
    points = list(range(10))
    calls = []
    def road(a, b):
        calls.append((a, b))
        return matrix[a, b]
    monkeypatch.setattr(opt, "osrm_route", road)
    # The unchanged greedy + swap/reversal path is the old fallback behavior.
    seed = opt._greedy_sequence(rows, None, points)
    opt._local_optimize_sequence(seed, None, points)
    old_calls = calls[:]
    calls.clear()
    opt._best_internal_sequence(rows, None, points)
    assert set(calls) <= set(old_calls)
    assert len(calls) <= len(old_calls)


def test_operator_candidate_is_kept_even_when_search_misses_it(monkeypatch):
    rows, matrix = deliveries(16), constant_matrix(16, km=20, minutes=20)
    for a, b in zip([0, *range(1, 17)], [*range(1, 17), 0]):
        matrix[a, b] = {"km": 1, "min": 1}
    good = opt._evaluate_fixed_sequence(rows, matrix, [])
    bad = opt._evaluate_fixed_sequence(rows[::-1], matrix, [])
    assert good["score"] < bad["score"]
    monkeypatch.setattr(opt, "_local_optimize_sequence", lambda *a, **k: bad)
    assert opt._best_internal_sequence(rows, matrix, []) == good
