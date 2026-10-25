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
          'strategy':'balanced','resources':[{'vehicle_id':v.id,'driver_id':d.id} for v,d in zip([vehicle,second],drivers)],
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
    # Nome automatico: base del piano · autista di ogni giro (non più "· 1", "· 2").
    assert sorted(r.nome for r in fleet[0][1].query(RoutePlan))==['Consegne · Anna','Consegne · Luca']
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
    assert 'Giro 1:' in plan['unassigned'][0]['reason']
    assert 'Giro 2:' in plan['unassigned'][0]['reason']
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

def test_traffic_failure_releases_batch_for_replanning(fleet):
    data=deepcopy(fleet[1]);data['consegne']=data['consegne'][:2]
    # Turno brevissimo: il traffico aggiornato al momento di programmare lo supera.
    for resource in data['resources']:resource['driver_schedule']={'start':'08:00','end':'08:30'}
    plan=preview(fleet,data)
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    result=command(fleet,saved.json(),'program')
    assert result.status_code==422 and 'turno' in result.json()['detail'],result.text
    assert all(r.status=='annullato' for r in fleet[0][1].query(RoutePlan))
    restored=fleet[0][0].get(f"/api/fleet-planning/{plan['id']}").json()
    assert restored['status']=='preview' and restored['route_ids']==[]


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
    assert any(0 in route['stop_indexes'] for route in plan['routes'])
    assert any('sponda' in warning for warning in plan['warnings'])
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
    # La durata massima del giro non esiste più: i piani salvati che la contengono restano validi.
    data=deepcopy(fleet[1]);data['resources'][0]['max_minutes']=1200
    plan=preview(fleet,data)
    assert all('max_minutes' not in r for r in plan['configuration']['resources'])


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
    assert 'Fasce orarie' in next(s['reason'] for s in plan['unassigned'] if s['index']==0)
    assert all(0 not in r['stop_indexes'] for r in plan['routes'])


@pytest.mark.parametrize('strategy',['efficient','balanced'])
def test_tail_lift_prefers_equipped_vehicle(fleet,strategy):
    ctx, original = fleet
    data=deepcopy(original);data['consegne']=data['consegne'][:2];data['strategy']=strategy
    ctx[2].needs_tail_lift=True
    for vehicle in ctx[1].query(Vehicle): vehicle.ha_sponda=False
    ctx[1].get(Vehicle,data['resources'][1]['vehicle_id']).ha_sponda=True
    ctx[1].commit()
    data['consegne'][0]['sponda']=True
    plan=preview(fleet,data)
    assert plan['unassigned']==[]
    assert next(r['resource'] for r in plan['routes'] if 0 in r['stop_indexes'])==1
    assert [r['has_tail_lift'] for r in plan['resource_capabilities']]==[False,True]
    assert not any('ma il mezzo' in w for w in plan['warnings'])
    # Manual membership remains valid even when the operator chooses the other vehicle.
    moved=command(fleet,plan,'revise',assignments=[0,0])
    assert moved.status_code==200,moved.text
    assert any('richiede la sponda' in w for w in moved.json()['warnings'])


@pytest.mark.parametrize('equipped_but_full',[False,True])
def test_tail_lift_fallback_warns_and_programs_without_excluding(fleet,equipped_but_full):
    ctx, original=fleet
    data=deepcopy(original);data['consegne']=data['consegne'][:2]
    ctx[2].needs_tail_lift=True
    for vehicle in ctx[1].query(Vehicle): vehicle.ha_sponda=False
    if equipped_but_full:
        vehicle=ctx[1].get(Vehicle,data['resources'][1]['vehicle_id'])
        vehicle.ha_sponda=True;vehicle.capacita_kg=5
    ctx[1].commit()
    data['consegne'][0]['sponda']=True
    plan=preview(fleet,data)
    assert plan['unassigned']==[]
    assert any('richiede la sponda, ma il mezzo non la possiede' in w for w in plan['warnings'])
    saved=command(fleet,plan,'confirm')
    assert saved.status_code==200,saved.text
    programmed=command(fleet,saved.json(),'program')
    assert programmed.status_code==200,programmed.text
    assert any('richiede la sponda' in w for w in programmed.json()['warnings'])
    routes=ctx[1].query(RoutePlan).all()
    assert sum(len(r.deliveries) for r in routes)==2
    assert any(d.sponda and 'sponda' in (d.warning or '').lower() for r in routes for d in r.deliveries)


@pytest.mark.parametrize('strategy',['efficient','balanced'])
def test_ztl_prefers_authorized_vehicle_and_allows_manual_override(fleet,strategy):
    ctx, original=fleet
    data=deepcopy(original);data['consegne']=data['consegne'][:2];data['strategy']=strategy
    ctx[2].has_ztl=True
    for vehicle in ctx[1].query(Vehicle): vehicle.accesso_ztl=False
    ctx[1].get(Vehicle,data['resources'][1]['vehicle_id']).accesso_ztl=True
    ctx[1].commit()
    data['consegne'][0]['ztl']=True
    plan=preview(fleet,data)
    assert plan['unassigned']==[]
    assert next(r['resource'] for r in plan['routes'] if 0 in r['stop_indexes'])==1
    assert [r['has_ztl_access'] for r in plan['resource_capabilities']]==[False,True]
    moved=command(fleet,plan,'revise',assignments=[0,0])
    assert moved.status_code==200,moved.text
    assert any('in ZTL, ma il mezzo non è abilitato' in w for w in moved.json()['warnings'])


