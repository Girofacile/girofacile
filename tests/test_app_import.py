"""Load every application router without touching a configured database."""
import os
import subprocess
import sys


def test_complete_application_imports():
    env = dict(os.environ, DATABASE_URL="sqlite+pysqlite:///:memory:",
               ALLOW_SQLITE_LEGACY="true", APP_ENV="development")
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app; assert app.routes"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
