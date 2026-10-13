"""Driver shifts and pauses: real optimizer and isolated persistence."""
import pytest
from test_agents_feature import env
from test_routing_architecture import routing_env,payload
from test_fleet_planning import fleet,preview
from app.optimizer import _evaluate_fixed_sequence
from app.models import Driver,RoutePlan
from app.schemas.driver_schedule import DriverSchedule

def evaluate(start='08:00',travel=20,unload=10,pauses=None,window=None,returning=False):
    stop={'_matrix_index':1,'cliente_nome':'Test','indirizzo':'Test','tempo_scarico_min':unload}
    if window:stop.update(scarico_mattina_da=window[0],scarico_mattina_a=window[1])
    return _evaluate_fixed_sequence([stop],{(0,1):{'km':10,'min':travel},(1,0):{'km':10,'min':travel}},[],
        vehicle={'driver_schedule':{'start':'08:00','end':'17:00','breaks':pauses or [{'start':'08:15','end':'08:45'}]}},start_time=start,return_depot=returning)

def test_break_interrupts_travel_without_changing_distance():
    result=evaluate()
    assert result['ordered'][0]['arrivo_stimato']=='08:50'
    assert result['ordered'][0]['minuti_tappa']==20 and result['total_km']==10
    assert result['total_min']==60 and result['driver_breaks'][0]['after_order']==0

def test_unloading_is_not_split_and_wait_does_not_double_count_pause():
    result=evaluate(travel=10,unload=10)
    assert result['ordered'][0]['arrivo_stimato']=='08:45'
    assert result['ordered'][0]['attesa_min']==35 and result['total_min']==55
    waiting=evaluate(travel=10,window=('09:00','10:00'))
    assert waiting['ordered'][0]['arrivo_stimato']=='09:00' and waiting['total_min']==70
    assert len(waiting['driver_breaks'])==1

def test_return_leg_pause_and_shift_overrun():
    result=evaluate(travel=10,unload=0,returning=True)
    assert result['return_time']=='08:50' and result['driver_breaks'][0]['after_order']==1
    assert evaluate(start='16:50',travel=20)['driver_schedule_error']

@pytest.mark.parametrize('value',[
    {'start':'08:00'},{'start':'18:00','end':'08:00'},
    {'breaks':[{'start':'12:00','end':'11:00'}]},
    {'start':'08:00','end':'17:00','breaks':[{'start':'07:00','end':'08:30'}]},
    {'breaks':[{'start':'12:00','end':'13:00'},{'start':'12:30','end':'14:00'}]}])
def test_invalid_schedule(value):
    with pytest.raises(ValueError):DriverSchedule.model_validate(value)

def test_defaults_snapshot_override_recalculate_and_traffic(routing_env):
    ctx=routing_env;client,db,owner=ctx[:3]
    driver=Driver(user_id=owner.id,nome='Anna',work_schedule={'start':'08:00','end':'17:00','breaks':[{'start':'08:05','end':'08:35'}]})
    db.add(driver);db.commit()
    data=payload(ctx);data['driver_id']=driver.id;data['consegne'][0].update(scarico_mattina_da=None,scarico_mattina_a=None,tempo_scarico_min=10)
    response=client.post('/api/routes/optimize',json=data);assert response.status_code==200,response.text
    saved=response.json();assert saved['driver_breaks'] and saved['consegne'][0]['arrivo_stimato']=='08:40'
    driver.work_schedule={};db.commit()
    reread=client.get('/api/routes/'+str(saved['id'])).json()
    assert reread['driver_schedule']==saved['driver_schedule']
    assert reread['consegne'][0]['arrivo_stimato']=='08:40'
    recalculated=client.post('/api/routes/recalculate-manual',json={**data,'route_id':saved['id']})
    assert recalculated.status_code==200,recalculated.text
    assert recalculated.json()['driver_schedule']==saved['driver_schedule']
    result=client.post(f"/api/routes/{saved['id']}/program",json={})
    assert result.status_code==200,result.text
    assert result.json()['driver_breaks'] and result.json()['consegne'][0]['arrivo_stimato']=='08:50'
    # An explicit empty override removes pauses only for this new route.
    data.update(driver_schedule={'breaks':[]},data_giro='2099-01-16')
    result=client.post('/api/routes/optimize',json=data)
    assert result.status_code==200,result.text
    assert result.json()['driver_breaks']==[]

def test_fleet_inherits_driver_schedule_and_leaves_overlong_jobs_unassigned(fleet):
    ctx,data=fleet;db=ctx[1]
    for driver in db.query(Driver):driver.work_schedule={'start':'08:00','end':'08:40','breaks':[{'start':'08:10','end':'08:30'}]}
    db.commit()
    plan=preview(fleet)
    assert plan['unassigned']
    assert all(r['result']['return_time']<='08:40' for r in plan['routes'])
    assert all(r['driver_schedule']['start']=='08:00' for r in plan['configuration']['resources'])