@pytest.mark.parametrize('authorized_but_full',[False,True])
def test_ztl_fallback_warns_and_programs_without_excluding(fleet,authorized_but_full):
    ctx, original=fleet
    data=deepcopy(original);data['consegne']=data['consegne'][:2]
    ctx[2].has_ztl=True
    for vehicle in ctx[1].query(Vehicle): vehicle.accesso_ztl=False
    if authorized_but_full:
        vehicle=ctx[1].get(Vehicle,data['resources'][1]['vehicle_id'])
        vehicle.accesso_ztl=True;vehicle.capacita_kg=5
    ctx[1].commit()
    data['consegne'][0]['ztl']=True
    plan=preview(fleet,data)
    assert plan['unassigned']==[]
    assert any('in ZTL, ma il mezzo non è abilitato' in w for w in plan['warnings'])
    saved=command(fleet,plan,'confirm')
    assert saved.status_code==200,saved.text
    programmed=command(fleet,saved.json(),'program')
    assert programmed.status_code==200,programmed.text
    assert any('in ZTL' in w for w in programmed.json()['warnings'])
    routes=ctx[1].query(RoutePlan).all()
    assert sum(len(r.deliveries) for r in routes)==2
    assert any(d.ztl and 'ztl' in (d.warning or '').lower() for r in routes for d in r.deliveries)


def test_tail_lift_and_ztl_prefer_vehicle_meeting_both_requirements(fleet):
    ctx, original=fleet
    data=deepcopy(original);data['consegne']=data['consegne'][:2]
    ctx[2].has_ztl=True;ctx[2].needs_tail_lift=True
    for vehicle in ctx[1].query(Vehicle):
        vehicle.ha_sponda=True;vehicle.accesso_ztl=False
    ctx[1].get(Vehicle,data['resources'][1]['vehicle_id']).accesso_ztl=True
    ctx[1].commit()
    data['consegne'][0].update(ztl=True,sponda=True)
    plan=preview(fleet,data)
    assert plan['unassigned']==[]
    assert next(r['resource'] for r in plan['routes'] if 0 in r['stop_indexes'])==1


@pytest.mark.parametrize('endpoint',['preview','confirm','program'])
def test_past_departure_rejected_before_any_reservation(fleet,monkeypatch,endpoint):
    from datetime import datetime
    from app.services import fleet_planning as service
    ctx,data=fleet
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,7,59))
    plan=preview(fleet)
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,8,1))
    response=ctx[0].post('/api/fleet-planning/preview',json=data) if endpoint=='preview' else command(fleet,plan,endpoint)
    assert response.status_code==400,response.text
    assert 'già passato' in response.json()['detail']
    assert ctx[1].query(RoutePlan).count()==0


def order_batch(fleet):
    from app.routers import orders,order_planning
    from test_order_planning import ready
    ctx,original=fleet;client=ctx[0]
    client.app.include_router(orders.router);client.app.include_router(order_planning.router)
    orders=[ready(ctx,f'FAIL-{i}',weight_kg=100,packages=2) for i in range(2)]
    selected=client.put('/api/order-planning/selection',json={'version':0,'action':'add','order_ids':[r.id for r in orders]}).json()
    configuration={k:original[k] for k in ('nome','data_giro','orario_partenza','deposit_id')}
    configuration.update(planning_mode='fleet',fleet_resources=original['resources'],fleet_strategy='balanced')
    stops=client.post('/api/order-planning/preview',json={'version':selected['version'],'configuration':configuration})
    assert stops.status_code==200,stops.text
    data=deepcopy(original);data['consegne']=stops.json()['stops']
    return data,orders


@pytest.mark.parametrize('failure',['provider','departure_elapsed'])
def test_failed_programming_releases_orders_and_can_retry(fleet,monkeypatch,failure):
    from datetime import datetime
    from fastapi import HTTPException
    from app.services import fleet_planning as service,route_enrichment
    from app.order_models import RouteOrderAssignment
    ctx,_=fleet;client,db=ctx[:2]
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,7,59))
    data,orders=order_batch(fleet)
    plan=preview(fleet,data)
    original=route_enrichment.enrich_final_route
    def fail_after_enrichment(*args,**kwargs):
        original(*args,**kwargs)
        if failure=='provider':raise HTTPException(503,'Provider non disponibile')
        monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,8,1))
    monkeypatch.setattr(route_enrichment,'enrich_final_route',fail_after_enrichment)
    result=command(fleet,plan,'program')
    assert result.status_code==(503 if failure=='provider' else 400),result.text
    assert db.query(RouteOrderAssignment).count()==0
    assert all(o.status=='pronto' and o.delivery_status=='not_assigned' for o in orders)
    assert all(r.status=='annullato' for r in db.query(RoutePlan))
    restored=client.get(f"/api/fleet-planning/{plan['id']}").json()
    assert restored['status']=='preview' and restored['route_ids']==[]
    selection=client.get('/api/order-planning/selection').json()
    versions={o.id:o.version for o in orders}
    assert all(ref['version']==versions[ref['id']] for stop in selection['stops'] for ref in stop['order_refs'])
    # Both the existing preview and the ordinary order selection remain reusable.
    monkeypatch.setattr(route_enrichment,'enrich_final_route',original)
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,7,59))
    retry=command(fleet,restored,'program')
    assert retry.status_code==200,retry.text
    assert db.query(RouteOrderAssignment).count()==2
    assert all(o.status=='assegnato' and o.delivery_status=='scheduled' for o in orders)
    assert db.query(RoutePlan).filter_by(status='programmato').count()==2


