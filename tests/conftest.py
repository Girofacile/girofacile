"""Impostazioni comuni ai test, indipendenti dal file .env locale."""
import pytest


@pytest.fixture(autouse=True)
def _pod_storage_production_backend(monkeypatch):
    # Il .env di sviluppo può attivare l'archivio POD locale: nei test vale il default di
    # produzione (S3) e l'archivio locale si usa solo dove un test lo chiede esplicitamente.
    monkeypatch.setenv('OBJECT_STORAGE_BACKEND', 's3')
