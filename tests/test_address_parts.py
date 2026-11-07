"""Indirizzo a campi separati: composizione, lettura, ordini, clienti e connettori."""
import pytest
from pydantic import ValidationError

from app.schemas.orders import OrderCreate
from app.services import address_parts
from app.services.order_connectors import shop_order
from app.services.order_files import suggestions
from test_orders import orders, create  # noqa: F401


def test_compose_and_split_round_trip():
    line = address_parts.compose("Via Roma", "10", "80026", "Casoria", "na")
    assert line == "Via Roma 10, 80026 Casoria NA"
    assert address_parts.split(line) == {"street": "Via Roma", "street_number": "10", "postal_code": "80026",
                                         "city": "Casoria", "province": "NA"}
    assert address_parts.split_street("Via G. Garibaldi 12/B") == ("Via G. Garibaldi", "12/B")
    assert address_parts.compose("Località Ponte", "", "80035", "Nola") == "Località Ponte, 80035 Nola"


def test_order_parts_compose_the_delivery_address_and_are_validated():
    order = OrderCreate(number="O-1", street="Via Roma", street_number="10", postal_code="118", city="Roma", province="RM")
    assert order.delivery_address == "Via Roma 10, 00118 Roma RM" and order.postal_code == "00118"
    with pytest.raises(ValidationError, match="via, CAP e comune"):
        OrderCreate(number="O-2", street="Via Roma", city="Casoria")
    with pytest.raises(ValidationError, match="5 cifre"):
        OrderCreate(number="O-3", street="Via Roma", postal_code="8002A", city="Casoria")
    # Senza campi separati l'indirizzo su una riga resta valido (API e integrazioni esistenti).
    assert OrderCreate(number="O-4", delivery_address="Via Roma 10, Casoria").delivery_address == "Via Roma 10, Casoria"


def test_order_detail_offers_parts_for_old_single_line_orders(orders):
    client, *_ = orders
    row = create(client, delivery_address="Via Nazionale 95, 80031 Brusciano NA")
    data = client.get(f"/api/orders/{row['id']}").json()["effective_data"]
    assert (data["street"], data["street_number"], data["postal_code"], data["city"]) == ("Via Nazionale", "95", "80031", "Brusciano")
    created = client.post("/api/orders", json={"number": "O-9", "recipient_name": "Bar", "street": "Via Roma",
                                               "street_number": "10", "postal_code": "80026", "city": "Casoria"})
    assert created.status_code == 201, created.text
    assert created.json()["delivery_address"] == "Via Roma 10, 80026 Casoria"


def test_shop_orders_keep_zip_and_city_without_country_or_second_line():
    body = {"id": 7, "name": "#1007", "note": "Citofono rotto",
            "shipping_address": {"name": "Bar Roma", "address1": "Via Roma 10", "address2": "Scala B",
                                 "zip": "80026", "city": "Casoria", "province_code": "NA", "country": "IT"}}
    order = shop_order(body, "shopify")
    assert order["delivery_address"] == "Via Roma 10, 80026 Casoria NA"
    assert order["notes"] == "Citofono rotto · Scala B"


def test_file_columns_for_separate_address_are_recognised():
    found = suggestions(["Numero ordine", "Cliente", "Via", "Civico", "CAP", "Comune", "Provincia"])
    assert (found["street"], found["street_number"], found["postal_code"], found["city"], found["province"]) == (
        "Via", "Civico", "CAP", "Comune", "Provincia")


def test_customer_cap_reaches_the_geocoding_query(monkeypatch):
    from types import SimpleNamespace
    from app.services import geocoding
    seen = {}
    monkeypatch.setattr(geocoding, "geocode_address", lambda indirizzo, comune="", provincia="", **kw: seen.update(q=(indirizzo, comune, provincia)) or {})
    geocoding.geocode_customer(SimpleNamespace(indirizzo="Via Roma 10", cap="80026", comune="Casoria", provincia="NA", user_id=1))
    assert seen["q"] == ("Via Roma 10", "80026 Casoria", "NA")


def test_forms_use_separate_address_fields():
    from pathlib import Path
    orders_js = Path("static/dashboard/js/orders.js").read_text(encoding="utf-8")
    assert "street:'Via',street_number:'Civico',postal_code:'CAP',city:'Comune'" in orders_js
    assert "Verifichiamo esattamente" in orders_js and "recipient_name:'Destinatario',delivery_address" not in orders_js
    customers_js = Path("static/dashboard/js/customers.js").read_text(encoding="utf-8")
    assert "field('cxStreet','Via'" in customers_js and "field('cxCap','CAP'" in customers_js
    index = Path("static/dashboard/index.html").read_text(encoding="utf-8")
    assert 'id="cVia"' in index and 'id="cCap"' in index and 'placeholder="Via, numero civico, città"' not in index
