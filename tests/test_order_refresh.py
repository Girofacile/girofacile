"""Ordini aggiornati dopo la selezione: i dati si ricaricano invece di bloccare il calcolo."""
from test_routing_architecture import routing_env, payload  # noqa: F401
from test_agents_feature import env  # noqa: F401
from test_order_planning import planning, ready, preview, calculate  # noqa: F401
from app.services.orders import touch


def test_preview_reloads_order_changed_after_selection(planning):  # noqa: F811
    ctx, _ = planning
    client, db, *_ = ctx
    row = ready(ctx, packages=3, weight_kg=10)
    state, config = preview(planning, [row])
    # L'operatore ha cambiato la durata dello scarico: è una scelta sulla fermata e resta.
    stops = [{**state['stops'][0], 'tempo_scarico_min': 25}]
    saved = client.put('/api/order-planning/snapshot', json={'version': state['version'], 'configuration': config, 'stops': stops}).json()
    row.operational_data = {**row.operational_data, 'packages': 7}
    touch(row)
    db.commit()
    # Come il pianificatore: l'anteprima riceve le fermate aperte.
    response = client.post('/api/order-planning/preview', json={'version': saved['version'], 'configuration': config, 'stops': saved['stops']})
    assert response.status_code == 200, response.text
    stop = response.json()['stops'][0]
    assert stop['colli'] == 7 and stop['tempo_scarico_min'] == 25
    assert stop['order_refs'] == [{'id': row.id, 'version': row.version}]
    assert any('ORD-1: aggiornato dopo la selezione' in w for w in response.json()['warnings'])


def test_saved_route_recalculates_with_its_old_references(planning):  # noqa: F811
    ctx, _ = planning
    client = ctx[0]
    route, config = calculate(planning, [ready(ctx)])
    stale = [{**stop, 'order_refs': [{**ref, 'version': ref['version'] - 1} for ref in stop['order_refs']]}
             if stop.get('order_refs') else stop for stop in route['consegne']]
    response = client.post('/api/routes/recalculate-manual', json={**config, 'route_id': route['id'], 'consegne': stale})
    assert response.status_code == 200, response.text


def test_cancelled_order_still_blocks(planning):  # noqa: F811
    ctx, _ = planning
    client, db, *_ = ctx
    row = ready(ctx)
    state, config = preview(planning, [row])
    row.status = 'annullato'
    touch(row)
    db.commit()
    response = client.post('/api/routes/optimize', json={**config, 'consegne': state['stops']})
    assert response.status_code == 409
