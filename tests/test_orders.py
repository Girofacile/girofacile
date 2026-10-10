"""Orders use isolated databases and stub geocoding, never live addresses."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def orders(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('ALLOW_SQLITE_LEGACY', 'true')
    from app.database import Base, get_db
    from app.models import User
    from app.routers.orders import router
    from app.core.dependencies import current_user
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    event.listen(engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner=User(username='orders-owner',password_hash='test',plan_status='active')
        other=User(username='orders-other',password_hash='test',plan_status='active')
        db.add_all([owner,other]);db.commit()
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:db
        app.dependency_overrides[current_user]=lambda:owner
        with TestClient(app) as client: yield client,db,owner,other
    engine.dispose()


def create(client, **values):
    result=client.post('/api/orders',json={'number':'O-1','recipient_name':'Destinatario','delivery_address':'Via Test 10, Roma',**values})
    assert result.status_code==201,result.text
    return result.json()


def test_create_update_original_history_and_missing_false(orders):
    client,db,owner,other=orders
    row=create(client,tail_lift=False,items=[{'description':'Articolo','quantity':2}])
    assert row['customer_id'] is None
    assert row['operational_data']['tail_lift'] is False
    assert row['operational_data']['pallet_truck'] is None
    assert row['items'][0]['quantity']==2
    correction={**row['operational_data'],'version':row['version'],'delivery_address':'Via Nuova 5','packages':4}
    result=client.put('/api/orders/'+str(row['id']),json=correction)
    assert result.status_code==200,result.text
    saved=result.json()
    assert saved['original_payload']['delivery_address']=='Via Test 10, Roma'
    assert saved['delivery_address']=='Via Nuova 5'
    assert saved['status']=='da_verificare'
    assert saved['events'][0]['changes']['packages']=={'before':None,'after':4}
    assert client.put('/api/orders/'+str(row['id']),json=correction).status_code==409
    from app.models import Customer
    assert db.query(Customer).count()==0


def test_tenant_isolation_and_untrusted_properties(orders):
    client,db,owner,other=orders
    row=create(client)
    from app.core.dependencies import current_user
    client.app.dependency_overrides[current_user]=lambda:other
    assert client.get('/api/orders').json()['total']==0
    assert client.get('/api/orders/'+str(row['id'])).status_code==404
    assert client.put('/api/orders/'+str(row['id']),json={**row['operational_data'],'version':1}).status_code==404
    assert client.post('/api/orders/'+str(row['id'])+'/status',json={'version':1,'status':'annullato'}).status_code==404
    for key,value in [('user_id',owner.id),('source_id',row['source_id']),('status','consegnato'),('customer_id',1),('original_payload',{})]:
        assert client.post('/api/orders',json={'number':'Invalid',key:value}).status_code==422


def test_pagination_filters_sort_and_metrics(orders):
    client,*_=orders
    for n in range(5):create(client,number=f'O-{n}',requested_date=f'2026-10-{10+n}')
    result=client.get('/api/orders?page_size=2&page=2&sort=number&direction=asc').json()
    assert result['total']==5 and [x['number'] for x in result['items']]==['O-2','O-3']
    assert result['metrics']['nuovo']==5
    assert client.get('/api/orders?date_from=2026-10-12&date_to=2026-10-13').json()['total']==2
    assert client.get('/api/orders?q=O-4').json()['total']==1
    assert client.get('/api/orders?q=%25').json()['total']==0
    for query in ['page=0','page_size=1000','sort=user_id','status=bad','date_from=2026-11-01&date_to=2026-10-01']:
        assert client.get('/api/orders?'+query).status_code==422


def test_verification_transitions_and_address_invalidation(orders,monkeypatch):
    client,*_=orders
    row=create(client)
    url='/api/orders/'+str(row['id'])
    assert client.post(url+'/status',json={'version':1,'status':'pronto'}).status_code==422
    monkeypatch.setattr('app.services.orders.verify_stop_address',lambda db,uid,address:{'stato_geocodifica':'verificato','lat':41.9,'lon':12.5,'indirizzo':address,'geocoding_token':'test'})
    verified=client.post(url+'/verify-address',json={'version':1})
    assert verified.status_code==200,verified.text
    ready=client.post(url+'/status',json={'version':2,'status':'pronto'})
    assert ready.status_code==200,ready.text
    assert ready.json()['verification_status']=='verified'
    changed=client.put(url,json={**row['operational_data'],'version':3,'delivery_address':'Indirizzo differente'}).json()
    assert changed['address_verification'] is None and changed['status']=='da_verificare'
    assert client.post(url+'/status',json={'version':4,'status':'consegnato'}).status_code==422
    assert client.post(url+'/status',json={'version':4,'status':'annullato'}).status_code==200
    assert client.put(url,json={**row['operational_data'],'version':5}).status_code==409
    assert client.get(url).json()['original_payload']==row['original_payload']


def test_assigned_order_cannot_be_edited(orders):
    from app.order_models import Order
    client,db,*_=orders
    row=create(client)
    order=db.get(Order,row['id']);order.status='assegnato';db.commit()
    assert client.put('/api/orders/'+str(row['id']),json={**row['operational_data'],'version':1}).status_code==409


@pytest.mark.parametrize('values',[{'number':'  '},{'weight_kg':-1},{'packages':1.5},{'time_from':'14:00'},{'time_from':'14:00','time_to':'10:00'},{'items':[{'description':'A','quantity':-1}]}])
def test_invalid_data_is_atomic(orders,values):
    client,*_=orders
    assert client.post('/api/orders',json={'number':'Test',**values}).status_code==422
    assert client.get('/api/orders').json()['total']==0


def test_external_uniqueness_is_scoped_to_company_and_source(orders):
    from app.order_models import Order,OrderSource
    from sqlalchemy.exc import IntegrityError
    client,db,owner,other=orders
    original=create(client)
    source=OrderSource(user_id=other.id,key='manual',name='Other',kind='manual');db.add(source);db.flush()
    def row(uid,sid):return Order(user_id=uid,source_id=sid,external_id=original['external_id'],number='X',original_payload={},operational_data={})
    db.add(row(other.id,source.id));db.commit()
    with pytest.raises(IntegrityError):
        db.add(row(owner.id,original['source_id']));db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.add(row(owner.id,source.id));db.commit()
    db.rollback()
