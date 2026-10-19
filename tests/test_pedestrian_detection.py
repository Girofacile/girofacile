"""Two non-blocking notices for verified customers and order stops."""
import json
from copy import deepcopy
from types import SimpleNamespace

from app.services import ztl
from scripts.update_ztl_osm import build_pedestrian_features, PEDESTRIAN_QUERY
from app.optimizer import _evaluate_fixed_sequence


OUTER = [[14.0, 40.0], [15.0, 40.0], [15.0, 41.0], [14.0, 41.0], [14.0, 40.0]]


def archive(path, name):
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {"name": name},
            "geometry": {"type": "Polygon", "coordinates": [OUTER]},
        }],
    }), encoding="utf-8")


def test_pedestrian_and_ztl_are_independent_and_manual_ztl_is_preserved(tmp_path, monkeypatch):
    ztl_data = tmp_path / "ztl_osm.geojson"
    pedestrian_data = tmp_path / "pedestrian_osm.geojson"
    archive(pedestrian_data, "Piazza pedonale")
    monkeypatch.setenv("GIROFACILE_ZTL_GEOJSON", str(ztl_data))
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_GEOJSON", str(pedestrian_data))
    monkeypatch.setenv("GIROFACILE_ZTL_OFFICIAL_GEOJSON", str(tmp_path / "no_official_ztl.json"))
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON", str(tmp_path / "no_official_ped.json"))
    ztl._read_zones.cache_clear()

    customer = SimpleNamespace(lat=40.5, lon=14.5, ztl=False)
    initial = ztl.customer_ztl(customer)
    assert initial["ztl"] is False
    assert initial["pedestrian_area"] is True
    assert initial["pedestrian_zone"] == "Piazza pedonale"
    assert initial["pedestrian_source"] == "osm"
    customer.ztl = True
    assert ztl.customer_ztl(customer)["ztl_source"] == "manuale"
    archive(ztl_data, "ZTL test")
    both = ztl.customer_ztl(customer)
    assert both["ztl"] is True and both["pedestrian_area"] is True
    assert both["ztl_zone"] == "ZTL test"
    assert ztl.detect_pedestrian(42, 14.5)["status"] == "non_rilevata"


def test_missing_archive_never_creates_a_positive_pedestrian_notice(tmp_path, monkeypatch):
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_GEOJSON", str(tmp_path / "missing.geojson"))
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON", str(tmp_path / "missing_official.geojson"))
    assert ztl.detect_pedestrian(40.5, 14.5)["status"] == "non_disponibile"
    assert ztl.detect_pedestrian(None, 14.5)["detected"] is False


def test_municipal_polygons_override_osm_and_osm_still_fills_other_cities(tmp_path, monkeypatch):
    a, b = tmp_path / "ztl_official.geojson", tmp_path / "ztl_osm.geojson"
    archive(a, "ZTL comunale")
    archive(b, "ZTL OpenStreetMap")
    monkeypatch.setenv("GIROFACILE_ZTL_OFFICIAL_GEOJSON", str(a))
    monkeypatch.setenv("GIROFACILE_ZTL_GEOJSON", str(b))
    ztl._read_zones.cache_clear()
    customer = SimpleNamespace(lat=40.5, lon=14.5, ztl=False)
    assert ztl.detect_ztl(40.5, 14.5)["zone"] == "ZTL comunale"
    assert ztl.customer_ztl(customer)["ztl_source"] == "comunale"
    a.unlink()
    assert ztl.detect_ztl(40.5, 14.5)["zone"] == "ZTL OpenStreetMap"


def test_pedestrian_updater_ignores_linework_and_regular_sidewalks():
    def pts(coords):
        return [{"lon": x, "lat": y} for x, y in coords]
    inputs = [
        {"type": "way", "id": 1,
         "tags": {"highway": "pedestrian", "area": "yes", "name": "Piazza"},
         "geometry": pts(OUTER)},
        {"type": "way", "id": 2, "tags": {"area:highway": "pedestrian"},
         "geometry": pts(OUTER)},
        {"type": "way", "id": 3, "tags": {"highway": "pedestrian"},
         "geometry": pts(OUTER[:-1])},
        {"type": "way", "id": 4, "tags": {"highway": "footway", "area": "yes"},
         "geometry": pts(OUTER)},
    ]
    features = build_pedestrian_features(inputs)
    assert {feature["properties"]["osm_id"] for feature in features} == {1, 2}
    assert '["area:highway"="pedestrian"]' in PEDESTRIAN_QUERY


def test_geographic_notices_do_not_affect_route_score_or_optimality():
    stop = dict(_matrix_index=1, cliente_nome="Test", indirizzo="Piazza",
                tempo_scarico_min=10, ztl=False, pedestrian_area=False)
    matrix = {(0, 1): {"km": 1.5, "min": 6}, (1, 0): {"km": 1.5, "min": 6}}
    points = [{"lat": 40, "lon": 14}, {"lat": 40.5, "lon": 14.5}]
    normal = _evaluate_fixed_sequence([stop], matrix, points)
    flagged = _evaluate_fixed_sequence([{**stop, "ztl": True, "pedestrian_area": True}], matrix, points)
    assert normal["_objective"] == flagged["_objective"]
    assert normal["score"] == flagged["score"]
    assert "cliente in zona ZTL" in flagged["ordered"][0]["warning"]
    assert "cliente in area pedonale" in flagged["ordered"][0]["warning"]


def test_saved_route_carries_pedestrian_warning(routing_env, monkeypatch, tmp_path):
    from test_routing_architecture import payload
    from app.models import Delivery
    client, db, owner, _, customer, *_ = routing_env
    pedestrian_data = tmp_path / "pedestrian.geojson"
    archive(pedestrian_data, "Piazza pedonale")
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_GEOJSON", str(pedestrian_data))
    monkeypatch.setenv("GIROFACILE_PEDESTRIAN_OFFICIAL_GEOJSON", str(tmp_path / "no_official.geojson"))
    ztl._read_zones.cache_clear()
    customer.lat, customer.lon = 40.5, 14.5
    db.commit()
    response = client.post("/api/routes/recalculate-manual", json=payload(routing_env))
    assert response.status_code == 200, response.text
    stop = response.json()["consegne"][0]
    assert stop["pedestrian_area"] is True
    assert "cliente in area pedonale" in stop["warning"]
    record = db.query(Delivery).first()
    assert record.pedestrian_area is True
    detail = client.get(f"/api/routes/{response.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["consegne"][0]["pedestrian_area"] is True


from test_routing_architecture import routing_env
from test_agents_feature import env
