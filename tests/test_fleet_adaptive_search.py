"""Adaptive fleet search contracts; all evaluator data are local and invented."""
from copy import deepcopy

import pytest

from app.services.fleet_search import optimize_fleet, refine_routes, stable_stop_key


def result(km, minutes):
    return {'total_km': round(km, 2), 'total_min': round(minutes, 1),
            '_objective': (float(km), float(minutes), 0.0, 0)}


def test_efficient_prefers_fewer_kilometres_even_when_it_uses_another_vehicle():
    # Two separate trips total four kilometres; joining both customers costs
    # nine kilometres. This must not be traded away for the old vehicle count.
    def evaluate(order, resource):
        return result(2, 3) if len(order) == 1 else result(9, 4)
    orders, scores, info = optimize_fleet([{}, {}], 2, evaluate, 'efficient')
    assert sorted(map(len, orders)) == [1, 1]
    assert sum(score['_objective'][0] for score in scores) == 4
    assert info['global_optimum_proven']
    assert info['objective'] == 'distance-then-work-time'


def test_efficient_exact_order_uses_raw_distance_before_duration():
    values = {(0, 1): result(1.00001, 30), (1, 0): result(1.00002, 2),
              (0,): result(50, 1), (1,): result(50, 1)}
    orders, _, info = optimize_fleet([{}, {}], 1,
                                   lambda order, resource: values[order], 'efficient')
    assert orders == ((0, 1),)
    assert info['global_optimum_proven']


def test_balanced_keeps_its_workload_priority():
    def evaluate(order, resource):
        return result(2, 20) if len(order) == 1 else result(3, 30)
    orders, _, _ = optimize_fleet([{}, {}], 2, evaluate, 'balanced')
    assert sorted(map(len, orders)) == [1, 1]


def test_fixed_membership_refinement_uses_the_selected_strategy():
    values = {(0, 1): result(8, 40), (1, 0): result(10, 20)}
    evaluate = lambda order, resource: values[order]
    efficient, _, _ = refine_routes(((1, 0),), (values[1, 0],), evaluate,
                                     strategy='efficient')
    balanced, _, _ = refine_routes(((0, 1),), (values[0, 1],), evaluate,
                                    strategy='balanced')
    assert efficient == ((0, 1),)
    assert balanced == ((1, 0),)


def test_business_identity_ignores_request_indices_but_distinguishes_orders():
    original = {'customer_id': 5, 'order_refs': [{'id': 101}], 'lat': 44.5, 'lon': 9.2,
                'peso_kg': 3, 'scarico_mattina_da': '08:00', 'scarico_mattina_a': '10:00'}
    moved = {**original, '_matrix_index': 99, 'fleet_stop_index': 98}
    another = {**original, 'order_refs': [{'id': 102}]}
    assert stable_stop_key(original) == stable_stop_key(moved)
    assert stable_stop_key(original) != stable_stop_key(another)


def test_invalid_additional_incumbent_never_inflates_coverage(monkeypatch):
    monkeypatch.setenv('FLEET_MAX_CANDIDATES', '0')
    initial = (tuple(range(5)), tuple(range(5, 10)))
    scores = (result(10, 10), result(10, 10))
    invalid = ((tuple(range(6)), (5, 6, 7, 8, 9)), scores)
    invalid_none = ((tuple(range(5)), tuple(range(5, 10))), (scores[0], None))
    def forbidden(*args):
        pytest.fail('Zero budget must not run additional canonical replays')
    orders, _, info = optimize_fleet([{} for _ in range(10)], 2, forbidden, 'efficient',
        initial_routes=initial, initial_results=scores,
        initial_candidates=[invalid, invalid_none])
    assert orders == initial
    assert info['additional_evaluations'] == 0


@pytest.mark.parametrize('budget', [1, 30, 200])
def test_adaptive_reconstruction_and_pool_respect_one_deterministic_budget(monkeypatch, budget):
    monkeypatch.setenv('FLEET_MAX_CANDIDATES', str(budget))
    rows = [{'customer_id': index + 1, 'peso_kg': 1, 'colli': 1} for index in range(12)]
    matrix = {(a, b): {'km': float(a != b), 'min': float(a != b)}
              for a in range(13) for b in range(13)}
    initial = (tuple(range(6)), tuple(range(6, 12)))
    calls = []
    def evaluate(order, resource):
        calls.append((order, resource))
        return result(len(order) + 1, len(order) + 1) if len(order) <= 6 else None
    score = result(7, 7)
    before = deepcopy(rows)
    orders, _, info = optimize_fleet(rows, 2, evaluate, 'efficient',
        initial_routes=initial, initial_results=(score, score), matrix=matrix)
    assert len(calls) == info['additional_evaluations'] <= budget
    assert sorted(index for order in orders for index in order) == list(range(12))
    assert rows == before
    assert info['route_pool']['global_optimum_proven'] is False


def test_membership_rejections_leave_the_calendar_budget_for_possible_routes(monkeypatch):
    monkeypatch.setenv('FLEET_MAX_CANDIDATES', '80')
    rows = [{'customer_id': index + 1, 'peso_kg': 1, 'colli': 1} for index in range(12)]
    initial = (tuple(range(6)), tuple(range(6, 12)))
    calls = []
    def evaluate(order, resource):
        assert len(order) <= 6, 'An overloaded membership must never reach the scheduler'
        calls.append((order, resource))
        return result(len(order) + 1, len(order) + 1)
    orders, _, info = optimize_fleet(rows, 2, evaluate, 'efficient',
        initial_routes=initial, initial_results=(result(7, 7), result(7, 7)),
        membership_compatible=lambda order, resource: len(order) <= 6)
    assert sorted(index for order in orders for index in order) == list(range(12))
    assert info['membership_rejections'] > 0
    assert info['membership_checks'] > 0
    assert info['additional_evaluations'] == len(calls) <= 80
    assert info['established_search_seed']['shared_budget_allowance'] == 40


@pytest.mark.parametrize('count,family,strategy', [
    (2, 'geography_capacity', 'efficient'),
    (3, 'combined_tight', 'balanced'),
])
def test_fifty_deliveries_recover_capacity_and_calendar_coverage(count, family, strategy, monkeypatch):
    # Independent constructive witnesses prove that ALL fifty fit. These two
    # development counterexamples previously stranded four and two deliveries;
    # reverse input order must not make them disappear from a feasible plan.
    from fleet_upgrade_cases import upgrade_cases
    from routing_quality_fleet import run_fleet
    from routing_quality_oracle import plan_metrics
    monkeypatch.delenv('FLEET_MAX_CANDIDATES', raising=False)
    case = next(case for case in upgrade_cases()
                if len(case['resources']) == count and case['family'] == family)
    answer = run_fleet(case, strategy, input_order=list(reversed(range(50))))
    metrics = plan_metrics(case, answer['routes'])
    assert metrics['feasible']
    assert metrics['served'] == 50
    assert answer['unassigned'] == []
    assert answer['external_calls'] == 0
    assert answer['routing_matrix_calls'] == 1
