"""The complementary constructor shares a strict budget and current constraints."""
from copy import deepcopy

import pytest

from app.services.fleet_seed_search import optimize_seed


def score(order):
    value = float(len(order) + 1)
    return {"total_min": value, "total_km": value,
            "_objective": (value, value, 0, 0)}


@pytest.mark.parametrize("budget", [0, 1, 23, 100])
@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_explicit_budget_preserves_a_valid_full_incumbent(monkeypatch, budget, strategy):
    # The outer solver owns the quota. An unrelated environment value must not
    # cause this nested constructor to claim or spend a separate global budget.
    monkeypatch.setenv("FLEET_MAX_CANDIDATES", "100000")
    rows = [{"peso_kg": 1, "colli": 1} for _ in range(12)]
    untouched = deepcopy(rows)
    initial = (tuple(range(6)), tuple(range(6, 12)))
    calls = []

    def evaluate(order, resource):
        calls.append((order, resource))
        return score(order) if len(order) <= 6 else None

    kwargs = dict(budget=budget, initial_routes=initial,
                  initial_results=tuple(score(order) for order in initial))
    orders, results, diagnostics = optimize_seed(rows, 2, evaluate, strategy, **kwargs)
    assert diagnostics["additional_evaluations"] == len(calls) <= budget
    assert diagnostics["candidate_budget"] == budget
    assert not diagnostics["global_optimum_proven"]
    assert sorted(index for order in orders for index in order) == list(range(12))
    assert all(len(order) <= 6 for order in orders)
    assert all(result is not None for result in results)
    assert rows == untouched
    if budget == 0:
        assert orders == initial and calls == []
    previous_calls = list(calls)
    calls.clear()
    repeated, _, repeated_diagnostics = optimize_seed(rows, 2, evaluate, strategy, **kwargs)
    assert repeated == orders and repeated_diagnostics == diagnostics
    assert calls == previous_calls


def test_small_input_still_uses_the_explicit_budget_without_an_exact_bypass():
    calls = []

    def evaluate(order, resource):
        calls.append((order, resource))
        return score(order)

    orders, _, diagnostics = optimize_seed([{}, {}], 1, evaluate, "efficient", budget=1)
    assert len(calls) == diagnostics["additional_evaluations"] <= 1
    assert not diagnostics["global_optimum_proven"]
    assert len({index for order in orders for index in order}) <= 2


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_recovers_a_delivery_without_relaxing_capacity_or_required_tail_lift(monkeypatch, strategy):
    monkeypatch.setenv("FLEET_MAX_CANDIDATES", "0")
    rows = [{"peso_kg": 1, "colli": 1, "sponda": index == 7} for index in range(8)]
    # The equipped vehicle is full, while the other vehicle has a free slot.
    # Serving the pending tail-lift job requires changing the existing grouping.
    initial = ((0, 1, 2), (3, 4, 5, 6))
    calls = []

    def evaluate(order, resource):
        calls.append((order, resource))
        if len(order) > 4 or (7 in order and resource == 0):
            return None
        return score(order)

    orders, results, diagnostics = optimize_seed(
        rows, 2, evaluate, strategy, budget=1000,
        initial_routes=initial, initial_results=tuple(score(order) for order in initial),
    )
    assert sorted(index for order in orders for index in order) == list(range(8))
    assert all(len(order) <= 4 for order in orders)
    assert 7 not in orders[0] and 7 in orders[1]
    assert all(result is not None for result in results)
    assert 1 < len(calls) == diagnostics["additional_evaluations"] <= 1000
    assert diagnostics["equipment_policy"] == "caller-enforced"
