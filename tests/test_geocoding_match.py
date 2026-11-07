"""La verifica indirizzi non accetta la stessa via in un altro comune."""
from app.services import geocoding


def google_item(formatted, comune, cap, partial=False, lat=40.9, lon=14.4):
    # Via e civico come li dà Google: «V. Nazionale, 95, 08028 Orosei NU, Italia».
    parts = formatted.split(", ")
    street = [{"long_name": parts[0], "short_name": parts[0], "types": ["route"]}] if not parts[0][:1].isdigit() else []
    number = [{"long_name": parts[1], "types": ["street_number"]}] if len(parts) > 2 and parts[1].isdigit() else []
    return {"formatted_address": formatted, "partial_match": partial, "place_id": formatted,
            "geometry": {"location": {"lat": lat, "lng": lon}, "location_type": "ROOFTOP"},
            "address_components": street + number + [{"long_name": comune, "types": ["locality", "political"]},
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


def test_partial_result_without_town_is_not_verified(monkeypatch):
    # Risposta reale di Google per «Via Roma 10, Casoria»: Montiglio (altro comune) e una
    # «Via Roma, Italia» senza comune, centro geometrico nelle Marche.
    other = google_item("Via Roma, 10, 14026 Montiglio AT, Italia", "Montiglio", "14026", partial=True, lat=45.07, lon=8.10)
    anywhere = {"formatted_address": "Via Roma, Italia", "partial_match": True, "place_id": "via-roma",
                "geometry": {"location": {"lat": 43.69, "lng": 12.80}, "location_type": "GEOMETRIC_CENTER"},
                "address_components": [{"long_name": "Via Roma", "types": ["route"]}]}
    fake_google(monkeypatch, other, anywhere)
    result = geocoding.geocode_address("Via Roma 10, Casoria")
    assert result["status"] == "da_verificare" and result["reason"] == "altro_comune"
    # Anche come corrispondenza completa, senza comune non si verifica da solo.
    anywhere["partial_match"] = False
    fake_google(monkeypatch, anywhere)
    assert geocoding.geocode_address("Via Roma 10, Casoria")["status"] == "da_verificare"


def test_same_town_but_other_street_or_number_is_not_verified(monkeypatch):
    fake_google(monkeypatch, google_item("Via Napoli, 10, 80026 Casoria NA, Italia", "Casoria", "80026"))
    result = geocoding.geocode_address("Via Roma 10, 80026 Casoria NA")
    assert result["status"] == "da_verificare" and result["reason"] == "via_diversa"
    fake_google(monkeypatch, google_item("Via Roma, 12, 80026 Casoria NA, Italia", "Casoria", "80026"))
    assert geocoding.geocode_address("Via Roma 10, 80026 Casoria NA")["reason"] == "via_diversa"


def test_street_center_or_missing_number_needs_a_person(monkeypatch):
    item = google_item("Via Roma, 80026 Casoria NA, Italia", "Casoria", "80026")
    item["geometry"]["location_type"] = "GEOMETRIC_CENTER"
    fake_google(monkeypatch, item)
    assert geocoding.geocode_address("Via Roma 10, 80026 Casoria NA")["reason"] == "via_diversa"
    assert geocoding.geocode_address("Via Roma, 80026 Casoria NA")["reason"] == "approssimativo"
    # Senza comune né CAP l'indirizzo è ambiguo: mai verificato da solo.
    fake_google(monkeypatch, google_item("Via Roma, 10, 80026 Casoria NA, Italia", "Casoria", "80026"))
    assert geocoding.geocode_address("Via Roma 10")["status"] == "da_verificare"


def test_abbreviations_initials_and_letters_still_match(monkeypatch):
    fake_google(monkeypatch, google_item("Via Giuseppe Garibaldi, 12, 80038 Pomigliano d'Arco NA, Italia", "Pomigliano d'Arco", "80038"))
    assert geocoding.geocode_address("V. G. Garibaldi 12/B, Pomigliano d'Arco")["status"] == "verificato"
    fake_google(monkeypatch, google_item("Corso Umberto I, 76, 80138 Napoli NA, Italia", "Napoli", "80138"))
    assert geocoding.geocode_address("C.so Umberto I 76, Napoli")["status"] == "verificato"


def test_only_italian_results_are_requested(monkeypatch):
    seen = {}
    monkeypatch.setattr(geocoding, "google_geocoding_enabled", lambda db=None: True)
    monkeypatch.setattr(geocoding, "google_maps_api_key", lambda db=None: "test")

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"status": "ZERO_RESULTS", "results": []}
    monkeypatch.setattr(geocoding.requests, "get", lambda url, params, **kw: seen.update(params) or Response())
    assert geocoding.geocode_address("Via Roma 10, Casoria")["status"] == "non_trovato"
    assert seen["components"] == "country:IT"


def test_number_followed_by_town_without_comma():
    parsed = geocoding.parse_address("piazza giovanni leone 22 pomigliano, pomigliano d'arco")
    assert parsed["street"] == "piazza giovanni leone" and parsed["number"] == "22"
    assert parsed["town"] == "pomigliano d'arco"
    assert geocoding.parse_address("Via 4 Novembre 12, Napoli")["number"] == "12"
