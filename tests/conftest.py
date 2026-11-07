"""Impostazioni comuni ai test, indipendenti dal file .env locale."""
import pytest

# Test del motore dei giri (algoritmo, ricerche a tempo, confronti di qualità): sono la
# parte lenta della suite. In locale, per modifiche che non toccano i calcoli:
#   python -m pytest tests -m "not motore"
# Senza -m la suite resta completa, come su GitHub.
MOTORE = frozenset((
    'test_balanced_work_minutes.py',
    'test_fleet_adaptive_search.py',
    'test_fleet_before_after.py',
    'test_fleet_benchmark_baselines.py',
    'test_fleet_highs_start.py',
    'test_fleet_milp_solver.py',
    'test_fleet_ortools.py',
    'test_fleet_pyvrp.py',
    'test_fleet_quality_reference.py',
    'test_fleet_route_evaluator.py',
    'test_fleet_route_exact.py',
    'test_fleet_route_exact_api.py',
    'test_fleet_route_pool.py',
    'test_fleet_search.py',
    'test_fleet_search_budget.py',
    'test_fleet_seed_search.py',
    'test_fleet_upgrade_quality.py',
    'test_fleet_working_clock.py',
    'test_optimizer.py',
    'test_optimizer_cost_first.py',
    'test_optimizer_improvements.py',
    'test_optimizer_priorities.py',
    'test_optimizer_scaling.py',
    'test_ortools_comparison.py',
    'test_ortools_full_comparison.py',
    'test_pyvrp_r104_benchmark.py',
    'test_real_optimizer_benchmark.py',
    'test_road_margin_benchmark.py',
    'test_routing_quality_audit.py',
    'test_routing_quality_fifty.py',
    'test_routing_quality_integration.py',
    'test_routing_quality_oracle.py',
))


def pytest_configure(config):
    config.addinivalue_line('markers', 'motore: test del motore dei giri (lenti), esclusi con -m "not motore"')


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.path.name in MOTORE:
            item.add_marker(pytest.mark.motore)


@pytest.fixture(autouse=True)
def _pod_storage_production_backend(monkeypatch):
    # Il .env di sviluppo può attivare l'archivio POD locale: nei test vale il default di
    # produzione (S3) e l'archivio locale si usa solo dove un test lo chiede esplicitamente.
    monkeypatch.setenv('OBJECT_STORAGE_BACKEND', 's3')


@pytest.fixture(autouse=True)
def _late_start_only_where_tested(request, monkeypatch):
    # I giri dei test hanno orari fissi (08:00): con l'orologio reale risulterebbero in ritardo.
    # Il controllo dei ritardi resta acceso dove è verificato.
    if request.node.path.name not in ('test_late_start.py',) and 'late_start' not in request.keywords:
        monkeypatch.setattr('app.services.late_start.ENABLED', False)


@pytest.fixture(autouse=True)
def _ortools_off_by_default(monkeypatch):
    # OR-Tools usa sempre tutto il tempo concesso e cambia i piani attesi dai test del
    # motore multi-mezzo: si accende solo nei test che lo verificano (test_fleet_ortools.py).
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '0')
    # Lo stesso per PyVRP: si accende solo in tests/test_fleet_pyvrp.py.
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '0')