def test_past_departure_releases_preexisting_unmodified_drafts(fleet,monkeypatch):
    from datetime import datetime
    from app.services import fleet_planning as service
    from app.order_models import RouteOrderAssignment
    ctx,_=fleet
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,7,59))
    data,orders=order_batch(fleet)
    plan=preview(fleet,data)
    saved=command(fleet,plan,'confirm').json()
    assert ctx[1].query(RouteOrderAssignment).count()==2
    monkeypatch.setattr(service,'local_now',lambda:datetime(2099,1,15,8,1))
    result=command(fleet,saved,'program')
    assert result.status_code==400,result.text
    assert ctx[1].query(RouteOrderAssignment).count()==0
    assert all(o.status=='pronto' for o in orders)


def test_manual_revision_preserves_selected_vehicle_membership(fleet):
    data=deepcopy(fleet[1]);data['consegne']=data['consegne'][:6];data['strategy']='efficient'
    plan=preview(fleet,data)
    assert len(plan['routes'])==1
    revised=command(fleet,plan,'revise',assignments=[0,0,0,1,1,1])
    assert revised.status_code==200,revised.text
    routes={route['resource']:set(route['stop_indexes']) for route in revised.json()['routes']}
    assert routes=={0:{0,1,2},1:{3,4,5}}
    assert revised.json()['unassigned']==[]


def test_traffic_window_message_names_customer_driver_and_delay():
    import json
    from types import SimpleNamespace as NS
    from app.services.fleet_planning import traffic_window_problems
    late={'time_window_violation':{'window':{'start':'07:00','end':'10:00'},'fine_servizio':'10:22','lateness_min':22.48}}
    row=NS(driver=NS(nome='Anna',cognome='Neri'),deliveries=[
        NS(ordine=2,cliente_nome='Bar Luna',optimizer_details=json.dumps(late)),
        NS(ordine=1,cliente_nome='Puntuale',optimizer_details='{}')])
    assert traffic_window_problems([row])==['Bar Luna (giro di Anna Neri): scarico fino alle 10:22, fascia 07:00–10:00, 22 min oltre']


def mapbox_calls(fleet):
    return sum('api.mapbox.com' in url for url,_ in fleet[0][-1])


def test_preview_traffic_is_reused_when_programming(fleet):
    plan=preview(fleet)
    assert plan['routes'] and all(r['traffic']['status']=='updated' for r in plan['routes'])
    # Le tratte restano sul server: l'anteprima inviata al browser non le contiene.
    assert all(r['traffic']['legs'] is None for r in plan['routes'])
    assert 'Tempi con traffico aggiornato' in plan['warnings'][0]
    before=mapbox_calls(fleet)
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    result=command(fleet,saved.json(),'program');assert result.status_code==200,result.text
    assert mapbox_calls(fleet)==before
    assert all(r.traffic_status=='updated' for r in fleet[0][1].query(RoutePlan))


def test_stale_preview_traffic_is_recalculated_when_programming(fleet):
    from datetime import timedelta
    from app.core.clock import utc_now
    from app.fleet_models import FleetPlan
    plan=preview(fleet)
    row=fleet[0][1].get(FleetPlan,plan['id']);result=deepcopy(row.result)
    for route in result['routes']:
        route['traffic']['calculated_at']=(utc_now()-timedelta(hours=2)).isoformat()+'+00:00'
    row.result=result;fleet[0][1].commit()
    before=mapbox_calls(fleet)
    saved=command(fleet,plan,'confirm');assert saved.status_code==200,saved.text
    assert command(fleet,saved.json(),'program').status_code==200
    assert mapbox_calls(fleet)>before


def test_traffic_margin_lengthens_times_on_a_copy():
    from app.services.fleet_planning import apply_traffic_margin
    from app.services.road_routing import RoadMatrix
    matrix=RoadMatrix({(0,1):{'km':10,'min':20}},source='osrm')
    longer=apply_traffic_margin(matrix,1.15)
    assert longer[(0,1)]=={'km':10,'min':pytest.approx(23)} and longer.source=='osrm'
    assert matrix[(0,1)]['min']==20 and apply_traffic_margin(matrix,1) is matrix
