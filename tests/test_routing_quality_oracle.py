"""Hand-calculated checks of the new independent audit reference.

These fixtures do not use the application, its scheduler, or older benchmarks.
Each expected number follows directly from the short itinerary in the test.
"""
from copy import deepcopy

import pytest

from routing_quality_oracle import replay, solve_fleet, solve_single


def stop(index, **changes):
    row = dict(customer_id=index + 1, peso_kg=0, colli=0,
               tempo_scarico_min=0, ztl=False, sponda=False)
    row.update(changes)
    return row


def resource(**changes):
    row = dict(capacita_kg=None, capacita_colli=None, ha_sponda=True,
               accesso_ztl=True, max_minutes=720, driver_schedule={})
    row.update(changes)
    return row


def case(rows, resources=None, *, returning=False, minutes=10, edges=None):
    matrix = {(i, j): dict(km=0 if i == j else 1,
                          min=0 if i == j else minutes)
              for i in range(len(rows) + 1) for j in range(len(rows) + 1)}
    if edges:
        matrix.update({edge: dict(km=km, min=duration)
                       for edge, (km, duration) in edges.items()})
    return dict(id='hand-calculated-reference', kind='single', stops=rows,
                resources=resources or [resource()], matrix=matrix,
                start_time='08:00', return_depot=returning)


def test_empty_itinerary_does_not_charge_travel_or_shift_time():
    data = case([stop(0)], [resource(driver_schedule={
        'start': '09:00', 'end': '17:00', 'breaks': []})])
    result = replay(data, 0, ())
    assert result['feasible']
    assert result['km'] == result['minutes'] == result['wait'] == 0
    assert result['violations'] == result['lateness'] == 0


def test_open_and_closed_tour_have_different_directed_optima():
    data = case([stop(0), stop(1)], edges={
        (0, 1): (1, 1), (1, 2): (1, 1), (2, 0): (10, 10),
        (0, 2): (4, 4), (2, 1): (1, 1), (1, 0): (1, 1),
    })
    opened = solve_single(data)
    assert tuple(opened['orders'][0]) == (0, 1)
    assert opened['metrics']['km'] == 2
    data['return_depot'] = True
    closed = solve_single(data)
    assert tuple(closed['orders'][0]) == (1, 0)
    assert closed['metrics']['km'] == 6
    assert opened['optimality_proven'] and closed['optimality_proven']


def test_single_tour_minimizes_distance_before_duration():
    data = case([stop(0), stop(1)], returning=True, edges={
        (0, 1): (1, 50), (1, 2): (1, 50), (2, 0): (1, 50),
        (0, 2): (2, 1), (2, 1): (2, 1), (1, 0): (2, 1),
    })
    result = solve_single(data)
    assert tuple(result['orders'][0]) == (0, 1)
    assert result['metrics']['km'] == 3
    assert result['metrics']['minutes'] == 150


def test_window_requires_service_completion_and_includes_exact_closing():
    data = case([stop(0, tempo_scarico_min=10, scarico_mattina_da='08:00',
                      scarico_mattina_a='08:20')])
    exact = replay(data, 0, (0,))
    assert exact['feasible'] and exact['minutes'] == 20
    data['stops'][0]['tempo_scarico_min'] = 10.25
    late = replay(data, 0, (0,))
    assert not late['feasible']
    assert late['violations'] >= 1
    assert late['lateness'] == pytest.approx(.25)


def test_later_window_is_usable_when_morning_service_cannot_finish():
    data = case([stop(0, tempo_scarico_min=20,
                      scarico_mattina_da='08:00', scarico_mattina_a='08:15',
                      scarico_pomeriggio_da='09:00', scarico_pomeriggio_a='10:00')])
    result = replay(data, 0, (0,))
    # Arrive 08:10; morning has only five minutes. Wait fifty minutes and
    # finish the twenty-minute service at 09:20.
    assert result['feasible']
    assert result['minutes'] == 80
    assert result['wait'] == 50


