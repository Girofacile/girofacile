"""Invalid report filters must not crash or silently broaden the report."""
import pytest

from test_agents_feature import env


@pytest.mark.parametrize("endpoint", ["summary", "export"])
@pytest.mark.parametrize("params", [
    {"date_from": "2026-02-30"},
    {"date_to": "invalid"},
    {"date_from": "20261016"},
    {"date_to": "2026-10-16extra"},
    {"date_from": "2026-10-16", "date_to": "2026-10-15"},
    {"customer_id": "invalid"},
    {"driver_id": "-1"},
    {"vehicle_id": "0"},
    {"customer_id": "999999999999999999999999999"},
    {"agent_id": "invalid"},
])
def test_invalid_report_filters_are_rejected(env, endpoint, params):
    client, *_ = env
    response = client.get(f"/api/reports/{endpoint}", params=params)
    assert response.status_code == 422
    assert response.json()["detail"]


@pytest.mark.parametrize("params", [{}, {"date_from": "2026-10-16", "date_to": "2026-10-16"},
                                     {"agent_id": "interno"}, {"customer_id": "123"}])
def test_valid_report_filters_still_work(env, params):
    client, *_ = env
    response = client.get("/api/reports/summary", params=params)
    assert response.status_code == 200
    assert response.json()["metrics"]["giri_effettuati"] == 0


@pytest.mark.parametrize("name", ["=1+1", "+1+1", "-1+1", "@SUM(1)", " \t=1+1"])
def test_report_export_keeps_user_names_as_text(env, name):
    import csv
    import io
    from test_stability import seed_route

    client, db, *_ = env
    route, _, _ = seed_route(env)
    route.status = "completato"
    route.nome = name
    db.commit()
    response = client.get("/api/reports/export")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text), delimiter=";"))
    assert rows[1][1] == "'" + name
    assert float(rows[1][6]) == 0  # Numeric metrics are not converted to text.
