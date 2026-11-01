"""Sparse MIP starts guide search without becoming extra constraints."""
from types import SimpleNamespace

import numpy as np
import pytest

from app.services.fleet_highs_start import _feasible_primal, solve_with_start


def model(cost, rows, lo, hi, *, lower=None, upper=None, integer=None):
    matrix = np.asarray(rows, dtype=float)
    ri, ci = np.nonzero(matrix)
    return SimpleNamespace(cost=list(cost), lower=lower or [0]*len(cost),
        upper=upper or [1]*len(cost), integer=integer or [1]*len(cost),
        ri=ri.tolist(), ci=ci.tolist(), values=matrix[ri, ci].tolist(), lo=list(lo), hi=list(hi))


def test_partial_hint_completes_unknown_variables():
    problem = model([3, 2, 1], [[1, 1, 1]], [2], [2])
    answer = solve_with_start(problem, 3, hint_indices=[1], hint_values=[1])
    assert answer.x is not None and sum(answer.x) == pytest.approx(2)
    assert answer.backend == 'highs-sparse-start'
    assert 'kOk' in answer.native_start_status
    assert all(value == pytest.approx(round(value)) for value in answer.x)


def test_conflicting_hint_does_not_override_model_constraints():
    problem = model([1, 2], [[1, 1]], [1], [1])
    answer = solve_with_start(problem, 3, hint_indices=[0, 1], hint_values=[1, 1])
    assert answer.x is not None and sum(answer.x) == pytest.approx(1)
    assert answer.status == 0


def test_infeasible_model_never_returns_the_supplied_hint_as_solution():
    problem = model([1, 2], [[1, 1]], [3], [3])
    answer = solve_with_start(problem, 3, hint_indices=[0], hint_values=[1])
    assert answer.x is None and answer.status == 2


def test_zero_allowance_skips_native_initialization_and_solve():
    answer = solve_with_start(None, 0, hint_indices=[0], hint_values=[1])
    assert answer.x is None and answer.status == 1
    assert answer.native_start_status == 'not-attempted'


def test_unavailable_native_api_falls_back_to_the_same_public_model(monkeypatch):
    from scipy.optimize._highspy import _core
    constructor = _core._Highs
    class WithoutStart:
        def __init__(self):
            self.engine = constructor()
        def __getattr__(self, name):
            if name == 'setSolution':
                raise AttributeError('Sparse start API unavailable for this build')
            return getattr(self.engine, name)
    monkeypatch.setattr(_core, '_Highs', WithoutStart)
    answer = solve_with_start(model([1, 2], [[1, 1]], [1], [1]), 3,
                              hint_indices=[0], hint_values=[1])
    assert answer.backend == 'scipy-public-milp-fallback'
    assert answer.x is not None and sum(answer.x) == pytest.approx(1)
    assert 'Sparse start API unavailable' in answer.native_start_error


@pytest.mark.parametrize('indices, values', [([0, 0], [1, 1]), ([2], [1]),
    ([.5], [1]), ([0], [float('nan')]), ([0, 1], [1])])
def test_invalid_sparse_hints_are_rejected(indices, values):
    with pytest.raises(ValueError):
        solve_with_start(model([1, 2], [[1, 1]], [1], [1]), 3,
                         hint_indices=indices, hint_values=values)


def test_fractional_or_constraint_violating_native_primal_is_rejected():
    from scipy.sparse import csc_array
    matrix = csc_array([[1., 1.]])
    args = (np.zeros(2), np.ones(2), np.ones(2), matrix, np.array([1.]), np.array([1.]))
    assert _feasible_primal([.5, .5], *args) is None
    assert _feasible_primal([1., 1.], *args) is None
    assert np.array_equal(_feasible_primal([1., 0.], *args), [1., 0.])