def test_driver_api_preserves_defaults_on_partial_legacy_update(routing_env):
    from app.routers.vehicles_drivers import drivers_router
    client,db,*_=routing_env;client.app.include_router(drivers_router)
    schedule={'start':'08:00','end':'17:00','breaks':[{'start':'12:00','end':'13:00'}]}
    created=client.post('/api/drivers',json={'nome':'Turnista','work_schedule':schedule})
    assert created.status_code==200,created.text
    id=created.json()['id']
    updated=client.put(f'/api/drivers/{id}',json={'nome':'Nuovo nome'})
    assert updated.status_code==200 and updated.json()['work_schedule']==schedule
    assert client.put(f'/api/drivers/{id}',json={'nome':'Test','work_schedule':{'start':'08:00'}}).status_code==422


def test_shift_limit_and_traffic_overrun_block_programming(routing_env):
    ctx=routing_env;data=payload(ctx);data['consegne'][0].update(scarico_mattina_da=None,scarico_mattina_a=None,tempo_scarico_min=5)
    data['driver_schedule']={'start':'08:00','end':'08:30','breaks':[]}
    first=ctx[0].post('/api/routes/optimize',json=data);assert first.status_code==200,first.text
    response=ctx[0].post(f"/api/routes/{first.json()['id']}/program",json={})
    assert response.status_code==400,response.text
    assert ctx[1].get(RoutePlan,first.json()['id']).status=='bozza'
    data['driver_schedule']['end']='08:10'
    assert ctx[0].post('/api/routes/optimize',json=data).status_code==422


def test_execution_delay_does_not_shift_fixed_pause(routing_env):
    from datetime import datetime
    from app.services.route_schedule import route_schedule_datetimes
    ctx=routing_env;data=payload(ctx);data['consegne'][0].update(scarico_mattina_da=None,scarico_mattina_a=None,tempo_scarico_min=10)
    data['driver_schedule']={'start':'08:00','end':'17:00','breaks':[{'start':'08:15','end':'08:45'}]}
    result=ctx[0].post('/api/routes/optimize',json=data);assert result.status_code==200,result.text
    route=ctx[1].get(RoutePlan,result.json()['id']);route.status='in_corso';route.started_at=datetime(2099,1,15,8,30)
    projected=route_schedule_datetimes(route)
    assert projected['deliveries'][route.deliveries[0].id]['arrival'].strftime('%H:%M')=='08:55'
    assert projected['return_at'].strftime('%H:%M')=='09:15'


def test_additive_upgrade_preserves_legacy_rows_and_is_repeatable(tmp_path):
    from sqlalchemy import create_engine,text,inspect
    from app.migrations import run_migrations,LATEST
    engine=create_engine('sqlite:///'+str(tmp_path/'upgrade.sqlite').replace('\\','/'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)'))
        for version in ('20261004_01','20261004_02','20261004_03','20261006_01','20261009_01','20261009_02','20261010_01','20261010_02','20261011_01','20261011_02','20261013_01'):
            conn.execute(text("INSERT INTO schema_migrations VALUES (:v,CURRENT_TIMESTAMP)"),{'v':version})
        conn.execute(text('CREATE TABLE drivers (id INTEGER PRIMARY KEY,nome TEXT)'))
        conn.execute(text('CREATE TABLE route_plans (id INTEGER PRIMARY KEY,nome TEXT)'))
        conn.execute(text("INSERT INTO drivers VALUES (1,'Autista esistente')"))
        conn.execute(text("INSERT INTO route_plans VALUES (1,'Giro esistente')"))
    run_migrations(engine);run_migrations(engine)
    assert {'driver_schedule','driver_breaks'} <= {c['name'] for c in inspect(engine).get_columns('route_plans')}
    with engine.connect() as conn:
        assert tuple(conn.execute(text('SELECT nome,work_schedule FROM drivers')).one())==('Autista esistente',None)
        assert tuple(conn.execute(text('SELECT nome,driver_schedule,driver_breaks FROM route_plans')).one())==('Giro esistente',None,None)
        assert conn.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'),{'v':LATEST}).scalar()==1
    engine.dispose()


def test_gps_projection_adds_pause_crossed_during_remaining_drive():
    from datetime import datetime,date,timezone
    from types import SimpleNamespace as N
    from app.services.route_schedule import _apply_gps,LOCAL
    now=datetime(2099,1,15,8,0,tzinfo=LOCAL)
    utc=now.astimezone(timezone.utc).replace(tzinfo=None)
    delivery=N(id=1,ordine=1,tempo_scarico_min=10,scarico_mattina_da=None,scarico_mattina_a=None,scarico_pomeriggio_da=None,scarico_pomeriggio_a=None)
    from datetime import timedelta
    position=N(driver_id=1,eta_at=utc+timedelta(minutes=20),captured_at=utc,eta_calculated_at=utc,eta_delivery_id=1)
    plan=N(status='in_corso',position=position,driver_id=1,deliveries=[delivery],data_giro=date(2099,1,15),rientro_deposito=False,
           driver_schedule={'breaks':[{'start':'08:05','end':'08:15'}]})
    result={'deliveries':{1:{'arrival':now+timedelta(minutes=20)}},'return_at':now+timedelta(minutes=30)}
    _apply_gps(plan,{},result,now)
    assert result['deliveries'][1]['arrival'].strftime('%H:%M')=='08:30'
    assert result['return_at'].strftime('%H:%M')=='08:40'
