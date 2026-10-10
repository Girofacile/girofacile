"""Full order-to-route lifecycle with real optimiser and mocked road providers."""
from copy import deepcopy
from datetime import date
import pytest
from test_routing_architecture import routing_env, payload
from test_agents_feature import env
from app.models import Driver, Delivery, RoutePlan
from app.order_models import Order, RouteOrderAssignment, OrderPlanningSelection
from app.services.occasional_stops import sign_stop_address


@pytest.fixture
def planning(routing_env):
    from app.routers import orders, order_planning
    ctx=routing_env
    client,db,owner,*_=ctx
    client.app.include_router(orders.router);client.app.include_router(order_planning.router)
    driver=Driver(user_id=owner.id,nome='Planner driver');db.add(driver);db.commit()
    return ctx,driver


def ready(ctx,number='ORD-1',**values):
    client,db,owner,*_=ctx
    response=client.post('/api/orders',json={'number':number,'recipient_name':'Recipient','delivery_address':'Order address',**values})
    assert response.status_code==201,response.text
    row=db.get(Order,response.json()['id'])
    row.status='pronto';row.verification_status='verified'
    row.address_verification={'input_address':row.delivery_address,'indirizzo':row.delivery_address,
        'stato_geocodifica':'verificato','lat':45.2,'lon':9.2,
        'geocoding_token':sign_stop_address(owner.id,row.delivery_address,45.2,9.2)}
    db.commit();return row


def preview(planning, rows):
    ctx,driver=planning;client=ctx[0]
    current=client.get('/api/order-planning/selection').json()
    selected=client.put('/api/order-planning/selection',json={'version':current['version'],'action':'add','order_ids':[r.id for r in rows]})
    assert selected.status_code==200,selected.text
    config={k:v for k,v in payload(ctx).items() if k not in ('consegne',)}
    config['driver_id']=driver.id
    response=client.post('/api/order-planning/preview',json={'version':selected.json()['version'],'configuration':config})
    assert response.status_code==200,response.text
    return response.json(),config


def calculate(planning,rows):
    ctx,_=planning;state,config=preview(planning,rows)
    response=ctx[0].post('/api/routes/optimize',json={**config,'consegne':state['stops']})
    assert response.status_code==200,response.text
    return response.json(),config


def test_persisted_selection_configuration_preview_without_routing(planning):
    ctx,_=planning;client,db,*_=ctx
    row=ready(ctx,weight_kg=25,packages=3,tail_lift=False,pallet_truck=True,notes='Gate B',time_from='09:00',time_to='10:00')
    state,config=preview(planning,[row])
    assert ctx[-1]==[] and db.query(RoutePlan).count()==0
    stop=state['stops'][0]
    assert stop['order_refs']==[{'id':row.id,'version':row.version}]
    assert stop['peso_kg']==25 and stop['colli']==3 and stop['note']=='Gate B'
    assert stop['sponda'] is False and stop['order_operational']['pallet_truck'] is True
    assert client.get('/api/order-planning/selection').json()['configuration']==state['configuration']
    assert client.get('/api/order-planning/selection').json()['stops']==state['stops']
    original=deepcopy(row.original_payload)
    response=client.put('/api/order-planning/snapshot',json={'version':state['version'],'configuration':config,'stops':[]})
    assert response.status_code==200,response.text
    assert response.json()['order_ids']==[] and row.original_payload==original and row.status=='pronto'


def test_all_filtered_stale_versions_and_tenant_selection(planning):
    ctx,_=planning;client,db,owner,other,*_=ctx
    a=ready(ctx,'ORD-A-unique');b=ready(ctx,'B')
    response=client.put('/api/order-planning/selection',json={'version':0,'action':'all_filtered','filters':{'q':'ORD-A-unique'}})
    assert response.json()['order_ids']==[a.id]
    assert client.put('/api/order-planning/selection',json={'version':0,'action':'clear'}).status_code==409
    from app.core.dependencies import current_user
    client.app.dependency_overrides[current_user]=lambda:other
    assert client.get('/api/order-planning/selection').json()['order_ids']==[]
    assert client.put('/api/order-planning/selection',json={'version':0,'action':'add','order_ids':[b.id]}).status_code==409
    assert db.query(OrderPlanningSelection).count()==1


def test_capacity_warning_and_calculation_block(planning):
    ctx,_=planning;client,db,*_=ctx
    ctx[6].capacita_kg=10;db.commit()
    state,config=preview(planning,[ready(ctx,weight_kg=11)])
    assert any('Capacità' in warning for warning in state['warnings'])
    response=client.post('/api/routes/optimize',json={**config,'consegne':state['stops']})
    assert response.status_code==400 and db.query(RoutePlan).count()==0


