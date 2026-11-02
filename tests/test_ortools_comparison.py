"""Optional checks for the offline OR-Tools comparison adapter."""
import pytest
pytest.importorskip('ortools')
import os
from unittest.mock import patch
with patch.dict(os.environ):
    from run_ortools_comparison import make_case, solve_google, rank
from routing_quality_oracle import solve_fleet


def test_small_comparison_matches_independent_exhaustive_reference():
    case=make_case(6,1102)
    result=solve_google(case,2)
    exact=solve_fleet(case,'efficient')
    assert result['metrics']['feasible']
    assert rank(result['metrics'])==rank(exact['metrics'])


def test_impossible_window_is_excluded_not_delivered_late():
    case=make_case(6,1102,impossible=True)
    result=solve_google(case,2)['metrics']
    exact=solve_fleet(case,'efficient')
    assert result['feasible'] and result['lateness']==0
    assert 0 in result['unassigned'] and result['served']==5
    assert rank(result)==rank(exact['metrics'])


def test_unsupported_breaks_cannot_be_silently_ignored():
    case=make_case(6,1102)
    case['resources'][0]['driver_schedule']['breaks']=[{'start':'12:00','end':'13:00'}]
    with pytest.raises(AssertionError):solve_google(case,1)
