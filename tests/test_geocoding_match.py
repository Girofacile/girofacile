"""La verifica indirizzi non accetta la stessa via in un altro comune."""
from app.services import geocoding


def google_item(formatted, comune, cap, partial=False, lat=40.9, lon=14.4):
    return {"formatted_address": formatted, "partial_match": partial, "place_id": formatted,
            "geometry": {"location": {"lat": lat, "lng": lon}, "location_type": "ROOFTOP"},
            "address_components": [{"long_name": comune, "types": ["locality", "political"]},
                                   {"long_name": cap, "types": ["postal_code"]}]}


def fake_google(monkeypatch, *items):
    monkeypatch.setattr(geocoding, "google_geocoding_enabled", lambda db=None: True)
    monkeypatch.setattr(geocoding, "google_maps_api_key", lambda db=None: "test")

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status": "OK", "results": list(items)}
    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **kw: Response())


def test_same_street_in_another_town_is_not_verified(monkeypatch):
    fake_google(monkeypatch, google_item("V. Nazionale, 95, 08028 Orosei NU, Italia", "Orosei", "08028",
                                         partial=True, lat=40.38, lon=9.69))
    result = geocoding.geocode_address("Via Nazionale, 95, 80031 Brusciano NA")
    assert result["status"] == "da_verificare" and result["reason"] == "altro_comune"
    assert "Orosei" in result["formatted"]  # resta proposto come posizione da confermare sulla mappa


def test_matching_result_is_preferred_to_the_first_one(monkeypatch):
    fake_google(monkeypatch,
                google_item("V. Nazionale, 95, 08028 Orosei NU, Italia", "Orosei", "08028", lat=40.38, lon=9.69),
                google_item("Via Nazionale, 95, 80031 Brusciano NA, Italia", "Brusciano", "80031"))
    result = geocoding.geocode_address("Via Nazionale, 95, 80031 Brusciano NA")
    assert result["status"] == "verificato" and "Brusciano" in result["formatted"]


def test_big_city_with_different_postal_code_is_still_verified(monkeypatch):
    fake_google(monkeypatch, google_item("Corso Umberto I, 76, 80138 Napoli NA, Italia", "Napoli", "80138"))
    assert geocoding.geocode_address("Corso Umberto I, 76, 80142 Napoli NA")["status"] == "verificato"


def test_postal_code_alone_is_enough(monkeypatch):
    fake_google(monkeypatch, google_item("Via Roma, 8, 80030 Castello di Cisterna NA, Italia", "Castello di Cisterna", "80030"))
    assert geocoding.geocode_address("Via Roma 8, 80030 Cisterna")["status"] == "verificato"


def test_without_postal_code_a_partial_match_elsewhere_is_rejected(monkeypatch):
    fake_google(monkeypatch, google_item("Via Roma, 1, 09170 Oristano OR, Italia", "Oristano", "09170", partial=True))
    assert geocoding.geocode_address("Via Roma 1, Sant'Anastasia")["status"] == "da_verificare"
    fake_google(monkeypatch, google_item("Via Roma, 1, 80048 Sant'Anastasia NA, Italia", "Sant'Anastasia", "80048", partial=True))
    assert geocoding.geocode_address("Via Roma 1, Sant Anastasia")["status"] == "verificato"


def test_approximate_position_in_the_right_town_explains_why(monkeypatch):
    item = google_item("80031 Brusciano NA, Italia", "Brusciano", "80031")
    item["geometry"]["location_type"] = "APPROXIMATE"
    fake_google(monkeypatch, item)
    result = geocoding.geocode_address("Via Inesistente 3, 80031 Brusciano NA")
    assert result["status"] == "da_verificare" and result["reason"] == "approssimativo"
    fake_google(monkeypatch, google_item("Via Roma, 8, 80030 Castello di Cisterna NA, Italia", "Castello di Cisterna", "80030"))
    assert geocoding.geocode_address("Via Roma 8, 80030 Cisterna")["reason"] is None


def test_strict_failure_carries_reason_and_message(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from app.services import occasional_stops
    for result, reason in [({"status": "non_trovato"}, "non_trovato"),
                           ({"status": "da_verificare", "reason": "altro_comune", "lat": 40.38, "lon": 9.69,
                             "formatted": "Via Nazionale, 95, 08028 Orosei NU"}, "altro_comune"),
                           ({"status": "da_verificare", "reason": "approssimativo", "lat": 40.92, "lon": 14.42,
                             "formatted": "80031 Brusciano NA"}, "approssimativo")]:
        monkeypatch.setattr(occasional_stops, "geocode_address", lambda *a, _r=result, **kw: _r)
        with pytest.raises(HTTPException) as error:
            occasional_stops.verify_stop_address(None, 1, "Via Nazionale 95, 80031 Brusciano NA", strict=True)
        detail = error.value.detail
        assert detail["reason"] == reason and detail["message"] == occasional_stops.ADDRESS_REASONS[reason]
        assert (detail["candidate"] is None) == (reason == "non_trovato")
