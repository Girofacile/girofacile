from copy import deepcopy
import json
from pathlib import Path
import random
import pytest
from app import optimizer as opt
from app.services.optimizer_search import (RouteEvaluator, CandidateBudget, bounded_descent,
    or_opt_moves, swap_moves, reversal_moves, candidate_limit, cheapest_insertion, nearest_neighbour)
import optimizer_legacy_reference as legacy
from optimizer_scaling_cases import scenario, exact_distance_reference
from test_optimizer import offline, deliveries, constant_matrix, ids


@pytest.mark.parametrize('n', [9, 15, 16, 20, 30, 50])
@pytest.mark.parametrize('kind', ['asymmetric', 'clusters', 'nearest_trap', 'windows'])
@pytest.mark.parametrize('back', [False, True])
def test_new_search_never_loses_legacy_candidate(n, kind, back):
    rows, matrix = scenario(n, kind)
    original = deepcopy(rows)
    before = legacy._best_internal_sequence(rows, matrix, [], return_depot=back)
    stats = {}
    after = opt._best_internal_sequence(rows, matrix, [], return_depot=back, diagnostics=stats)
    assert opt.solution_key(after) <= opt.solution_key(before)
    assert rows == original and sorted(ids(after)) == list(range(1, n + 1))
    assert stats['additional_candidates'] <= stats['candidate_budget']
    assert stats['candidates_evaluated'] == stats['baseline_candidates'] + stats['additional_candidates'] + 1
    assert '_search_order' not in after


@pytest.mark.parametrize('back', [False, True])
def test_score_only_replay_matches_full_schedule_for_mixed_constraints(back):
    rng = random.Random(6601)
    rows = deliveries(9)
    for i, row in enumerate(rows):
        row.update(tempo_scarico_min=i / 3, peso_kg=i * 43, colli=i,
                   ztl=i % 2 == 0, sponda=i % 3 == 0)
        if i % 3:
            row.update(scarico_mattina_da='08:05', scarico_mattina_a='08:25',
                       scarico_pomeriggio_da='08:35', scarico_pomeriggio_a='09:00')
    matrix = {(i, j): {'km': rng.random() * 20, 'min': rng.random() * 30}
              for i in range(10) for j in range(10) if i != j}
    vehicle = {'ha_sponda': False, 'accesso_ztl': False}
    evaluator = RouteEvaluator(rows, matrix, [], vehicle, back, '08:00')
    for _ in range(40):
        rng.shuffle(rows)
        fast = evaluator.evaluate(rows, include_details=False)
        full = opt._evaluate_fixed_sequence(rows, matrix, [], vehicle, back, '08:00')
        for field in fast:
            assert fast[field] == full[field], field
        assert opt.solution_key(fast) == opt.solution_key(full)


def test_or_opt_improves_a_proven_swap_reversal_and_relocate_local_minimum():
    data = json.loads((Path(__file__).parent/'fixtures/optimizer_or_opt.json').read_text())
    rows = deliveries(data['n'])
    matrix = {(i, j): value for i, line in enumerate(data['matrix']) for j, value in enumerate(line) if i != j}
    order = [rows[i-1] for i in data['order']]
    evaluator = RouteEvaluator(rows, matrix, [], None, True, '08:00')
    result = evaluator.evaluate(order, include_details=False)
    assert result['total_km'] == data['km']
    for generator in (swap_moves(order), reversal_moves(order), or_opt_moves(order, 1)):
        for candidate in generator:
            assert opt.solution_key(evaluator.evaluate(candidate, include_details=False)) >= opt.solution_key(result)
    without = bounded_descent(order, result, CandidateBudget(evaluator, 5000), 5000, block_lengths=(1,))[1]
    with_blocks = bounded_descent(order, result, CandidateBudget(evaluator, 5000), 5000)[1]
    assert without['total_km'] == data['km']
    assert with_blocks['total_km'] <= data['witness_km'] < data['km']


@pytest.mark.parametrize('limit', [0, 1, 7, 29, 300])
def test_budget_returns_best_seen_without_dropping_stops(monkeypatch, limit):
    rows, matrix = scenario(20, 'nearest_trap')
    monkeypatch.setenv('OPTIMIZER_MAX_CANDIDATES', str(limit))
    baseline = legacy._best_internal_sequence(rows, matrix, [])
    stats = {}
    result = opt._best_internal_sequence(rows, matrix, [], diagnostics=stats)
    assert opt.solution_key(result) <= opt.solution_key(baseline)
    assert sorted(ids(result)) == list(range(1, 21))
    assert stats['additional_candidates'] <= limit
    assert stats['optimization_budget_exhausted']
    if limit == 0:
        assert result == baseline


