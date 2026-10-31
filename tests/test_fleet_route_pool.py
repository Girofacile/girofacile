"""Resource-specific candidate recombination, without application schedulers."""
from copy import deepcopy
import math

import pytest

from app.services.fleet_route_pool import RoutePool


def result(km, minutes=None):
    duration = km if minutes is None else minutes
    return {'total_km': km, 'total_min': duration, '_objective': (km, duration, 0, 0)}


def key(routes, results):
    return (-sum(map(len, routes)), sum(r['_objective'][0] for r in results if r),
            sum(r['_objective'][1] for r in results if r), sum(bool(r) for r in routes))


def test_pool_combines_memberships_that_need_three_coordinated_changes():
    pool = RoutePool(3, 12)
    initial = ((0, 1, 2), (3, 4, 5, 6), (7, 8, 9, 10))
    scores = (result(30), result(40), result(40))
    # Each replacement alone overlaps another incumbent route. Together the
    # three resource-specific replacements serve the previously missing stop.
    target = ((0, 3, 7, 11), (1, 4, 8, 9), (2, 5, 6, 10))
    for resource, order in enumerate(target):
        pool.add(resource, order, result(20 + resource))
    routes, results, diagnostics = pool.recombine(initial, scores, key, lambda a, b: a < b)
    assert routes == target
    assert key(routes, results) < key(initial, scores)
    assert len({i for order in routes for i in order}) == 12
    assert diagnostics['improved']
    assert diagnostics['scope'] == 'candidate-pool-only'
    assert not diagnostics['global_optimum_proven']


def test_candidates_never_move_to_a_different_resource():
    pool = RoutePool(2, 4)
    pool.add(0, (0, 1), result(1))
    pool.add(1, (2, 3), result(2))
    routes, _, _ = pool.recombine(((), ()), (None, None), key, lambda a, b: a < b)
    assert routes == ((0, 1), (2, 3))


def test_cheaper_order_for_incumbent_membership_is_not_overwritten_by_quality_floor():
    pool = RoutePool(2, 4)
    initial, scores = ((0, 1), (2, 3)), (result(20), result(20))
    pool.add(0, (1, 0), result(3))
    pool.add(1, (3, 2), result(4))
    routes, results, diagnostics = pool.recombine(initial, scores, key, lambda a, b: a < b)
    assert routes == ((1, 0), (3, 2))
    assert key(routes, results) == (-4, 7, 7, 2)
    assert diagnostics['improved']


def test_overlapping_candidate_routes_cannot_duplicate_a_delivery():
    pool = RoutePool(2, 4)
    pool.add(0, (0, 1, 2), result(2))
    pool.add(1, (1, 2, 3), result(1))
    routes, _, _ = pool.recombine(((), ()), (None, None), key, lambda a, b: a < b)
    flat = [index for order in routes for index in order]
    assert len(flat) == len(set(flat)) == 3


def test_unchanged_incumbent_is_preserved_when_pool_or_budget_is_unhelpful():
    pool = RoutePool(2, 4)
    initial, scores = ((0, 1), (2, 3)), (result(2), result(2))
    pool.add(0, (0, 2), result(100))
    pool.add(1, (1, 3), result(100))
    for budget in (0, 1, 100):
        routes, results, diagnostics = pool.recombine(initial, scores, key,
            lambda a, b: a < b, max_states=budget)
        assert routes == initial and results == scores
        assert not diagnostics['improved']
        assert diagnostics['generated_states'] <= budget


def test_inputs_and_stored_results_are_not_mutated_or_aliased():
    pool = RoutePool(2, 4)
    candidate = result(1)
    pool.add(0, (0, 1), candidate)
    candidate['_objective'] = (100, 100, 0, 0)
    initial, scores = ((), (2, 3)), (None, result(2))
    before = deepcopy((initial, scores))
    routes, results, _ = pool.recombine(initial, scores, key, lambda a, b: a < b)
    assert (initial, scores) == before
    assert results[0]['_objective'][0] == 1
    results[0]['_objective'] = (999, 999, 0, 0)
    assert pool.recombine(initial, scores, key, lambda a, b: a < b)[1][0]['_objective'][0] == 1


def test_explicitly_invalid_results_are_not_stored():
    pool = RoutePool(1, 2)
    assert not pool.add(0, (0,), None)
    assert not pool.add(0, (0,), {**result(1), 'violations': 1})
    assert not pool.add(0, (0,), {**result(1), 'feasible': False})
    with pytest.raises(ValueError): pool.add(0, (0, 0), result(1))
    with pytest.raises(ValueError): pool.add(0, (2,), result(1))
    with pytest.raises(ValueError): pool.add(1, (0,), result(1))
    with pytest.raises(ValueError): pool.add(0, (0,), result(math.nan))


def test_same_membership_keeps_the_order_matching_the_supplied_objective():
    pool = RoutePool(1, 2, route_key=lambda score: (score['_objective'][1], score['_objective'][0]))
    pool.add(0, (0, 1), result(1, 10))
    pool.add(0, (1, 0), result(2, 5))
    def fastest(routes, scores):
        return (-sum(map(len, routes)), sum(r['_objective'][1] for r in scores if r))
    routes, _, _ = pool.recombine(((),), (None,), fastest, lambda a, b: a < b)
    assert routes == ((1, 0),)


def test_memory_expansion_and_result_are_bounded_and_deterministic():
    pool = RoutePool(4, 50, max_options=8)
    for resource in range(4):
        for shift in range(40):
            order = tuple((shift + offset) % 50 for offset in range(3 + shift % 9))
            pool.add(resource, order, result(1 + shift % 7))
    assert all(len(entries) <= 16 for entries in pool._entries)
    initial, scores = ((),) * 4, (None,) * 4
    one = pool.recombine(initial, scores, key, lambda a, b: a < b, max_states=120)
    two = pool.recombine(initial, scores, key, lambda a, b: a < b, max_states=120)
    assert one == two
    assert one[2]['generated_states'] <= 120
    assert all(count <= 8 for count in one[2]['options_per_resource'])


def test_invalid_incumbent_cannot_be_a_quality_floor():
    pool = RoutePool(2, 3)
    with pytest.raises(ValueError):
        pool.recombine(((0, 1), (1, 2)), (result(1), result(1)), key, lambda a, b: a < b)
    with pytest.raises(ValueError):
        pool.recombine(((0,), ()), (None, None), key, lambda a, b: a < b)
