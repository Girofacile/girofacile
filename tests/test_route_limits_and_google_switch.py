"""Tetto alle consegne di un giro singolo e interruttore Google spento rispettato anche con la chiave."""
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import SaaSPlatformSetting
from app.schemas import MAX_ROUTE_STOPS, RoutePlanIn
from app.services import platform_settings as ps


def _plan(count):
    stop = {'cliente_nome': 'Cliente', 'indirizzo': 'Via Roma 1'}
    return {'data_giro': '2026-11-20', 'deposit_id': 1, 'consegne': [stop] * count}


def test_single_route_accepts_up_to_the_limit_and_rejects_more():
    assert len(RoutePlanIn(**_plan(MAX_ROUTE_STOPS)).consegne) == MAX_ROUTE_STOPS
    with pytest.raises(ValidationError, match='al massimo 150 consegne'):
        RoutePlanIn(**_plan(10_001))


@pytest.mark.parametrize('key,check', [('google_geocoding_enabled', ps.google_geocoding_enabled),
                                       ('google_routes_enabled', ps.google_routes_enabled)])
def test_explicit_off_wins_over_a_saved_key(monkeypatch, key, check):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(SaaSPlatformSetting(key='google_maps_api_key', value='chiave-finta'))
        db.commit()
        assert check(db) is True  # chiave presente, interruttore mai toccato: acceso
        db.add(SaaSPlatformSetting(key=key, value='false'))
        db.commit()
        assert check(db) is False  # spento dal pannello: resta spento