def test_break_inside_window_wait_is_not_added_twice():
    schedule = dict(start='08:00', end='17:00',
                    breaks=[dict(start='08:15', end='08:45')])
    data = case([stop(0, tempo_scarico_min=10, scarico_mattina_da='09:00',
                      scarico_mattina_a='10:00')],
                [resource(driver_schedule=schedule)], minutes=5)
    result = replay(data, 0, (0,))
    assert result['feasible']
    assert result['minutes'] == 70
    assert result['wait'] == 55


def test_rest_that_displaces_morning_opening_does_not_add_opening_warning():
    schedule = dict(start='08:00', end='17:00',
                    breaks=[dict(start='08:20', end='08:40')])
    data = case([stop(0, tempo_scarico_min=7, sponda=True,
                      scarico_mattina_da='08:26', scarico_mattina_a='08:35',
                      scarico_pomeriggio_da='08:40', scarico_pomeriggio_a='09:15')],
                [resource(driver_schedule=schedule)], returning=True, minutes=7)
    result = replay(data, 0, (0,))
    assert result['feasible']
    assert result['minutes'] == 54 and result['wait'] == 33
    # Ready after rest at 08:40, exactly when the second window opens.
    # The lift requirement remains one informational warning.
    assert result['warnings'] == 1


def test_travel_can_resume_after_a_break():
    schedule = dict(start='08:00', end='17:00',
                    breaks=[dict(start='08:10', end='08:30')])
    data = case([stop(0)], [resource(driver_schedule=schedule)], minutes=30)
    result = replay(data, 0, (0,))
    # Ten minutes of travel, twenty-minute break, twenty remaining travel.
    assert result['feasible'] and result['minutes'] == 50
    assert result['wait'] == 0


def test_service_is_delayed_whole_when_it_would_cross_a_break():
    schedule = dict(start='08:00', end='17:00',
                    breaks=[dict(start='08:10', end='08:30')])
    data = case([stop(0, tempo_scarico_min=10)],
                [resource(driver_schedule=schedule)], minutes=5)
    result = replay(data, 0, (0,))
    # Arrive 08:05; the uninterrupted service starts 08:30, ends 08:40.
    assert result['feasible']
    assert result['minutes'] == 40 and result['wait'] == 25


def test_return_leg_also_crosses_declared_breaks():
    schedule = dict(start='08:00', end='17:00',
                    breaks=[dict(start='08:15', end='08:30')])
    data = case([stop(0)], [resource(driver_schedule=schedule)], returning=True,
                edges={(0, 1): (1, 10), (1, 0): (1, 20)})
    result = replay(data, 0, (0,))
    # Arrive 08:10; return five minutes, break fifteen, drive fifteen more.
    assert result['feasible']
    assert result['minutes'] == 45 and result['km'] == 2


def test_departure_before_shift_is_infeasible_and_shift_end_is_inclusive():
    data = case([stop(0, tempo_scarico_min=10)], [resource(driver_schedule={
        'start': '08:30', 'end': '09:00', 'breaks': []})], minutes=20)
    assert not replay(data, 0, (0,))['feasible']
    data['resources'][0]['driver_schedule'] = dict(start='08:00', end='08:30', breaks=[])
    assert replay(data, 0, (0,))['feasible']
    data['resources'][0]['driver_schedule']['end'] = '08:29'
    assert not replay(data, 0, (0,))['feasible']


def test_maximum_available_minutes_uses_ceiling_without_display_rounding():
    data = case([stop(0)], [resource(max_minutes=30)], minutes=30)
    data['kind'] = 'fleet'
    assert replay(data, 0, (0,))['feasible']
    data['matrix'][0, 1]['min'] = 30.001
    assert not replay(data, 0, (0,))['feasible']


