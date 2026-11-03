"""OR-Tools migliora il piano multi-mezzo senza perdere consegne; senza OR-Tools nulla cambia."""
import pytest

from fleet_upgrade_cases import _base
from routing_quality_fleet import run_fleet
from routing_quality_oracle import plan_metrics
from app.services import fleet_ortools

pytest.importorskip('ortools')


@pytest.fixture(scope='module')
def case():
    return _base(2, 'windows_shifts', 2027111211, 'development')


def test_time_budget_scales_with_stops(monkeypatch):
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '10')
    assert [fleet_ortools.seconds_budget(n) for n in (4, 50, 100)] == [1.0, 7.5, 10.0]
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '0')
    assert fleet_ortools.seconds_budget(50) == 0.0


def test_ortools_shortens_plan_and_keeps_deliveries(case, monkeypatch):
    baseline = run_fleet(case, 'efficient', budget=4000)
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '3')
    improved = run_fleet(case, 'efficient', budget=4000)
    report = improved['diagnostics']['ortools']
    assert baseline['diagnostics']['ortools'] == {'status': 'disabled'}
    assert report['seeded'] and report['accepted'], report
    before, after = plan_metrics(case, baseline['routes']), plan_metrics(case, improved['routes'])
    assert after['feasible'] and after['served'] == before['served'] == 50
    assert after['km'] < before['km']
    assert improved['external_calls'] == 0 and not improved['mutation_detected']


def test_solver_error_keeps_current_plan(case, monkeypatch):
    baseline = run_fleet(case, 'efficient', budget=4000)
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '3')
    def broken(*args, **kwargs):
        raise RuntimeError('solutore non disponibile')
    monkeypatch.setattr(fleet_ortools, 'improve', broken)
    result = run_fleet(case, 'efficient', budget=4000)
    assert result['diagnostics']['ortools'] == {'status': 'error', 'error': 'RuntimeError'}
    assert result['routes'] == baseline['routes']


def test_missing_library_keeps_current_plan(case, monkeypatch):
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '3')
    monkeypatch.setattr(fleet_ortools, 'available', lambda: False)
    assert run_fleet(case, 'efficient', budget=4000)['diagnostics']['ortools'] == {'status': 'unavailable'}


def test_balanced_strategy_never_gets_worse(case, monkeypatch):
    from routing_quality_oracle import objective
    baseline = run_fleet(case, 'balanced', budget=4000)
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '3')
    result = run_fleet(case, 'balanced', budget=4000)
    assert result['diagnostics']['ortools']['seeded']
    before, after = plan_metrics(case, baseline['routes']), plan_metrics(case, result['routes'])
    assert after['feasible'] and after['served'] == before['served']
    assert objective(after, 'balanced') <= objective(before, 'balanced')


def single_route():
    from optimizer_benchmark import deliveries, metric_matrix
    from test_optimizer import GRID
    return deliveries(14), metric_matrix(GRID[:15])


def test_single_route_long_is_improved_or_kept(monkeypatch):
    from app import optimizer as opt
    rows, matrix = single_route()
    baseline = opt._best_internal_sequence(rows, matrix, [], None, True, '08:00')
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '2')
    result = opt._ortools_single(rows, matrix, [], None, True, '08:00', baseline)
    assert sorted(d['customer_id'] for d in result['ordered']) == list(range(1, 15))
    assert opt.solution_key(result) <= opt.solution_key(baseline)


def test_single_route_keeps_order_on_solver_error_or_short_route(monkeypatch):
    from app import optimizer as opt
    rows, matrix = single_route()
    baseline = opt._best_internal_sequence(rows, matrix, [], None, True, '08:00')
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '2')
    def broken(*args, **kwargs):
        raise RuntimeError('solutore non disponibile')
    monkeypatch.setattr(fleet_ortools, 'improve', broken)
    assert opt._ortools_single(rows, matrix, [], None, True, '08:00', baseline) is baseline
    short = opt._best_internal_sequence(rows[:8], matrix, [], None, True, '08:00')
    assert opt._ortools_single(rows[:8], matrix, [], None, True, '08:00', short) is short