def test_reserve_draft_recalculate_program_cancel_preserve_original(planning):
    ctx,_=planning;client,db,*_=ctx
    first=ready(ctx,'First');second=ready(ctx,'Second')
    original=deepcopy(first.original_payload)
    route,config=calculate(planning,[first,second]);rid=route['id']
    assert route['status']=='bozza' and first.status=='assegnato' and first.delivery_status=='draft'
    assert db.query(RouteOrderAssignment).count()==2
    # Replaying a creation cannot silently create a second operational reservation.
    conflict=client.post('/api/routes/optimize',json={**config,'consegne':route['consegne']})
    assert conflict.status_code==409
    before={a.order_id:a.stop_key for a in db.query(RouteOrderAssignment)}
    saved=client.get(f'/api/routes/{rid}').json()
    update=client.post('/api/routes/recalculate-manual',json={**config,'route_id':rid,'consegne':list(reversed(saved['consegne']))})
    assert update.status_code==200,update.text
    assert {a.order_id:a.stop_key for a in db.query(RouteOrderAssignment)}==before
    assert first.original_payload==original
    programmed=client.post(f'/api/routes/{rid}/program',json={})
    assert programmed.status_code==200,programmed.text
    assert first.delivery_status=='scheduled'
    # Current versions are returned when reopening a programmed route.
    saved=client.get(f'/api/routes/{rid}').json()
    update=client.post('/api/routes/recalculate-manual',json={**config,'route_id':rid,'consegne':saved['consegne'][:1]})
    assert update.status_code==200,update.text
    assert db.query(RouteOrderAssignment).count()==1
    assert client.post(f'/api/routes/{rid}/cancel').status_code==200
    assert db.query(RouteOrderAssignment).count()==0
    assert first.status==second.status=='pronto'
    assert first.original_payload==original


def test_delivery_completion_and_manual_close_never_invent_delivery(planning):
    from app.services.route_execution import apply_delivery_update
    from app.services.usage_limits import start_route_usage
    ctx,_=planning;client,db,*_=ctx
    first=ready(ctx,'First');second=ready(ctx,'Second')
    route,_=calculate(planning,[first,second]);plan=db.get(RoutePlan,route['id'])
    start_route_usage(db,plan);db.commit()
    assert first.status==second.status=='in_consegna'
    delivery=next(d for d in plan.deliveries if str(first.id) in d.optimizer_details and 'First' in d.optimizer_details)
    apply_delivery_update(db,delivery,{},'complete');db.commit()
    assert first.status=='consegnato' and second.status=='in_consegna'
    assert client.post(f'/api/routes/{plan.id}/complete').status_code==200
    assert first.status=='consegnato' and second.status=='non_consegnato'
    assert db.query(RouteOrderAssignment).count()==2


def test_date_mismatch_and_forged_reference(planning):
    ctx,_=planning;client,db,*_=ctx
    row=ready(ctx,requested_date='2099-01-15');state,config=preview(planning,[row])
    wrong=deepcopy(state['stops']);wrong[0]['order_stop_key']='forged'
    assert client.post('/api/routes/optimize',json={**config,'consegne':wrong}).status_code==422
    assert client.post('/api/routes/optimize',json={**config,'data_giro':'2099-01-16','consegne':state['stops']}).status_code==422
    assert not ctx[-1]


def test_invalid_configuration_is_rejected_and_selection_preserved(planning):
    ctx,_=planning;client=ctx[0]
    row=ready(ctx);state,config=preview(planning,[row])
    for field,value in [('data_giro','bad-date'),('orario_partenza','29:90')]:
        response=client.put('/api/order-planning/snapshot',json={'version':state['version'],'configuration':{**config,field:value}})
        assert response.status_code==422
        assert client.get('/api/order-planning/selection').json()['version']==state['version']


def test_order_permission_required_even_when_removing_all_references(planning,monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.services.route_orders import require_planning_permission
    ctx,_=planning;client,db,owner,*_=ctx
    route,_=calculate(planning,[ready(ctx)])
    request=SimpleNamespace(state=SimpleNamespace(company_collaborator=SimpleNamespace(user_id=owner.id)))
    monkeypatch.setattr('app.services.company_permissions.permissions_for',lambda _: {'routes.plan'})
    with pytest.raises(HTTPException) as error:
        require_planning_permission(request,[],db,route['id'])
    assert error.value.status_code==403
