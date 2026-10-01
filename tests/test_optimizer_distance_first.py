"""Distance-first decisions on independent directed distance/time matrices."""
import pytest
from app import optimizer as opt
from test_optimizer import offline, deliveries, constant_matrix, ids


@pytest.mark.parametrize("return_depot", [False, True])
@pytest.mark.parametrize("constraints", [False, True])
def test_shorter_route_wins_even_when_historical_score_prefers_speed(return_depot, constraints):
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 4}
    matrix[0, 2] = {"km": 2, "min": 1}
    if constraints:
        for row in rows:
            row.update(scarico_mattina_da="08:00", scarico_mattina_a="12:00", tempo_scarico_min=5)
    short = opt._evaluate_fixed_sequence(rows, matrix, [], return_depot=return_depot)
    fast = opt._evaluate_fixed_sequence(rows[::-1], matrix, [], return_depot=return_depot)
    assert short["violations"] == fast["violations"] == 0
    assert short["total_km"] < fast["total_km"] and short["total_min"] > fast["total_min"]
    assert short["score"] > fast["score"]
    assert ids(opt._best_internal_sequence(rows, matrix, [], return_depot=return_depot)) == [1, 2]


def test_equal_distance_prefers_faster_route():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1]["min"] = 4
    assert ids(opt._best_internal_sequence(rows, matrix, [])) == [2, 1]


def test_comparison_uses_unrounded_distance_and_includes_return():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1]["km"] = 0.999
    matrix[0, 1]["min"] = 4
    short = opt._evaluate_fixed_sequence(rows, matrix, [])
    fast = opt._evaluate_fixed_sequence(rows[::-1], matrix, [])
    assert short["total_km"] == fast["total_km"]
    assert opt.solution_key(short) < opt.solution_key(fast)
    matrix[2, 0]["km"] = 10
    assert ids(opt._best_internal_sequence(rows, matrix, [], return_depot=False)) == [1, 2]
    assert ids(opt._best_internal_sequence(rows, matrix, [], return_depot=True)) == [2, 1]


@pytest.mark.parametrize("n", [9, 16])
@pytest.mark.parametrize("relocate", [False, True])
def test_large_greedy_and_local_search_choose_shorter_slower_chain(n, relocate):
    rows, matrix = deliveries(n), constant_matrix(n, 2, 1)
    for a, b in zip([0, *range(1, n+1)], [*range(1, n+1), 0]):
        matrix[a, b] = {"km": 1, "min": 2}
    greedy = opt._greedy_sequence(rows[::-1], matrix, [])
    assert [d["customer_id"] for d in greedy] == list(range(1, n+1))
    # Start one swap away, so local search must accept a slower distance improvement.
    initial = rows[:]
    initial[0], initial[1] = initial[1], initial[0]
    before = opt._evaluate_fixed_sequence(initial, matrix, [])
    after = opt._local_optimize_sequence(initial, matrix, [], relocate=relocate)
    assert after["total_km"] == n+1 < before["total_km"]
    assert after["total_min"] > before["total_min"]
    assert ids(opt._best_internal_sequence(rows[::-1], matrix, [])) == list(range(1, n+1))


def test_candidate_feasibility_cannot_be_overridden_by_distance_or_load():
    short = opt.evaluate_candidate(480, {"km": 0.01, "min": 20},
        dict(scarico_mattina_da="08:00", scarico_mattina_a="08:10", peso_kg=1e12))
    valid = opt.evaluate_candidate(480, {"km": 100000, "min": 1}, {})
    assert valid["priority"] < short["priority"]
