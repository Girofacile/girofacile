"""Native global assignment recovery, independently replayed by production time."""
from copy import deepcopy
import math

import pytest

from app import optimizer as opt
from app.services.fleet_milp_solver import solve_fleet_milp
from fleet_simulation_cases import resource, stop, uniform_matrix


def solve(rows, resources, *, matrix=None, returning=True, initial=None, evaluate_override=None):
    rows = deepcopy(rows)
    for i, row in enumerate(rows):
        row['_matrix_index'] = i+1
    points = [{'lat': 45, 'lon': 9}]+[{'lat': r['lat'], 'lon': r['lon']} for r in rows]
    matrix = matrix or uniform_matrix(len(rows), minutes=5)
    limits = [r.get('max_minutes', 540) for r in resources]
    calls = []
    def evaluate(order, v):
        calls.append((order, v))
        selected = [rows[i] for i in order]
        if any(r.get('sponda') for r in selected) and not resources[v].get('ha_sponda'):
            return None
        try:
            opt.validate_vehicle_load(selected, resources[v])
        except ValueError:
            return None
        score = opt._evaluate_fixed_sequence(selected, matrix, points, resources[v],
            returning, '08:00', include_details=False, earliest_windows=True)
        return None if score['violations'] or math.ceil(score['_objective'][1]) > limits[v] else score
    incumbent = initial or tuple(() for _ in resources)
    answer = solve_fleet_milp(rows, resources, matrix, points, '08:00', returning,
        limits, incumbent, evaluate_override or evaluate, max_seconds=3)
    return answer, calls


def test_joint_assignment_recovers_capacity_packing_and_required_lift():
    rows = [stop(i, weight=w, packages=p, service=1, sponda=i == 3)
            for i, (w, p) in enumerate(((3, 1), (1, 3), (2, 1), (1, 2)))]
    resources = [resource(4, 4, ha_sponda=False), resource(4, 4, ha_sponda=True)]
    (orders, scores, info), _ = solve(rows, resources, initial=((0,), (1,)))
    assert sorted(i for order in orders for i in order) == list(range(4))
    assert 3 in orders[1] and all(score is not None for score in scores)
    assert info['improvements'] == 1 and not info['global_optimum_proven']


def test_breaks_interrupt_driving_but_service_stays_contiguous():
    schedule = {'start': '08:00', 'end': '10:00', 'breaks': [
        {'start': '08:10', 'end': '08:25'}]}
    rows = [stop(0, service=10, scarico_mattina_da='08:00', scarico_mattina_a='08:40'),
            stop(1, service=5, scarico_mattina_da='08:40', scarico_mattina_a='09:15')]
    resources = [resource(schedule=schedule), resource(0, 0)]
    (orders, scores, info), _ = solve(rows, resources, matrix=uniform_matrix(2, minutes=12))
    assert orders == ((0, 1), ())
    assert scores[0]['_objective'][1] == pytest.approx(66)
    assert info['invalid_candidates'] == 0
    assert info['repair_stages'][-1]['method'] == 'global-unrestricted'


def test_dual_windows_and_asymmetric_matrix_have_one_joint_feasible_order():
    rows = [stop(0, service=5, scarico_mattina_da='08:00', scarico_mattina_a='08:05',
                 scarico_pomeriggio_da='09:00', scarico_pomeriggio_a='09:20'),
            stop(1, service=5, scarico_mattina_da='08:00', scarico_mattina_a='08:20')]
    resources = [resource(max_minutes=100), resource(0, 0)]
    matrix = uniform_matrix(2, minutes=10)
    matrix[0, 1]['min'] = 30
    (orders, _, info), _ = solve(rows, resources, matrix=matrix)
    assert orders == ((1, 0), ())
    assert info['invalid_candidates'] == 0


def test_zero_length_cycles_cannot_replace_a_connected_delivery_route():
    rows = [stop(i, service=0) for i in range(4)]
    resources = [resource(capacity=4, packages=4), resource(0, 0)]
    (orders, _, info), _ = solve(rows, resources, matrix=uniform_matrix(4, km=0, minutes=0))
    assert sorted(orders[0]) == list(range(4)) and orders[1] == ()
    assert info['invalid_candidates'] == 0


def test_impossible_total_capacity_keeps_the_valid_incumbent():
    rows = [stop(i, service=1) for i in range(3)]
    resources = [resource(1, 1), resource(1, 1)]
    (orders, _, info), _ = solve(rows, resources, initial=((0,), (1,)))
    assert orders == ((0,), (1,))
    assert info['status'] == 'model-infeasible' and not info['global_optimum_proven']


def test_canonical_rejection_never_replaces_the_incumbent():
    rows = [stop(i) for i in range(2)]
    resources = [resource(2, 2)]
    (orders, _, info), _ = solve(rows, resources, evaluate_override=lambda order, v: None)
    assert orders == ((),)
    assert info['status'] == 'canonical-rejection' and info['invalid_candidates'] == 1


def test_prepared_atomic_exchange_recovers_a_job_that_no_single_move_can_fit():
    # Weight is saturated on the first vehicle and parcels on the second.
    # No insertion or one-way ejection fits. Exchanging the two 3kg jobs with
    # different parcel counts creates the only room for the lift-required job.
    rows = [stop(i, weight=w, packages=p, service=1, sponda=i == 4)
            for i, (w, p) in enumerate(((3, 1), (5, 5), (3, 3), (3, 5), (2, 1)))]
    resources = [resource(8, 8, ha_sponda=False), resource(8, 8, ha_sponda=True)]
    (orders, scores, info), _ = solve(rows, resources, initial=((0, 1), (2, 3)))
    assert sorted(i for order in orders for i in order) == list(range(5))
    assert 4 in orders[1] and info['completed_stage'] == 'prepared-pair-exchange'
    assert info['canonical_candidates'] >= 1 and info['invalid_candidates'] == 0
    assert all(score is not None for score in scores)


def test_prepared_calendar_never_bypasses_canonical_rejection():
    rows = [stop(i, weight=w, packages=p, service=1, sponda=i == 4)
            for i, (w, p) in enumerate(((3, 1), (5, 5), (3, 3), (3, 5), (2, 1)))]
    resources = [resource(8, 8, ha_sponda=False), resource(8, 8, ha_sponda=True)]
    original = ((0, 1), (2, 3))
    score = {'total_km': 3, 'total_min': 17, '_objective': (3.0, 17.0, 0, 0)}
    def reject_changes(order, v):
        return deepcopy(score) if tuple(order) == original[v] else None
    (orders, _, info), _ = solve(rows, resources, initial=original,
                                 evaluate_override=reject_changes)
    assert orders == original
    assert info['repair_stages'][0]['canonical_candidates'] >= 1
    assert info['repair_stages'][0]['invalid_candidates'] >= 1
    assert info['invalid_candidates'] >= 1 and info['status'] == 'canonical-rejection'


def test_sparse_advisory_start_places_missing_job_without_fixing_existing_arcs():
    rows = [stop(i, weight=1, packages=1, service=1) for i in range(15)]
    resources = [resource(15, 15)]
    (orders, _, info), _ = solve(rows, resources, initial=(tuple(range(14)),))
    assert sorted(orders[0]) == list(range(15))
    stage = info['repair_stages'][-1]
    assert stage['method'] == 'global-unrestricted'
    assert stage['sparse_hint_variables'] > 0 and stage['fixed_arcs'] == 0
    assert stage['backend'] == 'highs-sparse-start'
    assert stage['has_solution'] and info['invalid_candidates'] == 0
