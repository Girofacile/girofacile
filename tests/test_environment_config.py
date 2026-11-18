"""Produzione riconosciuta allo stesso modo ovunque; valori sì/no con un refuso rifiutati."""
import importlib

import pytest

SAFE_PROD = {
    'APP_ENV': 'prod', 'APP_SECRET': 'x' * 40, 'SUPERADMIN_PASSWORD': 'Una-password-lunga-2026',
    'DATABASE_URL': 'postgresql://u:p@db/girofacile', 'APP_BASE_URL': 'https://girofacile.it',
    'COOKIE_SECURE': 'true',
}


@pytest.mark.parametrize('value', ['production', 'prod', ' PROD '])
def test_every_module_sees_production_the_same_way(monkeypatch, value):
    monkeypatch.setenv('APP_ENV', value)
    monkeypatch.delenv('COOKIE_SECURE', raising=False)
    from app.core import environment, production_check, config, http_security, links
    importlib.reload(config); importlib.reload(http_security)
    try:
        assert environment.is_production() and production_check.is_production()
        assert config.APP_ENV == http_security.APP_ENV == 'production'
        assert http_security.IS_PRODUCTION and http_security.cookie_options(60)['secure'] is True
        # In produzione gli indirizzi di prova per i link non valgono mai.
        assert links.local_override_allowed() is False
    finally:
        monkeypatch.setenv('APP_ENV', 'development')
        importlib.reload(config); importlib.reload(http_security)


@pytest.mark.parametrize('name,value', [('COOKIE_SECURE', 'tru'), ('COOKIE_SECURE', 'flase'),
                                         ('TRUST_PROXY_HEADERS', 'yes!'), ('OBJECT_STORAGE_ENABLED', 'attivo'),
                                         ('COOKIE_SAMESITE', 'lassa'), ('APP_ENV', 'prdo')])
def test_invalid_values_block_startup(name, value):
    from app.core.production_check import require_production_config
    env = dict(SAFE_PROD, **{name: value})
    with pytest.raises(RuntimeError) as error:
        require_production_config(env)
    assert name in str(error.value)
    # Anche fuori dalla produzione: un APP_ENV sbagliato farebbe saltare tutti i controlli.
    if name != 'APP_ENV':
        with pytest.raises(RuntimeError):
            require_production_config(dict(env, APP_ENV='development'))


def test_a_typo_never_turns_secure_cookies_off(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('COOKIE_SECURE', 'tru')
    from app.core import http_security
    importlib.reload(http_security)
    try:
        assert http_security.cookie_options(60)['secure'] is True
    finally:
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.delenv('COOKIE_SECURE')
        importlib.reload(http_security)


def test_valid_production_configuration_starts():
    from app.core.production_check import require_production_config
    require_production_config(dict(SAFE_PROD))
    require_production_config(dict(SAFE_PROD, APP_ENV='production', COOKIE_SECURE='on', TRUST_PROXY_HEADERS='1'))
