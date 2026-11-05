"""Impostazioni comuni ai test, indipendenti dal file .env locale."""
import pytest


@pytest.fixture(autouse=True)
def _pod_storage_production_backend(monkeypatch):
    # Il .env di sviluppo può attivare l'archivio POD locale: nei test vale il default di
    # produzione (S3) e l'archivio locale si usa solo dove un test lo chiede esplicitamente.
    monkeypatch.setenv('OBJECT_STORAGE_BACKEND', 's3')


@pytest.fixture(autouse=True)
def _ortools_off_by_default(monkeypatch):
    # OR-Tools usa sempre tutto il tempo concesso e cambia i piani attesi dai test del
    # motore multi-mezzo: si accende solo nei test che lo verificano (test_fleet_ortools.py).
    monkeypatch.setenv('FLEET_ORTOOLS_SECONDS', '0')
    # Lo stesso per PyVRP: si accende solo in tests/test_fleet_pyvrp.py.
    monkeypatch.setenv('FLEET_PYVRP_SECONDS', '0')
