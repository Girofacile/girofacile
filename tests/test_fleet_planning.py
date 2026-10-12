"""Fleet lifecycle on an isolated database; all road/traffic calls mocked."""
from copy import deepcopy
import pytest
from test_agents_feature import env
from test_routing_architecture import routing_env
from stop_fixture import verified_stop
from app.models import Driver, Vehicle, RoutePlan

@pytest.fixture
def fleet(routing_env):
    from app.routers.fleet_planning import router
    ctx=routing_env
    client,db,owner,_,_,depot,vehicle,_=ctx
    client.app.include_router(router)
    second=Vehicle(user_id=owner.id,nome='Second',capacita_kg=150,capacita_colli=15)
    drivers=[Driver(user_id=owner.id,nome='Anna'),Driver(user_id=owner.id,nome='Luca')]
    vehicle.capacita_kg=150;vehicle.capacita_colli=15
    db.add_all([second,*drivers]);db.commit()
    data={'nome':'Consegne','data_giro':'2099-01-15','orario_partenza':'08:00','deposit_id':depot.id,
          'strategy':'balanced','resources':[{'vehicle_id':v.id,'driver_id':d.id,'max_minutes':480} for v,d in zip([vehicle,second],drivers)],
          'consegne':[verified_stop(owner.id,cliente_nome=f'Cliente {i}',indirizzo=f'Via {i}',lat=45.1+i*.001,lon=9.1,peso_kg=10,colli=1,tempo_scarico_min=5) for i in range(30)]}
    return ctx,data

def preview(fleet,data=None):
    response=fleet[0][0].post('/api/fleet-planning/preview',json=data or fleet[1])
    assert response.status_code==200,response.text
    return response.json()

def command(fleet,plan,name,**kwargs):
    return fleet[0][0].post(f"/api/fleet-planning/{plan['id']}/{name}",json={'version':plan['version'],**kwargs})

def test_thirty_deliveries_preview_revise_confirm_idempotent(fleet):
    plan=preview(fleet)
    assert [len(r['stop_indexes']) for r in plan['routes']]==[15,15]
    assert plan['unassigned']==[] and fleet[0][1].query(RoutePlan).count()==0
    assignments=[None]*30
    for r in plan['routes']:
        for i in r['stop_indexes']:assignments[i]=r['resource']
    a,b=plan['routes'][0]['stop_indexes'][0],plan['routes'][1]['stop_indexes'][0]
    assignments[a],assignments[b]=assignments[b],assignments[a]
    revised=command(fleet,plan,'revise',assignments=assignments)
    assert revised.status_code==200,revised.text
    assert command(fleet,plan,'confirm').status_code==409
    plan=revised.json()
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    assert len(saved.json()['route_ids'])==2
    assert command(fleet,plan,'confirm').json()['route_ids']==saved.json()['route_ids']
    assert fleet[0][1].query(RoutePlan).count()==2
    programmed=command(fleet,saved.json(),'program');assert programmed.status_code==200,programmed.text
    assert all(r.status=='programmato' for r in fleet[0][1].query(RoutePlan))
    assert command(fleet,saved.json(),'program').status_code==200

@pytest.mark.parametrize('strategy,expected',[('efficient',1),('balanced',2)])
def test_operator_strategy(fleet,strategy,expected):
    data=deepcopy(fleet[1]);data['consegne']=data['consegne'][:6];data['strategy']=strategy
    assert len(preview(fleet,data)['routes'])==expected

def test_unassigned_and_invalid_manual_move(fleet):
    data=deepcopy(fleet[1]);data['consegne'][0]['peso_kg']=1000
    plan=preview(fleet,data)
    assert plan['unassigned'][0]['index']==0
    assert command(fleet,plan,'confirm').status_code==422
    invalid=command(fleet,plan,'revise',assignments=[0]*30)
    assert invalid.status_code==422
    saved=command(fleet,plan,'confirm',accept_unassigned=True)
    assert saved.status_code==200,saved.text
    assert sum(len(r.deliveries) for r in fleet[0][1].query(RoutePlan))==29

def test_tenant_and_duplicate_resources(fleet):
    data=deepcopy(fleet[1]);data['resources'][1]['driver_id']=data['resources'][0]['driver_id']
    assert fleet[0][0].post('/api/fleet-planning/preview',json=data).status_code==422
    plan=preview(fleet)
    from app.core.dependencies import current_user
    fleet[0][0].app.dependency_overrides[current_user]=lambda:fleet[0][3]
    assert fleet[0][0].get(f"/api/fleet-planning/{plan['id']}").status_code==404
    assert fleet[0][0].post('/api/fleet-planning/preview',json=fleet[1]).status_code==400

