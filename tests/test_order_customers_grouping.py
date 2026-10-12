"""Orders are independent of customers; compatible orders may share a delivery stop."""
from copy import deepcopy
import pytest
from test_order_planning import planning, routing_env, env, ready, preview
from app.models import Customer, Delivery, RoutePlan
from app.order_models import Order, CustomerSourceMapping, RouteOrderAssignment

def customer(ctx, **values):
    db=ctx[1]
    row=Customer(user_id=ctx[2].id,nome='Recipient',indirizzo='Order address',**values)
    db.add(row);db.commit();return row

def create(ctx, **values):
    response=ctx[0].post('/api/orders',json={'number':'MATCH',
        'recipient_name':'Recipient','delivery_address':'Order address',**values})
    assert response.status_code==201,response.text
    return response.json()

def test_identical_customer_is_never_linked_and_never_inherited(planning):
    from datetime import time
    from app.services.order_planning import to_stop
    from fastapi import HTTPException
    ctx,_=planning
    known=customer(ctx,sponda=True,transpallet=True,ztl=True,
        scarico_mattina_da=time(9),scarico_mattina_a=time(12),
        lat=45.2,lon=9.2,stato_geocodifica='verificato',note='Nota anagrafica')
    order=create(ctx,tail_lift=False,notes='Nota ordine')
    assert 'customer_id' not in order and 'customer_resolution' not in order
    assert order['status']=='nuovo' and order['address_verification'] is None
    assert order['effective_data']['tail_lift'] is False
    assert order['effective_data']['pallet_truck'] is None
    assert order['effective_data']['ztl'] is None
    assert order['effective_data']['notes']=='Nota ordine'
    assert not order['effective_data'].get('time_from')
    assert ctx[1].get(Order,order['id']).customer_id is None
    assert ctx[1].query(CustomerSourceMapping).count()==0
    assert known.lat==45.2
    with pytest.raises(HTTPException):to_stop(ctx[1].get(Order,order['id']))
    assert ctx[0].get(f"/api/orders/{order['id']}/customers").status_code==404
    assert ctx[0].post(f"/api/orders/{order['id']}/customer",
        json={'version':order['version'],'action':'link','customer_id':known.id}).status_code==404

def test_legacy_customer_link_is_ignored_for_order_planning(planning):
    from app.services.order_planning import to_stop
    from fastapi import HTTPException
    ctx,_=planning
    known=customer(ctx,sponda=True,transpallet=True,note='Customer note')
    order=create(ctx,tail_lift=False)
    row=ctx[1].get(Order,order['id'])
    row.customer_id=known.id
    row.customer_resolution='confirmed'
    ctx[1].commit()
    detail=ctx[0].get(f"/api/orders/{row.id}").json()
    assert 'customer_id' not in detail and 'inherited_fields' not in detail
    assert detail['effective_data']['tail_lift'] is False
    assert detail['effective_data']['notes'] is None
    with pytest.raises(HTTPException):to_stop(row)

def test_grouping_lifecycle_and_partial_regroup(planning):
    ctx,_=planning;client,db,*_=ctx
    a=ready(ctx,'A',weight_kg=10,packages=2,time_from='09:00',time_to='12:00')
    b=ready(ctx,'B',weight_kg=20,packages=3,time_from='10:00',time_to='13:00')
    original=deepcopy(a.original_payload)
    state,config=preview(planning,[a,b]);config['group_orders']=True
    grouped=client.post('/api/order-planning/preview',json={'version':state['version'],'configuration':config,'stops':None})
    assert grouped.status_code==200,grouped.text
    stop=grouped.json()['stops'][0]
    assert len(grouped.json()['stops'])==1 and len(stop['order_refs'])==2
    assert stop['peso_kg']==30 and stop['colli']==5
    assert stop['scarico_mattina_da']=='10:00' and stop['scarico_mattina_a']=='12:00'
    response=client.post('/api/routes/optimize',json={k:v for k,v in {**config,'consegne':[stop]}.items() if k!='group_orders'})
    assert response.status_code==200,response.text
    route=response.json();rid=route['id']
    assert len(route['consegne'][0]['order_refs'])==2
    saved=client.get(f'/api/routes/{rid}').json()
    result=client.post('/api/routes/recalculate-manual',json={**{k:v for k,v in config.items() if k!='group_orders'},'route_id':rid,'consegne':saved['consegne']})
    assert result.status_code==200,result.text
    assert db.query(RouteOrderAssignment).count()==2
    from app.services.order_planning import to_stop
    # Split a previously grouped stop: both stable links must follow their new stop keys.
    result=client.post('/api/routes/recalculate-manual',json={**{k:v for k,v in config.items() if k!='group_orders'},'route_id':rid,'consegne':[to_stop(a),to_stop(b)]})
    assert result.status_code==200,result.text
    assert len({link.stop_key for link in db.query(RouteOrderAssignment)})==2
    from app.services.route_execution import apply_delivery_update
    delivery=db.query(Delivery).filter_by(route_plan_id=rid).order_by(Delivery.ordine).first()
    apply_delivery_update(db,delivery,{},'complete');db.commit()
    assert sorted([a.status,b.status])==['consegnato','in_consegna']
    assert a.original_payload==original


def test_incompatible_groups_and_forged_merge_are_rejected(planning):
    from app.services.order_grouping import group_stops,group_key
    from app.services.order_planning import to_stop
    ctx,_=planning;client=ctx[0]
    a=ready(ctx,'A',time_from='09:00',time_to='10:00',tail_lift=False)
    b=ready(ctx,'B',time_from='11:00',time_to='12:00',tail_lift=True)
    assert len(group_stops(ctx[2].id,[to_stop(a),to_stop(b)]))==2
    state,config=preview(planning,[a,b]);stop=state['stops'][0]
    stop['order_refs']+=state['stops'][1]['order_refs'];stop['order_stop_key']=group_key(ctx[2].id,[a.id,b.id])
    assert client.post('/api/routes/optimize',json={**config,'consegne':[stop]}).status_code==422
    assert not ctx[-1]


def test_group_delivery_updates_every_original_order(planning):
    from app.services.route_execution import apply_delivery_update
    ctx,_=planning;client,db,*_=ctx
    a=ready(ctx,'A');b=ready(ctx,'B')
    state,config=preview(planning,[a,b])
    state=client.post('/api/order-planning/preview',json={'version':state['version'],'configuration':{**config,'group_orders':True}}).json()
    response=client.post('/api/routes/optimize',json={**config,'consegne':state['stops']})
    assert response.status_code==200,response.text
    delivery=db.query(Delivery).filter_by(route_plan_id=response.json()['id']).one()
    from app.routers.operator import delivery_to_operator_dict
    assert delivery_to_operator_dict(delivery,None)['order_numbers']==['A','B']
    apply_delivery_update(db,delivery,{},'complete');db.commit()
    assert a.status==b.status=='consegnato'
    assert db.query(RouteOrderAssignment).count()==2


def test_grouping_never_merges_different_destination_or_customer(planning):
    from app.services.order_grouping import group_stops
    from app.services.order_planning import to_stop
    ctx,_=planning;a=ready(ctx,'A');b=ready(ctx,'B',delivery_address='Other address')
    assert len(group_stops(ctx[2].id,[to_stop(a),to_stop(b)]))==2
    b.recipient_name='Different recipient';b.delivery_address=a.delivery_address;b.address_verification=a.address_verification
    values=dict(b.operational_data);values.update(recipient_name=b.recipient_name,delivery_address=b.delivery_address);b.operational_data=values
    assert len(group_stops(ctx[2].id,[to_stop(a),to_stop(b)]))==2


