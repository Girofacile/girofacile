"""Selected-only, cached and auditable address verification; no external API calls."""
from copy import deepcopy
import pytest
from fastapi import HTTPException
from test_orders import orders,create

@pytest.fixture
def selected_orders(orders):
    from app.routers.order_planning import router
    orders[0].app.include_router(router)
    return orders

def select(ctx,ids):
    client=ctx[0]
    state=client.get('/api/order-planning/selection').json()
    response=client.put('/api/order-planning/selection',json={'version':state['version'],'action':'add','order_ids':ids})
    assert response.status_code==200,response.text
    return response.json()

def verify(ctx,state,ids,retry=False):
    return ctx[0].post('/api/order-planning/verify-selected',json={'version':state['version'],'order_ids':ids,'retry':retry})

def proof(ctx,address):
    from app.services.occasional_stops import sign_stop_address
    return {'indirizzo':address,'stato_geocodifica':'verificato','lat':45.2,'lon':9.2,
            'geocoding_token':sign_stop_address(ctx[2].id,address,45.2,9.2)}

def test_lazy_selection_and_identical_verified_addresses_are_reused(selected_orders,monkeypatch):
    ctx=selected_orders;client=ctx[0]
    from app.services import orders as service
    calls=[]
    def geocode(db,user_id,address,**kwargs):calls.append(address);return proof(ctx,address)
    monkeypatch.setattr(service,'verify_stop_address',geocode)
    rows=[create(client,number=str(i)) for i in range(3)]
    original=deepcopy(rows[0]['original_payload'])
    state=select(ctx,[r['id'] for r in rows[:2]])
    assert calls==[]
    result=verify(ctx,state,state['order_ids'])
    assert result.status_code==200,result.text
    assert result.json()['issues']==[] and len(calls)==1
    again=verify(ctx,result.json()['selection'],state['order_ids'])
    assert again.status_code==200 and len(calls)==1
    assert client.get(f"/api/orders/{rows[2]['id']}").json()['status']=='nuovo'
    assert client.get(f"/api/orders/{rows[0]['id']}").json()['original_payload']==original

def test_wrong_address_is_cached_and_explicit_retry_rechecks(selected_orders,monkeypatch):
    ctx=selected_orders;client=ctx[0]
    from app.services import orders as service
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1);raise HTTPException(422,{'kind':'address','message':'Indirizzo non trovato','candidate':{'lat':45.2,'lon':9.2}})
    monkeypatch.setattr(service,'verify_stop_address',fail)
    rows=[create(client,number=str(i)) for i in range(2)]
    state=select(ctx,[r['id'] for r in rows])
    result=verify(ctx,state,state['order_ids']).json()
    assert len(result['issues'])==2 and len(calls)==1
    assert result['issues'][0]['candidate']['lat']==45.2
    verify(ctx,result['selection'],state['order_ids'],retry=True)
    assert len(calls)==3

def test_provider_failure_stops_the_queue_without_marking_addresses_wrong(selected_orders,monkeypatch):
    ctx=selected_orders;client=ctx[0]
    from app.services import orders as service
    calls=[]
    def fail(*args,**kwargs):calls.append(1);raise HTTPException(503,'Servizio temporaneamente non disponibile')
    monkeypatch.setattr(service,'verify_stop_address',fail)
    rows=[create(client,number=str(i)) for i in range(5)]
    state=select(ctx,[r['id'] for r in rows])
    result=verify(ctx,state,state['order_ids'][:3]).json()
    assert len(calls)==1 and result['aborted'] and len(result['issues'])==5
    assert all(i['kind']=='service' for i in result['issues'])
    assert all(client.get(f"/api/orders/{r['id']}").json()['address_verification'] is None for r in rows)

def test_only_owned_selected_editable_orders_can_be_verified(selected_orders):
    ctx=selected_orders;client,db,owner,other=ctx
    a=create(client,number='A');b=create(client,number='B')
    state=select(ctx,[a['id']])
    assert verify(ctx,state,[b['id']]).status_code==409
    from app.core.dependencies import current_user
    client.app.dependency_overrides[current_user]=lambda:other
    assert verify(ctx,state,[a['id']]).status_code==409

