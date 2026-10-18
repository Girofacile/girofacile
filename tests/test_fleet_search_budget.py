"""Bounded search keeps the initial feasible plan without routing or a clock budget."""
import pytest
from app.services.fleet_search import optimize_fleet, candidate_limit


@pytest.mark.parametrize("budget", [0, 1, 23, 100])
@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_hundred_stop_search_respects_budget_and_keeps_full_floor(monkeypatch, budget, strategy):
    monkeypatch.setenv("FLEET_MAX_CANDIDATES", str(budget))
    rows = [{"peso_kg": 1, "colli": 1} for _ in range(100)]
    initial = [tuple(range(resource * 10, (resource + 1) * 10)) for resource in range(10)]
    calls = []
    def result(sequence):
        value = float(len(sequence) + 1)
        return {"total_min": value, "total_km": value, "_objective": (value, value, 0, 0)}
    def evaluate(sequence, resource):
        calls.append((sequence, resource))
        return result(sequence) if len(sequence) <= 10 else None
    matrix = {(i, j): {"km": float(i != j), "min": float(i != j)}
              for i in range(101) for j in range(101)}
    kwargs = dict(initial_routes=initial, initial_results=[result(order) for order in initial],
                  matrix=matrix)
    orders, results, diagnostics = optimize_fleet(rows, 10, evaluate, strategy, **kwargs)
    assert len(calls) <= budget
    assert diagnostics["additional_evaluations"] == len(calls)
    assert not diagnostics["global_optimum_proven"]
    assert sorted(index for order in orders for index in order) == list(range(100))
    assert all(len(order) <= 10 for order in orders)
    assert all(value is not None for value in results)
    repeated, _, repeated_diagnostics = optimize_fleet(rows, 10, evaluate, strategy, **kwargs)
    assert repeated == orders
    assert repeated_diagnostics == diagnostics
    if budget == 0:
        assert orders == tuple(initial)
        assert calls == []


@pytest.mark.parametrize("value, expected", [("-1", 0), ("9999999", 100000), ("garbage", 5000)])
def test_candidate_configuration_is_bounded(monkeypatch, value, expected):
    monkeypatch.setenv("FLEET_MAX_CANDIDATES", value)
    assert candidate_limit(100) == expected


def test_exact_search_keeps_sub_minute_objective_precision():
    # The displayed durations tie; the unrounded scheduler objective must decide.
    rows = [{}, {}]
    def evaluate(order, resource):
        duration = 10.04 if order == (0, 1) else 10.01
        if len(order) == 1:
            duration = 8.0
        return {"total_min": round(duration, 1), "total_km": 2.0,
                "_objective": (2.0, duration, 0, 0)}
    orders, _, diagnostics = optimize_fleet(rows, 1, evaluate, "efficient")
    assert orders == ((1, 0),)
    assert diagnostics["global_optimum_proven"]


def test_resource_alias_reuses_only_explicit_semantic_equivalence():
    rows = [{}, {}, {}]
    calls = []
    def evaluate(order, resource):
        calls.append((order, resource))
        value = float(len(order))
        return {"total_min": value, "total_km": value, "_objective": (value, value, 0, 0)}
    orders, _, _ = optimize_fleet(rows, 2, evaluate, "balanced",
                                  resource_signatures=["equivalent", "equivalent"])
    assert len(calls) == 15  # 3 singletons, 6 pairs and 6 complete permutations.
    assert sorted(index for order in orders for index in order) == [0, 1, 2]


def test_floating_time_noise_does_not_prefer_more_kilometres():
    def evaluate(order, resource):
        duration=10.0 if order==(0,1) else 10.0-1e-14
        km=2.0 if order==(0,1) else 9.0
        return {"total_min":duration,"total_km":km,"_objective":(km,duration,0,0)}
    orders,_,_=optimize_fleet([{},{}],1,evaluate,"efficient")
    assert orders==((0,1),)
