"""La navigazione porta nel punto verificato usato per il giro, non al testo dell'indirizzo."""
from types import SimpleNamespace
from urllib.parse import unquote

from app import optimizer as opt


def test_route_link_uses_verified_coordinates_and_falls_back_to_text():
    deliveries = [
        {"indirizzo": "Via roma 1, volla (NA), Campania, Italia 155", "coord": {"lat": 40.8764449, "lon": 14.3410342}},
        {"indirizzo": "Via Senza Coordinate 3, Napoli"},
    ]
    url = opt.build_google_maps_url("Via Aldo Moro 6, Casalnuovo", deliveries, True, {"lat": 40.9, "lon": 14.35})
    parts = [unquote(x) for x in url.removeprefix("https://www.google.com/maps/dir/").split("/")]
    assert parts == ["40.900000,14.350000", "40.876445,14.341034", "Via Senza Coordinate 3, Napoli", "40.900000,14.350000"]
    assert opt.navigation_point({"lat": 0, "lon": 0}) is None and opt.navigation_point({"lat": "x", "lon": 1}) is None


def test_saved_route_link_is_rebuilt_from_saved_stop_coordinates():
    stop = lambda order, address, details: SimpleNamespace(ordine=order, indirizzo=address, optimizer_details=details)
    plan = SimpleNamespace(
        google_maps_url="https://www.google.com/maps/dir/vecchio",
        rientro_deposito=False,
        deposit=SimpleNamespace(indirizzo="Deposito", lat=None, lon=None),
        deliveries=[stop(2, "Seconda", None), stop(1, "Prima, Italia 155", '{"lat": 40.87, "lon": 14.34}')])
    url = opt.plan_navigation_url(plan)
    assert [unquote(x) for x in url.removeprefix("https://www.google.com/maps/dir/").split("/")] == ["Deposito", "40.870000,14.340000", "Seconda"]
    plan.deliveries = []
    assert opt.plan_navigation_url(plan) == "https://www.google.com/maps/dir/vecchio"
