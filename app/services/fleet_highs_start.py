"""Version-pinned HiGHS access for sparse, advisory MIP starts.

SciPy's public ``milp`` currently exposes no initial solution argument. Its
vendored HiGHS interface does. This small adapter isolates that private API,
keeps the matrix and bounds unchanged, and falls back to public SciPy when
the native interface is unavailable. Hints are never fixed constraints.
Canonical route replay remains the caller's final acceptance check.
"""
from __future__ import annotations

from time import perf_counter
import warnings


def _arrays(model):
    import numpy as np
    from scipy.sparse import coo_array

    cost = np.asarray(model.cost, dtype=np.float64)
    lower, upper = (np.asarray(values, dtype=np.float64)
                    for values in (model.lower, model.upper))
    integer = np.asarray(model.integer, dtype=np.int32)
    row_lower, row_upper = (np.asarray(values, dtype=np.float64)
                            for values in (model.lo, model.hi))
    shape = (len(row_lower), len(cost))
    matrix = getattr(model, '_compiled', None)
    if matrix is None or matrix.shape != shape:
        matrix = coo_array((np.asarray(model.values, dtype=np.float64),
            (np.asarray(model.ri, dtype=np.int32), np.asarray(model.ci, dtype=np.int32))),
            shape=shape).tocsc()
    else:
        matrix = matrix.tocsc(copy=True)
    matrix.indices = matrix.indices.astype(np.int32, copy=False)
    matrix.indptr = matrix.indptr.astype(np.int32, copy=False)
    if not (cost.shape == lower.shape == upper.shape == integer.shape):
        raise ValueError('MIP start model has inconsistent column arrays')
    if row_lower.shape != row_upper.shape:
        raise ValueError('MIP start model has inconsistent row arrays')
    if not np.all(np.isin(integer, (0, 1))):
        raise ValueError('MIP start adapter supports continuous and integer columns')
    return cost, lower, upper, integer, matrix, row_lower, row_upper


def _feasible_primal(values, lower, upper, integer, matrix, row_lower, row_upper):
    """Reject a native hint/relaxation masquerading as an integer incumbent."""
    import numpy as np

    values = np.asarray(values, dtype=np.float64)
    tolerance = 1e-6  # HiGHS' default MIP feasibility tolerance.
    if values.shape != lower.shape or not np.all(np.isfinite(values)):
        return None
    if np.any(values < lower-tolerance) or np.any(values > upper+tolerance):
        return None
    discrete = integer != 0
    if np.any(np.abs(values[discrete]-np.rint(values[discrete])) > tolerance):
        return None
    activity = matrix @ values
    if np.any(activity < row_lower-tolerance) or np.any(activity > row_upper+tolerance):
        return None
    return values.copy()


