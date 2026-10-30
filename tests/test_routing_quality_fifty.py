"""New fifty-delivery comparisons preserve roads and exercise real fleet search."""
from copy import deepcopy
import math

import pytest

from routing_quality_fifty import fifty_cases
from routing_quality_fleet import run_fleet
from routing_quality_oracle import plan_metrics
from run_routing_quality_audit import effective_case, inspect_answer, reference_for


def test_same_fifty_roads_are_used_for_all_four_resource_counts():
    cases = fifty_cases()
    assert len(cases) == 8
    assert {len(case['resources']) for case in cases} == {2, 3, 4, 5}
    matrix = cases[0]['matrix']
    geometry = [(row['customer_id'], row['lat'], row['lon']) for row in cases[0]['stops']]
    for case in cases:
        assert case['matrix'] == matrix
        assert [(row['customer_id'], row['lat'], row['lon']) for row in case['stops']] == geometry
        assert len(case['stops']) == 50
        assert case['resources'][0]['capacita_colli'] == math.ceil(50 / len(case['resources']))


def test_independent_witness_proves_complete_coverage_even_with_windows_and_breaks():
    for case in fifty_cases():
        before = deepcopy(case)
        witness = plan_metrics(effective_case(case), case['witness'])
        assert witness['feasible']
        assert witness['served'] == 50 and witness['used'] == len(case['resources'])
        if case['profile'] == 'constrained':
            assert all(resource['driver_schedule']['breaks'] for resource in case['resources'])
            assert all(row.get('scarico_mattina_da') or row.get('scarico_pomeriggio_da')
                       for row in case['stops'])
        assert case == before


@pytest.mark.parametrize('count', [2, 3, 4, 5])
@pytest.mark.parametrize('strategy', ['efficient', 'balanced'])
def test_fifty_unconstrained_deliveries_fit_the_selected_fleet(count, strategy):
    case = next(case for case in fifty_cases()
                if case['profile'] == 'baseline' and len(case['resources']) == count)
    answer = run_fleet(case, strategy)
    report = inspect_answer(case, strategy, answer, reference_for(case, strategy))
    assert not report['errors']
    assert report['actual']['feasible'] and report['actual']['served'] == 50
    assert report['actual']['used'] == count
    assert answer['external_calls'] == 0 and answer['routing_matrix_calls'] == 1
