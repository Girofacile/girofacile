"""Registrazione rapida (28/11/2026): sede operativa in una riga con i suggerimenti Google Places."""
import pytest
from fastapi import HTTPException


class Fake:
    def __init__(self, data, status=200):
        self.data, self.status_code, self.ok = data, status, status < 400

    def json(self):
        return self.data


def test_suggestions_and_details_from_google_places(monkeypatch):
    from app.services import signup_address
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', 'chiave-di-prova')
    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url, kw))
        if url.endswith('places:autocomplete'):
            return Fake({'suggestions': [{'placePrediction': {'placeId': 'ChIJ-prova-123', 'text': {'text': 'Via Toledo, 15, Napoli, NA, Italia'}}}]})
        return Fake({'formattedAddress': 'Via Toledo, 15, 80134 Napoli NA, Italia', 'location': {'latitude': 40.84, 'longitude': 14.25},
                     'addressComponents': [
                         {'longText': '15', 'shortText': '15', 'types': ['street_number']},
                         {'longText': 'Via Toledo', 'shortText': 'Via Toledo', 'types': ['route']},
                         {'longText': 'Napoli', 'shortText': 'Napoli', 'types': ['locality', 'political']},
                         {'longText': 'Città Metropolitana di Napoli', 'shortText': 'NA', 'types': ['administrative_area_level_2']},
                         {'longText': 'Italia', 'shortText': 'IT', 'types': ['country']},
                         {'longText': '80134', 'shortText': '80134', 'types': ['postal_code']}]})
    monkeypatch.setattr(signup_address.requests, 'request', fake_request)
    assert signup_address.suggestions(None, 'via tol') == [{'place_id': 'ChIJ-prova-123', 'label': 'Via Toledo, 15, Napoli, NA, Italia'}]
    assert signup_address.suggestions(None, 'via', 'sessione12345') == []  # troppo corto: nessuna chiamata
    assert len(calls) == 1 and calls[0][2]['json']['includedRegionCodes'] == ['it']
    place = signup_address.details(None, 'ChIJ-prova-123', 'sessione12345')
    assert place['street'] == 'Via Toledo, 15' and place['city'] == 'Napoli' and place['zip'] == '80134'
    assert place['province'] == 'NA' and place['country'] == 'Italia' and place['has_street_number']
    assert calls[-1][2]['params']['sessionToken'] == 'sessione12345'
    with pytest.raises(HTTPException) as error:
        signup_address.details(None, '../altro', '')
    assert error.value.status_code == 400


def test_google_errors_become_a_clear_unavailable_message(monkeypatch):
    from app.services import signup_address
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', 'chiave-di-prova')
    monkeypatch.setattr(signup_address.requests, 'request', lambda *a, **k: Fake({'error': {}}, 403))
    with pytest.raises(HTTPException) as error:
        signup_address.suggestions(None, 'via roma 1 napoli')
    assert error.value.status_code == 503


def test_public_search_is_limited_per_visitor(monkeypatch):
    from app.services import signup_address
    monkeypatch.setattr(signup_address, '_requests', type(signup_address._requests)())
    for _ in range(signup_address.SEARCHES_PER_WINDOW):
        signup_address.limit_visitor('203.0.113.7')
    with pytest.raises(HTTPException) as error:
        signup_address.limit_visitor('203.0.113.7')
    assert error.value.status_code == 429
    signup_address.limit_visitor('203.0.113.8')  # un altro visitatore non è bloccato


def test_signup_needs_only_the_operating_address(env, monkeypatch):
    from fastapi import Response
    from app.models import User
    from app.routers import auth
    from app.schemas import SignupIn
    _, db, *_ = env
    monkeypatch.setattr(auth, 'ERROR_NOTIFICATIONS_EMAIL', '')
    data = dict(username='rapida-1', email='rapida-1@example.com', company_name='Trasporti Rapidi', password='Orbit!River47Cedar#')
    with pytest.raises(HTTPException) as error:
        auth.signup(SignupIn(**data, company_address=''), Response(), db)
    assert error.value.status_code == 400
    auth.signup(SignupIn(**data, company_address='Via Toledo, 15', company_city='Napoli', company_zip='80134'), Response(), db)
    created = db.query(User).filter_by(username='rapida-1').one()
    assert (created.company_address, created.company_city, created.company_zip) == ('Via Toledo, 15', 'Napoli', '80134')
    assert created.company_vat is None and created.company_pec is None


from test_agents_feature import env  # noqa: E402,F401  (fixture)