def test_manual_position_is_explicit_signed_and_usable_for_planning(selected_orders):
    ctx=selected_orders;client=ctx[0]
    row=create(client);state=select(ctx,[row['id']])
    payload={'version':state['version'],'order_id':row['id'],'order_version':row['version'],
             'action':'manual','address':row['delivery_address'],'recipient_name':row['recipient_name']}
    assert client.post('/api/order-planning/resolve-address',json=payload).status_code==422
    assert client.post('/api/order-planning/resolve-address',json={**payload,'lat':999,'lon':1}).status_code==422
    response=client.post('/api/order-planning/resolve-address',json={**payload,'lat':45.2,'lon':9.2})
    assert response.status_code==200,response.text
    detail=client.get(f"/api/orders/{row['id']}").json()
    assert detail['verification_status']=='manual' and detail['address_verification']['confirmed_manually']
    assert detail['original_payload']==row['original_payload']
    stops=client.get('/api/order-planning/selection?include_stops=true').json()['stops']
    from app.services.occasional_stops import validate_occasional_stops
    validate_occasional_stops(ctx[2].id,stops)
    assert stops[0]['lat']==45.2
    assert any(e['kind']=='address_verified' and e['changes']['method']=='manual_position' for e in detail['events'])

def test_correct_and_exclude_preserve_original_and_do_not_cancel_orders(selected_orders,monkeypatch):
    ctx=selected_orders;client=ctx[0]
    row=create(client);state=select(ctx,[row['id']])
    payload={'version':state['version'],'order_id':row['id'],'order_version':row['version'],
             'action':'correct','address':'Via Corretta 9, Roma','recipient_name':row['recipient_name']}
    response=client.post('/api/order-planning/resolve-address',json=payload)
    assert response.status_code==200,response.text
    detail=client.get(f"/api/orders/{row['id']}").json()
    assert detail['delivery_address']=='Via Corretta 9, Roma'
    assert detail['original_payload']==row['original_payload']
    removed=client.post('/api/order-planning/resolve-address',json={'version':response.json()['selection']['version'],
        'order_id':row['id'],'order_version':detail['version'],'action':'exclude'})
    assert removed.status_code==200 and removed.json()['selection']['order_ids']==[]
    assert client.get(f"/api/orders/{row['id']}").json()['status']!='annullato'

def test_strict_geocoding_distinguishes_service_failure_and_zero_results(selected_orders,monkeypatch):
    from app.services import geocoding
    from app.services.occasional_stops import verify_stop_address
    ctx=selected_orders
    monkeypatch.setattr(geocoding,'google_maps_api_key',lambda db:'test')
    monkeypatch.setattr(geocoding,'google_geocoding_enabled',lambda db:True)
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'status':'ZERO_RESULTS'}
    monkeypatch.setattr(geocoding.requests,'get',lambda *a,**k:Response())
    with pytest.raises(HTTPException) as absent:
        verify_stop_address(ctx[1],ctx[2].id,'No address',strict=True)
    assert absent.value.status_code==422
    def offline(*a,**k):raise TimeoutError()
    monkeypatch.setattr(geocoding.requests,'get',offline)
    with pytest.raises(HTTPException) as unavailable:
        verify_stop_address(ctx[1],ctx[2].id,'No address',strict=True)
    assert unavailable.value.status_code==503


def test_stale_order_during_geocoding_cannot_be_overwritten(selected_orders,monkeypatch):
    from app.services import orders as service
    from app.order_models import Order
    ctx=selected_orders;client,db=ctx[:2]
    row=create(client);state=select(ctx,[row['id']])
    def changed(*args,**kwargs):
        order=db.get(Order,row['id']);order.status='annullato';service.touch(order);db.commit()
        return proof(ctx,row['delivery_address'])
    monkeypatch.setattr(service,'verify_stop_address',changed)
    response=verify(ctx,state,[row['id']])
    assert response.status_code==409
    assert db.get(Order,row['id']).status=='annullato'
    assert db.get(Order,row['id']).address_verification is None


def test_selection_version_checked_before_resolution(selected_orders):
    ctx=selected_orders;client=ctx[0]
    row=create(client);state=select(ctx,[row['id']])
    select(ctx,[create(client,number='Other')['id']])
    response=client.post('/api/order-planning/resolve-address',json={'version':state['version'],'order_id':row['id'],
        'order_version':row['version'],'action':'exclude'})
    assert response.status_code==409
