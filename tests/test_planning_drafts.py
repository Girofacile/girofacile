"""Giri in bozza: a planning left before scheduling is saved, listed, resumed and deleted."""
import pytest
from test_routing_architecture import routing_env, payload
from test_agents_feature import env
from test_order_planning import planning, ready, preview, calculate
from app.order_models import Order, PlanningDraft


@pytest.fixture
def drafts(planning):
    from app.routers import planning_drafts
    ctx, _ = planning
    ctx[0].app.include_router(planning_drafts.router)
    return planning


def selection(client):
    return client.get('/api/order-planning/selection').json()


def test_orders_draft_clears_selection_and_resumes_configuration(drafts):
    ctx, _ = drafts
    client, db, *_ = ctx
    rows = [ready(ctx, 'ORD-1'), ready(ctx, 'ORD-2')]
    state, config = preview(drafts, rows)
    response = client.post('/api/planning-drafts', json={'source': 'orders', 'selection_version': state['version']})
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft['orders'] == 2 and draft['stops'] == 2 and draft['name']
    # La selezione si svuota: riaprendo Ordini non resta spuntato il giro lasciato.
    assert selection(client)['order_ids'] == []
    listed = client.get('/api/planning-drafts').json()
    assert [d['id'] for d in listed['drafts']] == [draft['id']]
    resumed = client.post(f'/api/planning-drafts/{draft["id"]}/resume', json={'selection_version': selection(client)['version']})
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body['dropped'] == 0 and body['source'] == 'orders'
    assert body['selection']['order_ids'] == sorted(r.id for r in rows)
    assert body['selection']['configuration']['driver_id'] == config['driver_id']
    assert body['selection']['stops'] is not None
    assert db.query(PlanningDraft).count() == 0


def test_resume_skips_orders_no_longer_plannable(drafts):
    ctx, _ = drafts
    client, db, *_ = ctx
    rows = [ready(ctx, 'ORD-1'), ready(ctx, 'ORD-2')]
    state, _ = preview(drafts, rows)
    draft = client.post('/api/planning-drafts', json={'source': 'orders', 'selection_version': state['version']}).json()
    db.get(Order, rows[0].id).status = 'annullato'
    db.commit()
    body = client.post(f'/api/planning-drafts/{draft["id"]}/resume', json={'selection_version': selection(client)['version']}).json()
    assert body['dropped'] == 1
    assert body['selection']['order_ids'] == [rows[1].id]
    # Le fermate salvate non valgono più: si rigenerano dagli ordini rimasti.
    assert body['selection']['stops'] is None


def test_resume_refuses_when_another_selection_is_open(drafts):
    ctx, _ = drafts
    client, *_ = ctx
    state, _ = preview(drafts, [ready(ctx, 'ORD-1')])
    draft = client.post('/api/planning-drafts', json={'source': 'orders', 'selection_version': state['version']}).json()
    other = ready(ctx, 'ORD-2')
    current = client.put('/api/order-planning/selection', json={'version': selection(client)['version'], 'action': 'add', 'order_ids': [other.id]}).json()
    response = client.post(f'/api/planning-drafts/{draft["id"]}/resume', json={'selection_version': current['version']})
    assert response.status_code == 409
    assert 'già degli ordini selezionati' in response.json()['detail']


def test_customers_draft_keeps_stops_and_can_be_deleted(drafts):
    ctx, _ = drafts
    client, db, *_ = ctx
    body = payload(ctx)
    configuration = {k: body[k] for k in ('nome', 'data_giro', 'orario_partenza', 'deposit_id', 'vehicle_id', 'rientro_deposito') if k in body}
    response = client.post('/api/planning-drafts', json={'source': 'customers', 'configuration': configuration, 'stops': body['consegne']})
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft['source'] == 'customers' and draft['stops'] == len(body['consegne'])
    resumed = client.post(f'/api/planning-drafts/{draft["id"]}/resume', json={}).json()
    assert [s['cliente_nome'] for s in resumed['stops']] == [s['cliente_nome'] for s in body['consegne']]
    assert resumed['configuration']['data_giro'] == configuration['data_giro']
    again = client.post('/api/planning-drafts', json={'source': 'customers', 'configuration': configuration, 'stops': body['consegne']}).json()
    assert client.delete(f'/api/planning-drafts/{again["id"]}').status_code == 200
    assert client.get('/api/planning-drafts').json()['drafts'] == []
    assert client.post('/api/planning-drafts', json={'source': 'customers', 'stops': []}).status_code == 422


def test_calculated_route_drafts_are_listed(drafts):
    ctx, _ = drafts
    client, *_ = ctx
    route, _ = calculate(drafts, [ready(ctx, 'ORD-1')])
    routes = client.get('/api/planning-drafts').json()['routes']
    assert [r['id'] for r in routes] == [route['id']]


def test_draft_remembers_stage_and_fleet_preview(drafts):
    ctx, _ = drafts
    client, *_ = ctx
    state, _ = preview(drafts, [ready(ctx, 'ORD-1')])
    draft = client.post('/api/planning-drafts', json={'source': 'orders', 'selection_version': state['version'], 'stage': 'suddivisione', 'fleet_plan_id': 42}).json()
    assert draft['stage'] == 'suddivisione' and draft['fleet_plan_id'] == 42
    resumed = client.post(f'/api/planning-drafts/{draft["id"]}/resume', json={'selection_version': selection(client)['version']}).json()
    assert resumed['stage'] == 'suddivisione' and resumed['fleet_plan_id'] == 42
    # Fuori dalla suddivisione il riferimento all'anteprima non si conserva.
    state = selection(client)
    other = client.post('/api/planning-drafts', json={'source': 'orders', 'selection_version': state['version'], 'stage': 'configurazione', 'fleet_plan_id': 42}).json()
    assert other['stage'] == 'configurazione' and other['fleet_plan_id'] is None