@pytest.mark.parametrize('value,expected', [('garbage', 10000), ('-1', 0), ('0', 0), ('300000', 200000)])
def test_budget_configuration_is_bounded(monkeypatch, value, expected):
    monkeypatch.setenv('OPTIMIZER_MAX_CANDIDATES', value)
    assert candidate_limit(50) == expected


def test_budget_returns_best_of_all_complete_candidates_actually_seen(monkeypatch):
    rows, matrix = scenario(20, 'clusters')
    monkeypatch.setenv('OPTIMIZER_MAX_CANDIDATES', '137')
    before = legacy._best_internal_sequence(rows, matrix, [])
    keys = [opt.solution_key(before)]
    original = CandidateBudget.evaluate
    def capture(self, order):
        result = original(self, order)
        if result is not None and len(order) == len(rows):
            keys.append(opt.solution_key(result))
        return result
    monkeypatch.setattr(CandidateBudget, 'evaluate', capture)
    result = opt._best_internal_sequence(rows, matrix, [])
    assert opt.solution_key(result) == min(keys)


def test_large_route_rejects_shorter_infeasible_window_order():
    rows, matrix = scenario(20, 'nearest_trap')
    rows[0].update(scarico_mattina_da='08:00', scarico_mattina_a='08:01')
    short = opt._evaluate_fixed_sequence(rows[1:] + rows[:1], matrix, [], return_depot=False)
    assert short['violations'] == 1
    result = opt._best_internal_sequence(rows, matrix, [], return_depot=False)
    assert result['violations'] == 0 and ids(result)[0] == 1
    assert result['total_km'] > short['total_km']


@pytest.mark.parametrize('n', [16, 30, 50])
def test_multistart_above_fifteen_is_repeatable_and_diagnostics_are_out_of_band(n):
    rows, matrix = scenario(n, 'clusters')
    first, second = {}, {}
    a = opt._best_internal_sequence(rows, matrix, [], diagnostics=first)
    b = opt._best_internal_sequence(rows, matrix, [], diagnostics=second)
    assert a == b
    assert len(first['seeds_evaluated']) > 1
    assert first['seeds_evaluated'] == second['seeds_evaluated']
    assert first['candidates_evaluated'] == second['candidates_evaluated']
    assert 'optimization_ms' not in a and 'optimizer_strategy' not in a


def test_eight_stop_result_and_enumeration_are_unchanged(monkeypatch):
    rows, matrix = scenario(8, 'asymmetric')
    monkeypatch.setenv('OPTIMIZER_MAX_CANDIDATES', '0')
    stats = {}
    after = opt._best_internal_sequence(rows, matrix, [], diagnostics=stats)
    assert after == legacy._best_internal_sequence(rows, matrix, [])
    assert stats['candidates_evaluated'] == 40321
    assert stats['optimizer_strategy'] == 'exact-permutations'
    oracle = exact_distance_reference(rows, matrix)
    assert (after['total_km'], after['total_min']) == (oracle['total_km'], oracle['total_min'])


def test_cheapest_insertion_escapes_directed_nearest_trap():
    rows, matrix = scenario(20, 'nearest_trap')
    nearest = opt._evaluate_fixed_sequence(nearest_neighbour(rows, matrix), matrix, [])
    inserted = opt._evaluate_fixed_sequence(cheapest_insertion(rows, matrix, True), matrix, [])
    assert inserted['total_km'] < nearest['total_km']


def test_search_builds_matrix_once_and_never_routes_variants(monkeypatch):
    rows, matrix = scenario(20, 'asymmetric')
    calls = []
    monkeypatch.setattr(opt.road_routing, 'build_matrix', lambda *a, **k: calls.append(1) or matrix)
    def forbidden(*a, **k): pytest.fail('Search contacted a provider')
    monkeypatch.setattr(opt.road_routing, 'osrm_table', forbidden)
    monkeypatch.setattr(opt, 'osrm_route', forbidden)
    result = opt._best_internal_sequence(rows, None, list(range(21)))
    assert len(calls) == 1 and len(result['ordered']) == 20


def test_duplicate_customer_labels_do_not_lose_matrix_identity():
    rows, matrix = scenario(16, 'asymmetric')
    for row in rows:
        row.update(customer_id=1, cliente_nome='Same', indirizzo='Same', lat=45, lon=9)
    result = opt._best_internal_sequence(rows, matrix, [])
    assert len(result['ordered']) == 16
    assert opt.solution_key(result) <= opt.solution_key(legacy._best_internal_sequence(rows, matrix, []))
