"""Unfinished routes must remain discoverable until explicitly closed."""
from datetime import time, timedelta

from test_agents_feature import env
from test_stability import seed_route


def test_old_running_route_remains_visible_and_cancel_releases_driver(env):
    from app.core.utils import local_today
    from app.models import RoutePlan, DeliveryStatus
    from app.routers import routes, driver

    client, db, owner, other, *_ = env
    running, delivery, account = seed_route(env)
    running.data_giro = local_today() - timedelta(days=30)
    evidence = DeliveryStatus(route_plan_id=running.id, delivery_id=delivery.id,
                              status='completata', note_operatore='Esito conservato')
    next_route = RoutePlan(user_id=owner.id, driver_id=running.driver_id,
                           nome='Nuovo giro', data_giro=local_today(),
                           orario_partenza=time(8), status='programmato')
    foreign = RoutePlan(user_id=other.id, nome='Altra azienda',
                        data_giro=running.data_giro, orario_partenza=time(8), status='in_corso')
    db.add_all([evidence, next_route, foreign])
    # Closed/draft rows must not consume the scheduled-list limit.
    db.add_all([RoutePlan(user_id=owner.id, nome=f'Chiuso {i}',
                          data_giro=local_today(), orario_partenza=time(7), status='annullato')
                for i in range(151)])
    db.commit()
    client.app.include_router(routes.router)
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account

    visible = client.get('/api/routes/operativi').json()
    assert {r['id'] for r in visible} == {running.id, next_route.id}
    assert client.post(f'/api/driver/routes/{next_route.id}/start').status_code == 409
    assert client.post(f'/api/routes/{foreign.id}/cancel').status_code == 404
    response = client.post(f'/api/routes/{running.id}/cancel')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'annullato'
    assert evidence.status == 'completata' and evidence.note_operatore == 'Esito conservato'
    assert {r['id'] for r in client.get('/api/routes/operativi').json()} == {next_route.id}
    # Giri programmati: anche gli annullati recenti, mai quelli di altre aziende o troppo vecchi.
    with_cancelled = client.get('/api/routes/operativi?include_cancelled=true').json()
    cancelled = [r for r in with_cancelled if r['status'] == 'annullato']
    assert len(cancelled) == 150 and all(r['cancelled_at'] is None for r in cancelled)
    assert {r['id'] for r in with_cancelled} - {r['id'] for r in cancelled} == {next_route.id}
    assert client.post(f'/api/driver/routes/{next_route.id}/start').status_code == 200


def test_scheduled_limit_never_truncates_running_routes(env):
    from app.core.utils import local_today
    from app.models import RoutePlan
    from app.routers import routes

    client, db, owner, *_ = env
    running = RoutePlan(user_id=owner.id, nome='Sempre visibile',
                        data_giro=local_today() + timedelta(days=10),
                        orario_partenza=time(8), status='in_corso')
    db.add(running)
    db.add_all([RoutePlan(user_id=owner.id, nome=f'Programmato {i}',
                          data_giro=local_today(), orario_partenza=time(8), status='programmato')
                for i in range(151)])
    db.commit()
    client.app.include_router(routes.router)
    response = client.get('/api/routes/operativi')
    assert response.status_code == 200
    assert len(response.json()) == 151
    assert response.json()[0]['id'] == running.id
