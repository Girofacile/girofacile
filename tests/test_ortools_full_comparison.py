"""Il confronto completo usa casi con un testimone valido; OR-Tools resta facoltativo."""
import pytest

from run_ortools_full_comparison import large_case, winner
from routing_quality_oracle import plan_metrics


def test_large_case_has_independent_feasible_witness():
    case = large_case(40, 4, 'combined_tight', 2061100099)
    metrics = plan_metrics(case, case['witness'])
    assert metrics['feasible'] and metrics['served'] == 40
    assert all(len(r['driver_schedule']['breaks']) == 2 for r in case['resources'])
    assert any(row.get('scarico_mattina_da') for row in case['stops'])


def test_invalid_plan_always_loses():
    valid = {'objective': [-50, 0, 100.0, 500.0, 3]}
    assert winner(valid, {'objective': None}) == 'girofacile'
    assert winner({'objective': None}, valid) == 'ortools'
    assert winner(valid, {'objective': [-50, 0, 99.0, 900.0, 4]}) == 'ortools'


def test_ortools_model_serves_a_small_case():
    pytest.importorskip('ortools')
    from run_ortools_full_comparison import solve_ortools
    case = large_case(16, 2, 'windows_shifts', 2061100123)
    result = solve_ortools(case, 2)
    metrics = plan_metrics(case, result['orders'])
    assert metrics['feasible'] and metrics['served'] == 16