def test_atomic_confirmation_rollback(fleet,monkeypatch):
    from app.routers import routes
    plan=preview(fleet);original=routes.save_route_result;calls=[]
    def fail_second(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise ValueError('Second route failed')
        return original(*args,**kwargs)
    monkeypatch.setattr(routes,'save_route_result',fail_second)
    assert command(fleet,plan,'confirm').status_code==422
    assert fleet[0][1].query(RoutePlan).count()==0

def test_traffic_failure_keeps_all_drafts(fleet):
    data=deepcopy(fleet[1]);data['consegne']=data['consegne'][:2]
    for resource in data['resources']:resource['max_minutes']=30
    plan=preview(fleet,data)
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    result=command(fleet,saved.json(),'program')
    assert result.status_code==409,result.text
    assert all(r.status=='bozza' for r in fleet[0][1].query(RoutePlan))


def test_road_windows_equipment_and_remaining_availability(fleet):
    from datetime import date,time
    ctx,data=fleet;db=ctx[1]
    data=deepcopy(data);data['consegne']=data['consegne'][:4]
    # Preferences explicitly enable customer constraints for the fleet just as for a single route.
    ctx[2].has_time_windows=True;ctx[2].needs_tail_lift=True
    for vehicle in db.query(Vehicle): vehicle.ha_sponda=False
    data['consegne'][0]['sponda']=True
    # The second resource has a booking at 08:40: only 40 minutes remain.
    r=data['resources'][1]
    booking=RoutePlan(user_id=ctx[2].id,nome='Impegno',data_giro=date(2099,1,15),orario_partenza=time(8,40),
                      driver_id=r['driver_id'],vehicle_id=r['vehicle_id'],totale_minuti=60,status='programmato')
    db.add(booking);db.commit()
    plan=preview(fleet,data)
    assert any(stop['index']==0 for stop in plan['unassigned'])
    assert all(route['result']['total_min']<=40 for route in plan['routes'] if route['resource']==1)
    # A booking later in the morning does not hide a resource available at departure.
    available=ctx[0].get('/api/resources/availability?data_giro=2099-01-15&orario=08:00&preview_minutes=1').json()
    assert all(row['available'] for row in available['vehicles'])


def test_changed_depot_blocks_confirmation(fleet):
    plan=preview(fleet)
    fleet[0][5].lat=46;fleet[0][1].commit()
    assert command(fleet,plan,'confirm').status_code==409
    assert fleet[0][1].query(RoutePlan).count()==0


def test_invalid_windows_and_resource_duration(fleet):
    for update in ({'scarico_mattina_da':'09:00'},{'scarico_mattina_da':'11:00','scarico_mattina_a':'09:00'}):
        data=deepcopy(fleet[1]);data['consegne'][0].update(update)
        assert fleet[0][0].post('/api/fleet-planning/preview',json=data).status_code==422
    data=deepcopy(fleet[1]);data['resources'][0]['max_minutes']=1200
    assert fleet[0][0].post('/api/fleet-planning/preview',json=data).status_code==422


def test_saved_batch_rejects_individual_edits(fleet):
    plan=command(fleet,preview(fleet),'confirm').json()
    row=fleet[0][1].get(RoutePlan,plan['route_ids'][0]);row.orario_partenza=__import__('datetime').time(9)
    fleet[0][1].commit()
    assert command(fleet,plan,'program').status_code==409
    assert all(r.status=='bozza' for r in fleet[0][1].query(RoutePlan))


def test_cold_migration_repeat_and_postgres_ddl(tmp_path):
    import os,subprocess,sys
    from sqlalchemy import create_engine,text,inspect
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects.postgresql import dialect
    from app.fleet_models import FleetPlan
    assert 'user_id INTEGER' in str(CreateTable(FleetPlan.__table__).compile(dialect=dialect()))
    url='sqlite:///'+str(tmp_path/'migration.sqlite').replace('\\','/')
    environment=dict(os.environ,DATABASE_URL=url,ALLOW_SQLITE_LEGACY='true')
    for _ in range(2):
        result=subprocess.run([sys.executable,'-m','app.migrations'],env=environment,capture_output=True,timeout=90)
        assert result.returncode==0,result.stderr.decode(errors='replace')
    engine=create_engine(url)
    assert 'fleet_plans' in inspect(engine).get_table_names()
    with engine.connect() as connection:
        markers=set(connection.execute(text('SELECT version FROM schema_migrations')).scalars())
        assert {'20261011_02','20261013_01'}<=markers
    engine.dispose()


def test_imported_orders_split_reserve_and_schedule(fleet):
    from app.routers import orders,order_planning
    from test_order_planning import ready
    from app.order_models import RouteOrderAssignment
    ctx,data=fleet;client,db=ctx[:2]
    client.app.include_router(orders.router);client.app.include_router(order_planning.router)
    rows=[ready(ctx,str(i),weight_kg=100,packages=2) for i in range(2)]
    selected=client.put('/api/order-planning/selection',json={'version':0,'action':'add','order_ids':[r.id for r in rows]}).json()
    configuration={k:data[k] for k in ('nome','data_giro','orario_partenza','deposit_id')}
    configuration.update(planning_mode='fleet',fleet_resources=data['resources'],fleet_strategy='balanced')
    response=client.post('/api/order-planning/preview',json={'version':selected['version'],'configuration':configuration})
    assert response.status_code==200,response.text
    data=deepcopy(data);data['consegne']=response.json()['stops']
    plan=preview(fleet,data)
    assert len(plan['routes'])==2
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    assert db.query(RouteOrderAssignment).count()==2
    assert all(r.status=='assegnato' and r.delivery_status=='draft' for r in rows)
    assert client.post('/api/fleet-planning/preview',json=data).status_code==409
    result=command(fleet,saved.json(),'program');assert result.status_code==200,result.text
    assert all(r.delivery_status=='scheduled' for r in rows)


def test_notification_only_after_successful_commit_once(fleet,monkeypatch):
    from app.models import RouteToken
    calls=[]
    def notify(**kwargs):
        assert all(r.status=='programmato' for r in fleet[0][1].query(RoutePlan))
        calls.append(kwargs);return True
    monkeypatch.setattr('app.services.email.send_driver_route_assigned',notify)
    for row in fleet[0][1].query(Driver):row.email=f'driver{row.id}@example.test'
    fleet[0][1].commit()
    plan=command(fleet,preview(fleet),'confirm').json()
    assert command(fleet,plan,'program').status_code==200
    assert command(fleet,plan,'program').status_code==200
    assert len(calls)==2 and fleet[0][1].query(RouteToken).count()==2


from test_company_collaborators import company

def test_collaborator_permissions_and_private_previews(company):
    from app.routers.fleet_planning import router
    from app.fleet_models import FleetPlan
    client,db,owner,_,actor,_,_,login_owner,login_actor=company
    client.app.include_router(router)
    plan=FleetPlan(user_id=owner.id,actor=f'owner:{owner.id}',configuration={'consegne':[]},result={'routes':[],'unassigned':[],'warnings':[]},route_ids=[])
    db.add(plan);db.commit()
    login_actor(['routes.read'])
    assert client.get(f'/api/fleet-planning/{plan.id}').status_code==403
    login_actor(['routes.plan'])
    assert client.get(f'/api/fleet-planning/{plan.id}').status_code==404
    assert client.post(f'/api/fleet-planning/{plan.id}/program',json={'version':1}).status_code==403
    login_owner()
    assert client.get(f'/api/fleet-planning/{plan.id}').status_code==200


def test_changed_assignment_cannot_double_book_batch(fleet):
    plan=command(fleet,preview(fleet),'confirm').json()
    db=fleet[0][1];first,second=[db.get(RoutePlan,i) for i in plan['route_ids']]
    second.driver_id=first.driver_id;second.vehicle_id=first.vehicle_id;db.commit()
    assert command(fleet,plan,'program').status_code==409
    assert first.status==second.status=='bozza'


def test_impossible_window_remains_unassigned(fleet):
    data=deepcopy(fleet[1]);data['consegne']=data['consegne'][:2]
    fleet[0][2].has_time_windows=True;fleet[0][1].commit()
    data['consegne'][0].update(scarico_mattina_da='07:00',scarico_mattina_a='07:30')
    plan=preview(fleet,data)
    assert any(s['index']==0 for s in plan['unassigned'])
    assert all(0 not in r['stop_indexes'] for r in plan['routes'])
