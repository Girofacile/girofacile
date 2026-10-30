"""Verify that the new audit detects poor and invalid answers independently."""
from copy import deepcopy
from pathlib import Path

import pytest

from run_routing_quality_audit import (effective_case, first_difference, inspect_answer,
                                       reference_for, run_campaign, serializable_case)
from routing_quality_single import single_cases, run_single
from routing_quality_fleet import fleet_cases, run_fleet


def test_oracle_imports_neither_application_nor_historical_reference():
    import ast
    source = Path(__file__).with_name('routing_quality_oracle.py').read_text()
    tree = ast.parse(source)
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert set(imports) <= {'itertools', 'math'}


def test_audit_detects_a_nonoptimal_answer_in_an_exact_single_problem():
    case = single_cases(True)[0]
    reference = reference_for(case, 'single')
    poor = {'routes': [[2, 1, 0]], 'provider_calls': 0}
    report = inspect_answer(case, 'single', poor, reference)
    assert 'exact_objective_gap' in report['errors']
    assert report['comparison']['worse']


def test_duplicate_assignment_is_a_failure_even_when_totals_look_good():
    case = fleet_cases(True)[0]
    answer = {'routes': [[0, 1], [0, 2]]}
    report = inspect_answer(case, 'efficient', answer)
    assert 'fleet_contains_infeasible_or_duplicate_assignment' in report['errors']


def test_witness_is_independently_checked_before_it_is_trusted():
    case = deepcopy(fleet_cases(True)[0])
    case['reference'] = 'witness'
    case['witness'] = [[0, 1, 2], [3, 4, 5]]  # First load exceeds eighteen kg.
    reference = reference_for(case, 'efficient')
    answer = run_fleet(case, 'efficient')
    assert 'invalid_audit_witness' in inspect_answer(case, 'efficient', answer, reference)['errors']


def test_margins_copy_only_travel_time_and_preserve_input_and_distances():
    case = next(c for c in fleet_cases(True) if c['family'] == 'traffic-margin')
    before = deepcopy(case)
    effective = effective_case(case)
    assert case == before
    assert effective['matrix'][0, 1]['min'] == pytest.approx(case['matrix'][0, 1]['min'] * 1.15)
    assert effective['matrix'][0, 1]['km'] == case['matrix'][0, 1]['km']


def test_input_generation_is_frozen_and_provider_free_adapter_preserves_node_identity():
    a, b = single_cases(True), single_cases(True)
    assert [serializable_case(case) for case in a] == [serializable_case(case) for case in b]
    case = a[0]
    before = deepcopy(case)
    answer = run_single(case, input_order=list(reversed(range(len(case['stops'])))))
    report = inspect_answer(case, 'single', answer, reference_for(case, 'single'))
    assert not report['errors']
    assert answer['provider_calls'] == 0 and answer['matrix_calls'] == 1
    assert case == before


def test_rounding_cannot_hide_a_real_objective_gap():
    assert first_difference((0, 10.000001), (0, 10.0))['worse']
    assert first_difference((0, 10.0 + 1e-12), (0, 10.0)) is None


def test_new_quick_campaign_respects_constraints_and_proven_optima():
    report, cases, _ = run_campaign(quick=True, variants=False)
    assert report['summary']['cases'] == len(cases) >= 20
    assert report['summary']['errors'] == report['summary']['exact_gaps'] == 0
    assert report['summary']['external_calls'] == 0