def test_zero_capacity_is_real_while_none_is_unlimited():
    data = case([stop(0, peso_kg=1, colli=1)],
                [resource(capacita_kg=0, capacita_colli=0)])
    assert not replay(data, 0, (0,))['feasible']
    data['resources'][0].update(capacita_kg=None, capacita_colli=None)
    assert replay(data, 0, (0,))['feasible']
    data['resources'][0].update(capacita_kg=0, capacita_colli=0)
    data['stops'][0].update(peso_kg=0, colli=0)
    assert replay(data, 0, (0,))['feasible']


def test_fleet_strategies_have_different_proven_optima():
    data = case([stop(0), stop(1)], [resource(), resource()], returning=True)
    data['kind'] = 'fleet'
    efficient = solve_fleet(data, 'efficient')
    balanced = solve_fleet(data, 'balanced')
    assert efficient['metrics']['served'] == balanced['metrics']['served'] == 2
    assert efficient['metrics']['used'] == 1
    assert efficient['metrics']['minutes'] == 30
    assert balanced['metrics']['used'] == 2
    assert balanced['metrics']['makespan'] == 20
    assert balanced['metrics']['minutes'] == 40
    assert efficient['optimality_proven'] and balanced['optimality_proven']


def test_eight_stop_fleet_certificate_with_capacity_forced_equal_routes():
    data = case([stop(i, peso_kg=1, colli=1) for i in range(8)],
                [resource(capacita_kg=4, capacita_colli=4),
                 resource(capacita_kg=4, capacita_colli=4)], returning=True)
    data['kind'] = 'fleet'
    for strategy in ('efficient', 'balanced'):
        result = solve_fleet(data, strategy)
        metrics = result['metrics']
        # Full coverage forces four stops per vehicle. Each closed itinerary
        # has five identical legs: fifty minutes and five kilometres.
        assert metrics['served'] == 8
        assert metrics['used'] == 2
        assert sorted(len(order) for order in result['orders']) == [4, 4]
        assert metrics['makespan'] == 50
        assert metrics['minutes'] == 100
        assert metrics['km'] == 10
        assert result['optimality_proven']


def test_equipment_is_a_preference_before_fleet_usage_objective():
    data = case([stop(0, sponda=True)],
                [resource(ha_sponda=False), resource(ha_sponda=True)])
    data['kind'] = 'fleet'
    result = solve_fleet(data, 'efficient')
    assert tuple(result['orders'][0]) == ()
    assert tuple(result['orders'][1]) == (0,)
    assert result['metrics']['mismatches'] == 0


def test_fleet_coverage_has_priority_over_equipment_warning():
    data = case([stop(0, sponda=True), stop(1)],
                [resource(ha_sponda=False)])
    data['kind'] = 'fleet'
    result = solve_fleet(data, 'efficient')
    assert result['metrics']['served'] == 2
    assert result['metrics']['mismatches'] == 1
    assert result['optimality_proven']


def test_proven_best_partial_assignment_excludes_only_the_unservable_weight():
    data = case([stop(0, peso_kg=2), stop(1, peso_kg=1), stop(2, peso_kg=1)],
                [resource(capacita_kg=1), resource(capacita_kg=1)])
    data['kind'] = 'fleet'
    result = solve_fleet(data, 'efficient')
    assert result['metrics']['served'] == 2
    assert sorted(index for order in result['orders'] for index in order) == [1, 2]
    assert result['optimality_proven']


def test_single_infeasibility_is_proven_without_claiming_best_legacy_score():
    data = case([stop(0, peso_kg=2)], [resource(capacita_kg=1)])
    result = solve_single(data)
    assert result['feasibility_proven']
    assert not result['optimality_proven']


def test_reference_does_not_modify_input():
    data = case([stop(0), stop(1)], [resource(), resource()], returning=True)
    original = deepcopy(data)
    solve_single(data)
    solve_fleet(data, 'balanced')
    assert data == original
