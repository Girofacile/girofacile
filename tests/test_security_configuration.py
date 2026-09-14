from pathlib import Path


def test_dockerfile_has_no_sqlite_or_default_secrets():
    content = Path("Dockerfile").read_text(encoding="utf-8")
    assert "sqlite:///" not in content
    assert "admin123" not in content
    assert "change-me" not in content


def test_compose_reads_secrets_from_environment():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file:" in content
    assert "girofacile_local" not in content
    assert "demo1234" not in content


def test_production_hides_api_documentation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    # Verifica statica per non importare il database durante questo smoke test.
    content = Path("app/main.py").read_text(encoding="utf-8")
    assert 'docs_url=None if IS_PRODUCTION' in content
    assert 'openapi_url=None if IS_PRODUCTION' in content


def test_all_authentication_cookies_use_shared_security_options():
    targets = [
        Path("app/routers/auth.py"),
        Path("app/routers/driver.py"),
        Path("app/routers/agent.py"),
        Path("app/routers/transfer_portal.py"),
    ]
    for target in targets:
        content = target.read_text(encoding="utf-8")
        assert "cookie_options" in content
        assert 'set_cookie(' not in content or 'httponly=True, samesite="lax"' not in content


def test_login_rate_limiter_covers_sensitive_endpoints():
    content = Path("app/core/http_security.py").read_text(encoding="utf-8")
    for path in ("/api/login", "/api/admin/login", "/api/driver/login", "/api/agent/login"):
        assert path in content
    assert "status_code=429" in content
