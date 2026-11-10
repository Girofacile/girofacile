"""Un cliente già servito da un giro programmato lo stesso giorno viene segnalato nell'anteprima (collaudo 10/11)."""
from test_agents_feature import env  # noqa: F401  (fixture)
from test_routing_architecture import routing_env, saved_route, payload  # noqa: F401


def test_preview_flags_customer_already_programmed_that_day(routing_env):
    ctx = routing_env
    client = ctx[0]
    first = saved_route(ctx)
    assert first['clienti_gia_programmati'] == []
    assert client.post(f"/api/routes/{first['id']}/program", json={}).status_code == 200
    body = payload(ctx); body['orario_partenza'] = '14:00'
    for stop in body['consegne']: stop.pop('scarico_mattina_da', None); stop.pop('scarico_mattina_a', None)
    response = client.post('/api/routes/recalculate-manual', json=body)
    assert response.status_code == 200, response.text
    second = response.json()
    dup = second['clienti_gia_programmati']
    assert len(dup) == 1 and dup[0]['route_id'] == first['id'] and dup[0]['cliente_nome']
    # Una volta programmato, il giro non segnala più se stesso.
    programmed = client.get(f"/api/routes/{first['id']}").json()
    assert programmed['clienti_gia_programmati'] == []
