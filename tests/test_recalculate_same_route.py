"""Ricalcolare un giro già salvato (bozza o programmato) lo aggiorna: niente bozza doppia accanto."""
from datetime import datetime

from app.models import RoutePlan
from test_agents_feature import env  # noqa: F401 (serve a routing_env)
from test_routing_architecture import routing_env, payload


def test_recalculating_a_draft_updates_it(routing_env):
    client, db, *_ = routing_env
    data = payload(routing_env)
    first = client.post('/api/routes/optimize', json=data)
    assert first.status_code == 200, first.text
    route_id = first.json()['id']
    # Si riapre la bozza, si cambia qualcosa e si ricalcola: stesso giro, nessun altro creato.
    again = client.post('/api/routes/optimize', json=dict(data, route_id=route_id, nome='Giro rivisto'))
    assert again.status_code == 200, again.text
    assert again.json()['id'] == route_id
    assert db.query(RoutePlan).count() == 1
    assert db.query(RoutePlan).one().nome == 'Giro rivisto'


def test_recalculating_a_programmed_route_keeps_it_programmed(routing_env):
    client, db, *_ = routing_env
    data = payload(routing_env)
    route_id = client.post('/api/routes/optimize', json=data).json()['id']
    assert client.post(f'/api/routes/{route_id}/program', json={}).status_code == 200
    again = client.post('/api/routes/optimize', json=dict(data, route_id=route_id))
    assert again.status_code == 200, again.text
    assert again.json()['id'] == route_id
    db.expire_all()
    assert db.query(RoutePlan).count() == 1
    assert db.query(RoutePlan).one().status == 'programmato'


def test_started_or_foreign_route_is_not_rewritten(routing_env):
    client, db, *_ = routing_env
    data = payload(routing_env)
    route_id = client.post('/api/routes/optimize', json=data).json()['id']
    plan = db.get(RoutePlan, route_id)
    plan.started_at = datetime.utcnow()
    plan.status = 'in_corso'
    db.commit()
    assert client.post('/api/routes/optimize', json=dict(data, route_id=route_id)).status_code == 409
    assert client.post('/api/routes/optimize', json=dict(data, route_id=999999)).status_code == 404
    assert db.query(RoutePlan).count() == 1
