"""Il portale autista mostra percorso e orari, mai costi e pedaggi dell'azienda."""
from test_agents_feature import env
from test_stability import seed_route


def test_driver_route_detail_hides_company_costs(env):
    from app.routers import driver

    client, db, *_ = env
    route, _, account = seed_route(env)
    route.costo_carburante, route.costo_totale, route.toll_estimated_eur = 12.5, 30.0, 4.2
    db.commit()
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account

    response = client.get(f'/api/driver/routes/{route.id}')
    assert response.status_code == 200, response.text
    data = response.json()['route']
    assert 'eta_label' in data and 'traffic_status' in data
    assert not driver.DRIVER_HIDDEN_COSTS & data.keys()
