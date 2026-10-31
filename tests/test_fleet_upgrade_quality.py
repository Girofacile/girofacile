"""Independent validation of fresh development and holdout fleet problems.

These checks validate the experimental inputs and their constructive witnesses.
They do not generate expected answers from the production search and do not
claim a global distance optimum for fifty-stop instances.
"""
from copy import deepcopy
import math

import pytest

from fleet_upgrade_cases import independent_energy_cost, upgrade_cases
from routing_quality_oracle import plan_metrics


@pytest.fixture(scope='module')
def cases_by_split():
    return {'development': upgrade_cases(holdout=False),
            'holdout': upgrade_cases(holdout=True)}


def _effective(case):
    result = deepcopy(case)
    margin = max(1.0, case.get('traffic_margin', 1.0))
    result['matrix'] = {edge: {**leg, 'min': leg['min'] * margin}
                        for edge, leg in case['matrix'].items()}
    return result


def _individually_compatible(stop, resource):
    return (
        (resource.get('capacita_kg') is None or stop['peso_kg'] <= resource['capacita_kg'])
        and (resource.get('capacita_colli') is None or stop['colli'] <= resource['capacita_colli'])
        and (not stop.get('sponda') or resource.get('ha_sponda', False))
    )


def test_development_and_holdout_are_reproducible_disjoint_experiments(cases_by_split):
    development, holdout = cases_by_split.values()
    assert development and holdout
    assert development == upgrade_cases(holdout=False)
    assert holdout == upgrade_cases(holdout=True)
    assert {case['id'] for case in development}.isdisjoint(case['id'] for case in holdout)
    assert {case['seed'] for case in development}.isdisjoint(case['seed'] for case in holdout)
    for split, cases in cases_by_split.items():
        assert all(case['split'] == split for case in cases)
        assert len({case['id'] for case in cases}) == len(cases)
        assert {len(case['resources']) for case in cases} == {2, 3, 4, 5}


def test_every_problem_has_fifty_identifiable_stops_and_complete_directed_roads(cases_by_split):
    for cases in cases_by_split.values():
        for case in cases:
            assert case['kind'] == 'fleet'
            assert len(case['stops']) == 50
            assert {stop['customer_id'] for stop in case['stops']} == set(range(1, 51))
            assert set(case['matrix']) == {(i, j) for i in range(51) for j in range(51)}
            for (origin, destination), leg in case['matrix'].items():
                assert math.isfinite(leg['km']) and math.isfinite(leg['min'])
                assert leg['km'] >= 0 and leg['min'] >= 0
                if origin == destination:
                    assert leg['km'] == leg['min'] == 0
            assert any(case['matrix'][i, j] != case['matrix'][j, i]
                       for i in range(51) for j in range(i + 1, 51))


def test_all_claimed_witnesses_pass_the_independent_calendar_and_equipment(cases_by_split):
    for cases in cases_by_split.values():
        for case in cases:
            before = deepcopy(case)
            witness = plan_metrics(_effective(case), case['witness'])
            assert witness['feasible'], (case['id'], witness)
            assert witness['served'] == case.get('expected_served', 50), case['id']
            assert witness['mismatches'] == 0, case['id']
            assert list(witness['unassigned']) == case.get('expected_unassigned', []), case['id']
            for resource, order in zip(case['resources'], case['witness']):
                assert all(_individually_compatible(case['stops'][index], resource)
                           for index in order), case['id']
            assert case == before


def test_vehicle_mix_and_loads_exercise_independent_capacity_dimensions(cases_by_split):
    for cases in cases_by_split.values():
        for case in cases:
            fuels = {resource.get('alimentazione') for resource in case['resources']}
            assert 'elettrico' in fuels and 'gasolio' in fuels, case['id']
            assert len({stop['peso_kg'] for stop in case['stops']}) > 1, case['id']
            assert len({stop['colli'] for stop in case['stops']}) > 1, case['id']
            assert all(resource['capacita_kg'] > 0 and resource['capacita_colli'] > 0
                       for resource in case['resources'])
            for resource in case['resources']:
                if resource['alimentazione'] == 'elettrico':
                    assert resource.get('consumo_kwh_100km', 0) > 0
                else:
                    assert resource.get('consumo_primario_100km', 0) > 0


def test_combined_families_really_include_windows_breaks_and_scarce_tail_lifts(cases_by_split):
    for cases in cases_by_split.values():
        combined = [case for case in cases if case['family'] == 'combined_tight']
        assert {len(case['resources']) for case in combined} == {2, 3, 4, 5}
        for case in combined:
            assert case.get('hard_tail_lift') is True
            assert {resource['ha_sponda'] for resource in case['resources']} == {False, True}
            assert any(stop.get('sponda') for stop in case['stops'])
            assert any(not stop.get('sponda') for stop in case['stops'])
            assert all(resource['driver_schedule'].get('start') and
                       resource['driver_schedule'].get('end') and
                       len(resource['driver_schedule'].get('breaks', [])) >= 2
                       for resource in case['resources'])
            assert any(stop.get('scarico_mattina_da') or stop.get('scarico_pomeriggio_da')
                       for stop in case['stops'])


def test_negative_coverage_bounds_follow_from_physical_incompatibility(cases_by_split):
    negative = [case for case in cases_by_split['development']
                if case.get('expected_served', 50) < 50]
    assert len(negative) >= 2
    for case in negative:
        blocked = case['expected_unassigned']
        assert blocked
        assert case.get('proof') or case.get('coverage_proof')
        assert case['expected_upper_bound'] == 50 - len(blocked)
        assert case['expected_served'] == case['expected_upper_bound']
        for index in blocked:
            assert not any(_individually_compatible(case['stops'][index], resource)
                           for resource in case['resources']), case['id']
        # A feasible witness attaining this necessary-condition bound certifies
        # maximum service coverage, without asserting minimum km or work hours.
        witness = plan_metrics(_effective(case), case['witness'])
        assert witness['feasible'] and witness['served'] == case['expected_upper_bound']


def test_electric_and_diesel_estimates_match_hand_calculated_energy_only_amounts():
    case = dict(kind='fleet', start_time='08:00', return_depot=False,
        stops=[dict(customer_id=1), dict(customer_id=2)],
        matrix={(i, j): dict(km=0 if i == j else 100, min=0 if i == j else 10)
                for i in range(3) for j in range(3)},
        resources=[dict(alimentazione='elettrico', consumo_kwh_100km=20,
                        energy_price_electric=.30),
                   dict(alimentazione='gasolio', consumo_primario_100km=8,
                        energy_price_primary=1.90)])
    assert independent_energy_cost(case, [[0], [1]]) == [6.0, 15.2]
    case['return_depot'] = True
    assert independent_energy_cost(case, [[0], [1]]) == [12.0, 30.4]
