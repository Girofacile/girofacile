"""«Aggiungi ordini» e «Aggiungi clienti»: ordini aggiunti senza rigenerare le fermate."""
from test_routing_architecture import routing_env, payload  # noqa: F401
from test_agents_feature import env  # noqa: F401
from test_order_planning import planning, ready, preview  # noqa: F401
from app.models import Customer
from app.order_models import OrderPlanningSelection
from app.services.occasional_stops import sign_stop_address

DAY = '2099-01-15'


def at(ctx, row, lat, lon):
    """Indirizzo verificato in un altro punto (es. un'isola)."""
    row.address_verification = {**row.address_verification, 'lat': lat, 'lon': lon,
                                 'geocoding_token': sign_stop_address(ctx[2].id, row.delivery_address, lat, lon)}
    ctx[1].commit()


def test_available_lists_only_ready_free_orders_for_the_route_date(planning):  # noqa: F811
    ctx, _ = planning
    client = ctx[0]
    today = ready(ctx, 'ORD-1', requested_date=DAY, packages=2, weight_kg=12, time_from='09:00', time_to='11:00')
    undated = ready(ctx, 'ORD-2')
    ready(ctx, 'ORD-3', requested_date='2099-01-16')
    draft = ready(ctx, 'ORD-4')
    draft.status = 'nuovo'
    ctx[1].commit()
    response = client.get(f'/api/order-planning/available?data_giro={DAY}')
    assert response.status_code == 200, response.text
    rows = response.json()['orders']
    assert [r['id'] for r in rows] == [today.id, undated.id]
    assert rows[0] | {'source': None} == {
        'id': today.id, 'number': 'ORD-1', 'source': None, 'recipient_name': 'Recipient', 'address': 'Order address',
        'requested_date': DAY, 'weight_kg': 12, 'packages': 2, 'time_from': '09:00', 'time_to': '11:00', 'ferry_reason': None}


def test_available_marks_orders_reachable_only_by_ferry(planning):  # noqa: F811
    ctx, _ = planning
    client, db, owner, _, _, depot, *_ = ctx
    depot.lat, depot.lon = 40.8518, 14.2681  # Napoli
    db.commit()
    island = ready(ctx, 'ORD-ISCHIA')
    at(ctx, island, 40.7461, 13.9437)
    rows = client.get(f'/api/order-planning/available?data_giro={DAY}&deposit_id={depot.id}').json()['orders']
    assert 'isola (Ischia)' in rows[0]['ferry_reason']


def test_append_without_selection_returns_new_stops_only(planning):  # noqa: F811
    ctx, _ = planning
    client = ctx[0]
    first, second = ready(ctx, 'ORD-1', packages=3), ready(ctx, 'ORD-2', packages=1)
    current = payload(ctx)['consegne']
    response = client.post('/api/order-planning/stops', json={'order_ids': [second.id, first.id], 'data_giro': DAY, 'stops': current})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['merged'] == [] and 'selection' not in body
    assert [s['order_refs'][0]['id'] for s in body['added']] == [first.id, second.id]
    again = client.post('/api/order-planning/stops', json={'order_ids': [first.id], 'data_giro': DAY, 'stops': body['added']})
    assert again.status_code == 409
    dated = ready(ctx, 'ORD-3', requested_date='2099-01-16')
    wrong = client.post('/api/order-planning/stops', json={'order_ids': [dated.id], 'data_giro': DAY, 'stops': []})
    assert wrong.status_code == 422 and '16/01/2099' in wrong.text


def test_append_updates_selection_and_joins_compatible_stop(planning):  # noqa: F811
    ctx, _ = planning
    client, db, *_ = ctx
    first = ready(ctx, 'ORD-1', packages=3, weight_kg=10)
    state, config = preview(planning, [first])
    # L'operatore ha modificato la fermata: la modifica deve restare.
    stops = [{**state['stops'][0], 'note': 'Citofono 4'}]
    snapshot = client.put('/api/order-planning/snapshot', json={'version': state['version'], 'configuration': {**config, 'group_orders': True}, 'stops': stops})
    assert snapshot.status_code == 200, snapshot.text
    same_place, elsewhere = ready(ctx, 'ORD-2', packages=2, weight_kg=5), ready(ctx, 'ORD-3', packages=1)
    at(ctx, elsewhere, 45.3, 9.3)
    response = client.post('/api/order-planning/stops', json={
        'order_ids': [same_place.id, elsewhere.id], 'data_giro': DAY, 'group_orders': True,
        'stops': snapshot.json()['stops'], 'version': snapshot.json()['version']})
    assert response.status_code == 200, response.text
    body = response.json()
    joined = body['merged'][0]
    assert joined['index'] == 0 and joined['stop']['colli'] == 5 and joined['stop']['peso_kg'] == 15
    assert [r['id'] for r in joined['stop']['order_refs']] == [first.id, same_place.id]
    assert 'Citofono 4' in joined['stop']['note']
    assert [s['order_refs'][0]['id'] for s in body['added']] == [elsewhere.id]
    selection = body['selection']
    assert selection['order_ids'] == sorted([first.id, same_place.id, elsewhere.id])
    assert selection['version'] == snapshot.json()['version'] + 1
    assert len(db.query(OrderPlanningSelection).one().stops) == 2
    stale = client.post('/api/order-planning/stops', json={'order_ids': [ready(ctx, 'ORD-9').id], 'data_giro': DAY,
                                                           'stops': [], 'version': snapshot.json()['version']})
    assert stale.status_code == 409


def test_customers_flag_ferry_only_with_planning_deposit(routing_env):  # noqa: F811
    client, db, owner, _, customer, depot, *_ = routing_env
    depot.lat, depot.lon = 40.8518, 14.2681  # Napoli
    island = Customer(user_id=owner.id, nome='Hotel Ischia', indirizzo='Via Iasolino 10, Ischia', lat=40.7461, lon=13.9437,
                      stato_geocodifica='verificato')
    db.add(island)
    db.commit()
    plain = {c['id']: c for c in client.get('/api/customers?planning_only=true').json()}
    assert 'ferry_reason' not in plain[island.id]
    rows = {c['id']: c for c in client.get(f'/api/customers?planning_only=true&deposit_id={depot.id}').json()}
    assert 'isola (Ischia)' in rows[island.id]['ferry_reason']
    assert rows[customer.id]['ferry_reason'] is None


def test_append_to_saved_route_keeps_its_reserved_orders(planning):  # noqa: F811
    from test_order_planning import calculate
    ctx, _ = planning
    client = ctx[0]
    route, _ = calculate(planning, [ready(ctx, 'ORD-1')])
    extra = ready(ctx, 'ORD-2')
    body = {'order_ids': [extra.id], 'data_giro': DAY, 'stops': route['consegne']}
    assert client.post('/api/order-planning/stops', json=body).status_code == 409
    response = client.post('/api/order-planning/stops', json={**body, 'route_id': route['id']})
    assert response.status_code == 200, response.text
    assert [s['order_refs'][0]['id'] for s in response.json()['added']] == [extra.id]
