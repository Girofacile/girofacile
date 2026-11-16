"""Indirizzo del database da Docker Compose: password con caratteri speciali."""
from sqlalchemy.engine import make_url

from app.core.database_url import compose_database_url


def test_password_with_special_characters_survives():
    env = {'POSTGRES_HOST': 'postgres', 'POSTGRES_USER': 'girofacile', 'POSTGRES_PASSWORD': 'audit@pass:w/rd#1', 'POSTGRES_DB': 'gf'}
    url = make_url(compose_database_url(env))
    assert url.host == 'postgres' and url.password == 'audit@pass:w/rd#1' and url.database == 'gf'


def test_explicit_database_url_wins_and_empty_means_absent():
    assert compose_database_url({'DATABASE_URL': 'postgresql+psycopg2://a:b@h/d', 'POSTGRES_HOST': 'postgres'}) == 'postgresql+psycopg2://a:b@h/d'
    assert compose_database_url({'DATABASE_URL': '', 'POSTGRES_HOST': ''}) == ''
