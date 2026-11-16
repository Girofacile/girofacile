"""Account di sviluppo admin/admin123: mai creato né accettato in produzione."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import legacy_schema
from app.core.production_check import default_account_problems
from app.core.security import hash_password
from app.database import Base
from app.models import User


def _engine():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    return engine


def test_default_account_is_not_created_in_production(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(legacy_schema, 'engine', engine)
    monkeypatch.setenv('APP_ENV', 'production')
    legacy_schema.ensure_default_user()
    with Session(engine) as db:
        assert db.query(User).count() == 0


def test_default_account_is_still_created_for_development(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(legacy_schema, 'engine', engine)
    monkeypatch.setenv('APP_ENV', 'development')
    legacy_schema.ensure_default_user()
    with Session(engine) as db:
        assert db.query(User).count() == 1


def test_production_rejects_an_existing_account_with_a_default_password():
    engine = _engine()
    with Session(engine) as db:
        db.add(User(username='admin', password_hash=hash_password('admin123'), plan='pro', plan_status='active'))
        db.commit()
        assert default_account_problems(db, {'APP_USER': 'admin'})
        db.query(User).first().password_hash = hash_password('Una-Password-Lunga-2026!')
        db.commit()
        assert default_account_problems(db, {'APP_USER': 'admin'}) == []
