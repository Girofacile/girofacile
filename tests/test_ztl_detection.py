"""ZTL: matching informativo, dati OSM locali, nessuna API ad ogni richiesta."""
import json
from types import SimpleNamespace

from app.services import ztl
from app.services.order_planning import to_stop
from scripts.update_ztl_osm import assemble_rings, build_features


OUTER = [[10, 40], [11, 40], [11, 41], [10, 41], [10, 40]]
HOLE = [[10.4, 40.4], [10.6, 40.4], [10.6, 40.6], [10.4, 40.6], [10.4, 40.4]]


def fixture(monkeypatch, tmp_path):
    path = tmp_path / "ztl_osm.geojson"
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {"name": "ZTL test", "osm_id": 123},
            "geometry": {"type": "Polygon", "coordinates": [OUTER, HOLE]},
        }],
    }), encoding="utf-8")
    monkeypatch.setenv("GIROFACILE_ZTL_GEOJSON", str(path))
    ztl._read_zones.cache_clear()
    return path


def test_polygon_hole_border_and_non_detection(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    inside = ztl.detect_ztl(40.2, 10.2)
    assert inside == {"detected": True, "status": "rilevata", "zone": "ZTL test"}
    assert ztl.detect_ztl(40.5, 10.5)["detected"] is False  # foro
    assert ztl.detect_ztl(42, 12)["status"] == "non_rilevata"
    assert ztl.detect_ztl(40, 10.3)["detected"] is True  # bordo


def test_missing_dataset_and_missing_coordinates(monkeypatch, tmp_path):
    monkeypatch.setenv("GIROFACILE_ZTL_GEOJSON", str(tmp_path / "missing.geojson"))
    assert ztl.detect_ztl(40.2, 10.2)["status"] == "non_disponibile"
    assert ztl.detect_ztl(None, 10.2)["status"] == "non_disponibile"


def test_manual_marking_remains_possible(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    customer = SimpleNamespace(lat=40.9, lon=12, ztl=True)
    result = ztl.customer_ztl(customer)
    assert result["ztl"] is True
    assert result["ztl_source"] == "manuale"
    customer.ztl = False
    customer.lat, customer.lon = 40.2, 10.2
    assert ztl.customer_ztl(customer)["ztl_source"] == "osm"


def test_verified_order_flag_uses_same_lookup(monkeypatch, tmp_path):
    fixture(monkeypatch, tmp_path)
    address = "Via Test, Napoli"
    order = SimpleNamespace(
        user_id=3, id=5, version=1, number="A5",
        operational_data={"recipient_name": "Mario", "delivery_address": address, "ztl": False},
        address_verification={
            "input_address": address, "indirizzo": address, "lat": 40.2, "lon": 10.2,
            "stato_geocodifica": "verificato", "geocoding_token": "test-token",
        },
    )
    assert to_stop(order)["ztl"] is True


def test_osm_relation_way_segments_and_inner_ring():
    outer_a = OUTER[:3]
    outer_b = OUTER[2:]
    rings = assemble_rings([outer_b, outer_a])
    assert rings == [OUTER] or rings == [OUTER[2:] + OUTER[1:3]]
    element = {"type": "relation", "id": 4, "tags": {"boundary": "limited_traffic_zone"},
               "members": [
                   {"type": "way", "role": "outer", "geometry": [
                       {"lon": x, "lat": y} for x, y in OUTER]},
                   {"type": "way", "role": "inner", "geometry": [
                       {"lon": x, "lat": y} for x, y in HOLE]},
               ]}
    features = build_features([element])
    assert len(features) == 1
    assert len(features[0]["geometry"]["coordinates"][0]) == 2
