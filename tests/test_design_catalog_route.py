"""Il catalogo dei componenti risponde in sviluppo e mai in produzione."""
import os
import subprocess
import sys

PROBE = (
    "from fastapi.testclient import TestClient; from app.main import app; "
    "response = TestClient(app).get('/catalogo'); "
    "print(response.status_code, 'data-gf-layout=\"base\"' in response.text)"
)


def _catalog_status(app_env):
    env = dict(os.environ, DATABASE_URL="sqlite+pysqlite:///:memory:",
               ALLOW_SQLITE_LEGACY="true", APP_ENV=app_env)
    result = subprocess.run([sys.executable, "-c", PROBE], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()[-1]


def test_catalog_is_served_in_development():
    assert _catalog_status("development") == "200 True"


def test_catalog_is_hidden_in_production():
    assert _catalog_status("production") == "404 False"
