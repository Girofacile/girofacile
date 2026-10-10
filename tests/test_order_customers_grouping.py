"""Customer recognition, precedence, grouping and stable multi-order delivery links."""
from copy import deepcopy
import pytest
from test_order_planning import planning, routing_env, env, ready, preview
from app.models import Customer, Delivery, RoutePlan
from app.order_models import Order, CustomerSourceMapping, RouteOrderAssignment


def customer(ctx, **values):
    db=ctx[1];row=Customer(user_id=ctx[2].id,nome='Recipient',indirizzo='Order address',**values)
    db.add(row);db.commit();return row


def create(ctx, **values):
    response=ctx[0].post('/api/orders',json={'number':'MATCH','recipient_name':'Recipient','delivery_address':'Order address',**values})
    assert response.status_code==201,response.text
    return response.json()


def action(ctx, order, name, **values):
    return ctx[0].post(f"/api/orders/{order['id']}/customer",json={'version':order['version'],'action':name,**values})


def test_certain_normalized_and_ambiguous_matches(planning):
    ctx,_=planning;c=customer(ctx)
    order=create(ctx,recipient_name='  RECIPIENT ',delivery_address='Order, address')
    assert order['customer_id']==c.id and order['customer_resolution']=='automatic'
    assert order['address_verification'] is None
    customer(ctx)
    ambiguous=create(ctx)
    assert ambiguous['customer_id'] is None
    result=ctx[0].get(f"/api/orders/{ambiguous['id']}/customers").json()
    assert result['kind']=='probable' and len(result['candidates'])==2
    assert any(a['code']=='customer' and a['blocking'] for a in ambiguous['anomalies'])
    separated=action(ctx,ambiguous,'separate').json()
    assert separated['customer_resolution']=='separate'
    assert not any(a['code']=='customer' for a in separated['anomalies'])
    assert separated['original_payload']==ambiguous['original_payload']


def test_probable_confirmation_mapping_and_tenant_isolation(planning):
    ctx,_=planning;client,db,owner,other,*_=ctx;c=customer(ctx)
    order=create(ctx,delivery_address='Different destination')
    assert order['customer_id'] is None
    row=db.get(Order,order['id']);row.external_customer_id='EXT-C';db.commit()
    linked=action(ctx,order,'link',customer_id=c.id)
    assert linked.status_code==200,linked.text
    assert linked.json()['effective_data']['delivery_address']=='Different destination'
    assert db.query(CustomerSourceMapping).one().customer_id==c.id
    from app.services.order_customers import auto_link
    second=db.get(Order,create(ctx,recipient_name='External alias')['id']);second.external_customer_id='EXT-C'
    auto_link(db,second,'test');db.commit();assert second.customer_id==c.id
    foreign=Customer(user_id=other.id,nome='Foreign',indirizzo='Foreign address');db.add(foreign);db.commit()
    result=action(ctx,linked.json(),'link',customer_id=foreign.id)
    assert result.status_code==404
    c.is_active=False;db.commit()
    assert ctx[0].get(f"/api/orders/{order['id']}/customers").json()['kind']=='invalid'


def test_defaults_respect_false_and_verify_effective_address(planning,monkeypatch):
    from datetime import time
    ctx,_=planning;c=customer(ctx,sponda=True,ztl=True,transpallet=True,scarico_mattina_da=time(9),scarico_mattina_a=time(12))
    order=create(ctx,delivery_address=None,tail_lift=False,ztl=False)
    order=action(ctx,order,'link',customer_id=c.id).json()
    assert order['effective_data']['tail_lift'] is False and order['effective_data']['ztl'] is False
    assert order['effective_data']['pallet_truck'] is True
    assert order['effective_data']['delivery_address']=='Order address'
    assert order['operational_data']['delivery_address'] is None
    from app.services.occasional_stops import sign_stop_address
    def verify(db,uid,address):
        return {'indirizzo':address,'stato_geocodifica':'verificato','lat':45.2,'lon':9.2,'geocoding_token':sign_stop_address(uid,address,45.2,9.2)}
    monkeypatch.setattr('app.services.orders.verify_stop_address',verify)
    verified=ctx[0].post(f"/api/orders/{order['id']}/verify-address",json={'version':order['version']}).json()
    ready_response=ctx[0].post(f"/api/orders/{order['id']}/status",json={'version':verified['version'],'status':'pronto'})
    assert ready_response.status_code==200,ready_response.text
    state,_=preview(planning,[ctx[1].get(Order,order['id'])])
    stop=state['stops'][0]
    assert stop['sponda'] is False and stop['scarico_mattina_da']=='09:00:00'
    assert stop['order_operational']['pallet_truck'] is True
    # A changed inherited address must be verified again.
    c.indirizzo='New address';ctx[1].commit()
    from app.services.order_planning import to_stop
    from fastapi import HTTPException
    with pytest.raises(HTTPException):to_stop(ctx[1].get(Order,order['id']))


def test_create_customer_explicit_atomic_and_versioned(planning):
    ctx,_=planning;db=ctx[1];before=db.query(Customer).count();order=create(ctx)
    assert db.query(Customer).count()==before
    result=action(ctx,order,'create');assert result.status_code==200,result.text
    created=db.get(Customer,result.json()['customer_id'])
    assert created.stato_geocodifica=='da_verificare' and created.lat is None
    assert db.query(Customer).count()==before+1
    assert action(ctx,order,'create').status_code==409
    assert db.query(Customer).count()==before+1


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


def test_invalid_mapping_can_be_repaired_by_explicit_confirmation(planning):
    ctx,_=planning;db=ctx[1];old=customer(ctx);order=create(ctx,delivery_address='Other address')
    row=db.get(Order,order['id']);row.external_customer_id='REPAIR';db.commit()
    linked=action(ctx,order,'link',customer_id=old.id).json()
    old.is_active=False;db.commit()
    replacement=customer(ctx)
    result=action(ctx,linked,'link',customer_id=replacement.id)
    assert result.status_code==200,result.text
    assert db.query(CustomerSourceMapping).one().customer_id==replacement.id
    assert result.json()['customer_id']==replacement.id
