"""Clienti raggiungibili solo in traghetto: esclusi dai giri e segnalati negli avvisi."""
import os
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")

import pytest

from app import optimizer as opt
from app.services import islands
from optimizer_benchmark import deliveries
from test_agents_feature import env  # noqa: F401
from test_routing_architecture import routing_env  # noqa: F401
from test_fleet_planning import fleet, preview, command  # noqa: F401
from app.models import RoutePlan
from stop_fixture import verified_stop

ISCHIA = dict(lat=40.7461, lon=13.9437)


@pytest.mark.parametrize("lat,lon,expected", [
    (40.8518, 14.2681, None),           # Napoli
    (40.8217, 14.1219, None),           # Pozzuoli porto
    (40.7461, 13.9437, "Ischia"),       # Ischia Porto
    (40.7376, 13.8606, "Ischia"),       # Forio
    (40.7650, 14.0285, "Procida"),
    (40.5560, 14.2380, "Capri"),
    (38.1938, 15.5540, "Sicilia"),      # Messina
    (38.2670, 15.6460, "Sicilia"),      # Torre Faro, sullo Stretto
    (38.2190, 15.6370, None),           # Villa San Giovanni
    (38.1110, 15.6470, None),           # Reggio Calabria
    (38.2540, 15.7160, None),           # Scilla
    (38.1330, 13.3680, "Sicilia"),      # Palermo porto
    (37.0600, 15.2930, "Sicilia"),      # Ortigia, unita da ponte
    (38.4670, 14.9540, "Lipari"),
    (39.2110, 9.1100, "Sardegna"),      # Cagliari porto
    (39.0700, 8.4040, "Sardegna"),      # Sant'Antioco, unita da ponte
    (39.1440, 8.3060, "San Pietro"),    # Carloforte
    (41.2100, 9.4500, "La Maddalena"),  # Caprera, unita da ponte
    (42.8130, 10.3290, "Elba"),         # Portoferraio
    (42.9250, 10.5270, None),           # Piombino
    (45.4340, 12.3390, None),           # Venezia centro, collegata da ponte
    (45.4260, 12.3250, "Giudecca"),
    (45.4100, 12.3700, "Lido"),
    (45.4900, 12.2420, None),           # Mestre
    (45.4642, 9.1900, None),            # Milano
    (35.5000, 12.6050, "Lampedusa"),
])
def test_landmass_of_known_places(lat, lon, expected):
    assert islands.landmass(lat, lon) == expected


def test_reason_depends_on_depot_landmass():
    napoli, messina = dict(lat=40.8518, lon=14.2681), dict(lat=38.1938, lon=15.5540)
    assert "isola (Ischia)" in islands.ferry_reason(napoli, ISCHIA)
    assert islands.ferry_reason(ISCHIA, dict(lat=40.7376, lon=13.8606)) is None
    assert islands.ferry_reason(messina, dict(lat=38.0170, lon=12.5150)) is None
    assert "fuori dall'isola del deposito (Sicilia)" in islands.ferry_reason(messina, dict(lat=38.1110, lon=15.6470))
    assert islands.ferry_reason(napoli, dict(lat=None, lon=None)) is None


@pytest.fixture
def offline_single(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Nessuna chiamata esterna nei test")
    monkeypatch.setattr(opt.requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(opt, "geocode", forbidden)
    monkeypatch.setattr(opt, "local_now", lambda: datetime(2029, 1, 1, tzinfo=timezone.utc))
    calls = []
    def stub(db, user_id, points, keys, **kwargs):
        calls.append(points)
        return {(i, j): {"km": 1, "min": 5} for i in range(len(points)) for j in range(len(points)) if i != j}
    monkeypatch.setattr(opt, "build_distance_matrix", stub)
    return calls


@pytest.mark.parametrize("entrypoint", [opt.optimize_route, opt.recalculate_manual_route])
def test_single_route_excludes_island_customer(offline_single, entrypoint):
    rows = deliveries(3)
    for row in rows:
        row.pop("_matrix_index")
    rows[1].update(cliente_nome="Hotel Ischia", peso_kg=9999, **ISCHIA)
    deposit = SimpleNamespace(id=1, user_id=7, lat=45, lon=9, indirizzo="Deposito")
    # Il peso della consegna esclusa non conta per la capacità del mezzo.
    result = entrypoint(None, deposit, rows, vehicle={"capacita_kg": 100}, route_date="2030-01-15")
    assert sorted(d["customer_id"] for d in result["ordered"]) == [1, 3]
    assert len(offline_single[0]) == 3
    assert result["consegne_escluse"] == [{
        "customer_id": 2, "cliente_nome": "Hotel Ischia", "indirizzo": "Via 2", "order_refs": [],
        "motivo": "Consegna non programmabile: il cliente si trova su un'isola (Ischia), raggiungibile solo in traghetto."}]


def test_single_route_without_mainland_customers_is_rejected(offline_single):
    rows = deliveries(1)
    rows[0].pop("_matrix_index")
    rows[0].update(**ISCHIA)
    deposit = SimpleNamespace(id=1, user_id=7, lat=45, lon=9, indirizzo="Deposito")
    with pytest.raises(ValueError, match="Nessuna consegna programmabile.*Ischia"):
        opt.optimize_route(None, deposit, rows, route_date="2030-01-15")
    assert offline_single == []


def test_fleet_leaves_island_customers_unassigned(fleet):  # noqa: F811
    data = deepcopy(fleet[1])
    owner = fleet[0][2]
    data["consegne"][3] = verified_stop(owner.id, cliente_nome="Bar Forio", indirizzo="Via Forio", lat=40.7376, lon=13.8606,
                                        peso_kg=10, colli=1, tempo_scarico_min=5)
    plan = preview(fleet, data)
    assigned = sorted(i for route in plan["routes"] for i in route["stop_indexes"])
    assert assigned == [i for i in range(30) if i != 3]
    assert plan["unassigned"] == [{"index": 3, "reason":
        "Consegna non programmabile: il cliente si trova su un'isola (Ischia), raggiungibile solo in traghetto."}]
    assert plan["warnings"][0].startswith("1 consegna esclusa dal giro (Bar Forio)")
    # Assegnarla a mano non la fa entrare nel giro.
    assignments = [None] * 30
    for route in plan["routes"]:
        for i in route["stop_indexes"]:
            assignments[i] = route["resource"]
    assignments[3] = 0
    revised = command(fleet, plan, "revise", assignments=assignments)
    assert revised.status_code == 200, revised.text
    plan = revised.json()
    assert plan["unassigned"][0]["index"] == 3
    assert all(3 not in route["stop_indexes"] for route in plan["routes"])
    assert command(fleet, plan, "confirm").status_code == 422
    saved = command(fleet, plan, "confirm", accept_unassigned=True)
    assert saved.status_code == 200, saved.text
    assert sum(len(r.deliveries) for r in fleet[0][1].query(RoutePlan)) == 29


def test_fleet_with_only_island_customers(fleet):  # noqa: F811
    data = deepcopy(fleet[1])
    data["consegne"] = [verified_stop(fleet[0][2].id, cliente_nome=f"Ischia {i}", indirizzo=f"Via Ischia {i}",
                                      peso_kg=10, colli=1, tempo_scarico_min=5, **ISCHIA) for i in range(2)]
    plan = preview(fleet, data)
    assert plan["routes"] == [] and [u["index"] for u in plan["unassigned"]] == [0, 1]
    assert plan["warnings"][0].startswith("2 consegne escluse dai giri")
    assert command(fleet, plan, "confirm", accept_unassigned=True).status_code == 422
