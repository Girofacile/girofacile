"""Vincoli di input: niente valori negativi né orari/date malformati trasformati in "nessun vincolo"."""
import pandas as pd
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas import CustomerIn, DeliveryIn, DriverIn, RoutePlanIn, VehicleIn
from app.services.customer_import import import_row_errors, unload_minutes


@pytest.mark.parametrize("field, value", [
    ("capacita_kg", -1), ("capacita_colli", -1), ("consumo_l_100km", -0.1),
    ("consumo_primario_100km", -2), ("consumo_kwh_100km", -5), ("capacita_kg", float("inf")),
])
def test_vehicle_rejects_negative_or_infinite_values(field, value):
    with pytest.raises(ValidationError):
        VehicleIn(nome="Furgone", **{field: value})


def test_vehicle_zero_capacity_is_a_valid_value():
    vehicle = VehicleIn(nome="Furgone", capacita_kg=0, capacita_colli=0, consumo_kwh_100km=0)
    assert vehicle.capacita_kg == 0 and vehicle.capacita_colli == 0


@pytest.mark.parametrize("changes", [
    {"tempo_scarico_min": -5},
    {"scarico_mattina_da": "25:00"},
    {"scarico_mattina_da": "otto"},
    {"scarico_mattina_da": "12:00", "scarico_mattina_a": "09:00"},
    {"lat": 120},
])
def test_customer_rejects_invalid_values(changes):
    with pytest.raises(ValidationError):
        CustomerIn(nome="Bar Roma", indirizzo="Via Roma 1", **changes)


def test_customer_normalizes_times_and_keeps_blank_as_absent():
    customer = CustomerIn(nome="Bar Roma", indirizzo="Via Roma 1", scarico_mattina_da="8:00",
                          scarico_mattina_a="12:30", scarico_pomeriggio_da="", tempo_scarico_min=0)
    assert (customer.scarico_mattina_da, customer.scarico_mattina_a) == ("08:00", "12:30")
    assert customer.scarico_pomeriggio_da is None and customer.tempo_scarico_min == 0


def test_delivery_rejects_negative_load():
    with pytest.raises(ValidationError):
        DeliveryIn(cliente_nome="X", indirizzo="Via 1", peso_kg=-3)
    with pytest.raises(ValidationError):
        DeliveryIn(cliente_nome="X", indirizzo="Via 1", colli=-1)


@pytest.mark.parametrize("changes", [
    {"data_giro": "13/10/2026"}, {"data_giro": ""}, {"data_giro": "2026-02-30"},
    {"orario_partenza": "8 e mezza"}, {"prezzo_carburante_litro": -1},
])
def test_route_rejects_invalid_date_time_and_price(changes):
    data = {"data_giro": "2026-10-13", "deposit_id": 1, "consegne": [], **changes}
    with pytest.raises(ValidationError):
        RoutePlanIn(**data)


def test_driver_expiry_dates_are_strict_but_optional():
    assert DriverIn(nome="Luca", scadenza_patente="").scadenza_patente is None
    assert DriverIn(nome="Luca", scadenza_patente="2027-05-01").scadenza_patente == "2027-05-01"
    with pytest.raises(ValidationError):
        DriverIn(nome="Luca", scadenza_patente="maggio 2027")


def test_import_row_errors_report_bad_times_and_unload():
    row = pd.Series({"nome": "A", "indirizzo": "B", "scarico_mattina_da": "9.00x",
                     "scarico_pomeriggio_da": "16:00", "scarico_pomeriggio_a": "14:00",
                     "tempo_scarico_min": "-3"})
    errors = import_row_errors(row)
    assert len(errors) == 3
    assert import_row_errors(pd.Series({"nome": "A", "indirizzo": "B", "scarico_mattina_da": "08:00",
                                        "scarico_mattina_a": "12:00", "tempo_scarico_min": "15.0"})) == []


def test_unload_minutes_accepts_spreadsheet_numbers():
    assert unload_minutes("15.0") == 15
    assert unload_minutes(None) == 10
    assert unload_minutes(float("nan"), 7) == 7
    with pytest.raises(ValueError):
        unload_minutes("abc")


def test_import_preflight_stops_before_any_change(monkeypatch):
    from app.services import customer_import

    class Query:
        def filter(self, *_a): return self
        def all(self): return []

    class Db:
        def query(self, *_a): return Query()

    monkeypatch.setattr(customer_import, "check_customer_limit", lambda *a, **k: None)
    df = pd.DataFrame([{"nome": "A", "indirizzo": "B", "scarico_mattina_da": "99:99"}])
    with pytest.raises(HTTPException) as exc:
        customer_import.preflight_customer_import(df, Db(), user=type("U", (), {"id": 1})())
    assert exc.value.status_code == 400 and "Riga 2" in exc.value.detail