def solve_with_start(model, seconds, *, hint_indices=(), hint_values=()):
    """Return an OptimizeResult-compatible MIP result with an advisory start.

    ``model`` supplies cost/lower/upper/integer and sparse row construction
    arrays ri/ci/values/lo/hi, as used by the fleet MILP builder. Only explicitly
    supplied hint columns are suggested; all remaining columns stay unknown.
    Time spent loading and preparing the model consumes the same allowance.
    """
    import numpy as np
    from scipy.optimize import OptimizeResult

    started = perf_counter()
    if seconds <= 0:
        return OptimizeResult(status=1, success=False, x=None, fun=None,
            message='MIP start solve disabled: no remaining time', mip_node_count=0,
            backend='highs-sparse-start', native_start_status='not-attempted')
    arrays = _arrays(model)
    cost, lower, upper, integer, matrix, row_lower, row_upper = arrays
    raw_indices = np.asarray(hint_indices)
    values = np.asarray(hint_values, dtype=np.float64)
    if raw_indices.ndim != 1 or values.ndim != 1 or len(raw_indices) != len(values):
        raise ValueError('MIP start hint arrays must have matching one-dimensional lengths')
    if len(raw_indices) and (not np.all(np.isfinite(raw_indices))
            or not np.all(raw_indices == np.rint(raw_indices))
            or np.any(raw_indices < 0) or np.any(raw_indices >= len(cost))):
        raise ValueError('MIP start column index is invalid')
    indices = raw_indices.astype(np.int32)
    if len(set(indices.tolist())) != len(indices) or not np.all(np.isfinite(values)):
        raise ValueError('MIP start hints must be finite and use distinct columns')

    native_error = None
    try:
        from scipy.optimize._highspy import _core as core

        highs = core._Highs()
        options = {'output_flag': False, 'threads': 1, 'random_seed': 0,
                   'presolve': 'on', 'mip_rel_gap': 1.0}
        for name, value in options.items():
            if highs.setOptionValue(name, value) == core.HighsStatus.kError:
                raise RuntimeError(f'HiGHS rejected option {name}')
        lp = core.HighsLp()
        lp.num_col_, lp.num_row_ = matrix.shape[1], matrix.shape[0]
        lp.col_cost_, lp.col_lower_, lp.col_upper_ = cost, lower, upper
        lp.row_lower_, lp.row_upper_ = row_lower, row_upper
        lp.integrality_ = [core.HighsVarType.kInteger if flag else core.HighsVarType.kContinuous
                           for flag in integer]
        lp.a_matrix_.format_ = core.MatrixFormat.kColwise
        lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = matrix.shape[1], matrix.shape[0]
        lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = (
            matrix.indptr, matrix.indices, matrix.data)
        if highs.passModel(lp) == core.HighsStatus.kError:
            raise RuntimeError('HiGHS rejected the sparse model')
        remaining = float(seconds)-(perf_counter()-started)
        if remaining <= 0:
            return OptimizeResult(status=1, success=False, x=None, fun=None,
                message='Time limit reached while loading MIP start model', mip_node_count=0,
                backend='highs-sparse-start', native_start_status='not-attempted')
        # A native build may process/repair a partial start in setSolution().
        # Give that work the same remaining quota as the subsequent run().
        highs.setOptionValue('time_limit', remaining)
        hint_status = 'not-supplied'
        if len(indices):
            hint_status = str(highs.setSolution(len(indices), indices, values))
        remaining = float(seconds)-(perf_counter()-started)
        if remaining <= 0:
            return OptimizeResult(status=1, success=False, x=None, fun=None,
                message='Time limit reached while preparing MIP start', mip_node_count=0,
                backend='highs-sparse-start', native_start_status=hint_status)
        highs.setOptionValue('time_limit', remaining)
        run_status = highs.run()
        status = highs.getModelStatus()
        info, solution = highs.getInfo(), highs.getSolution()
        statuses = core.HighsModelStatus
        if status == statuses.kOptimal:
            mapped = 0
        elif status in (statuses.kTimeLimit, statuses.kIterationLimit, statuses.kSolutionLimit,
                        statuses.kObjectiveBound, statuses.kObjectiveTarget,
                        statuses.kInterrupt, statuses.kMemoryLimit):
            mapped = 1
        elif status == statuses.kInfeasible:
            mapped = 2
        elif status == statuses.kUnbounded:
            mapped = 3
        else:
            mapped = 4
        primal = None
        if (run_status != core.HighsStatus.kError and info.valid
                and int(info.primal_solution_status) == 2 and solution.value_valid):
            primal = _feasible_primal(solution.col_value, lower, upper, integer,
                                      matrix, row_lower, row_upper)
        return OptimizeResult(status=mapped, success=mapped == 0 and primal is not None,
            x=primal, fun=float(cost @ primal) if primal is not None else None,
            message=highs.modelStatusToString(status),
            mip_node_count=int(info.mip_node_count) if info.valid else 0,
            mip_gap=float(info.mip_gap) if info.valid else None,
            mip_dual_bound=float(info.mip_dual_bound) if info.valid else None,
            backend='highs-sparse-start', native_start_status=hint_status,
            native_model_status=int(status))
    except (ImportError, AttributeError, RuntimeError, TypeError) as exc:
        native_error = f'{type(exc).__name__}: {exc}'

    # The public path cannot use hints. It still receives exactly the same
    # model and only the time left after the failed native setup.
    from scipy.optimize import Bounds, LinearConstraint, milp
    remaining = float(seconds)-(perf_counter()-started)
    if remaining <= 0:
        return OptimizeResult(status=1, success=False, x=None, fun=None,
            message='Time limit reached before public MIP fallback', mip_node_count=0,
            backend='scipy-public-milp-fallback', native_start_error=native_error)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Unrecognized options detected')
        result = milp(cost, integrality=integer, bounds=Bounds(lower, upper),
            constraints=LinearConstraint(matrix, row_lower, row_upper),
            options={'time_limit': remaining, 'presolve': True, 'mip_rel_gap': 1.0,
                     'threads': 1, 'random_seed': 0})
    if result.x is not None:
        result.x = _feasible_primal(result.x, lower, upper, integer, matrix, row_lower, row_upper)
    result['success'] = result.status == 0 and result.x is not None
    result['backend'] = 'scipy-public-milp-fallback'
    result['native_start_error'] = native_error
    return result
