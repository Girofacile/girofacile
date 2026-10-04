import io
from datetime import date

import pytest
from fastapi import HTTPException

from app.models import Customer, Delivery, DeliveryStatus, RoutePlan, Driver, DriverAccount, RouteUsage
from app.services import occasional_stops
from test_agents_feature import env
from test_routing_architecture import routing_env, payload
from test_delivery_pod import storage, image_data
from stop_fixture import verified_stop


def test_google_verification_returns_attestation_without_creating_customer(routing_env, monkeypatch):
    client, db, owner, *_ = routing_env
    calls = []
    def google(address, **kwargs):
        calls.append((address, kwargs['user_id']))
        return dict(status='verificato', lat=40.85, lon=14.27, formatted='Via Roma 18, Napoli')
    monkeypatch.setattr(occasional_stops, 'geocode_address', google)
    before = db.query(Customer).count()
    response = client.post('/api/routes/verify-stop-address', json={'indirizzo':'Via Roma 18 Napoli'})
    assert response.status_code == 200
    stop = dict(response.json(), customer_id=None, cliente_nome='Cantiere')
    occasional_stops.validate_occasional_stops(owner.id, [stop])
    data = payload(routing_env)
    data['consegne'] = [stop]
    route = client.post('/api/routes/optimize', json=data)
    assert route.status_code == 200, route.text
    saved = client.get(f"/api/routes/{route.json()['id']}").json()
    data.update(route_id=saved['id'], consegne=saved['consegne'])
    assert client.post('/api/routes/recalculate-manual', json=data).status_code == 200
    assert calls == [('Via Roma 18 Napoli', owner.id)]
    assert db.query(Customer).count() == before
    assert db.query(Delivery).one().customer_id is None


@pytest.mark.parametrize('result', [dict(status='non_trovato'), dict(status='da_verificare',lat=40,lon=14),
                                    dict(status='verificato',lat=None,lon=14)])
def test_unverified_google_results_rejected(routing_env, monkeypatch, result):
    monkeypatch.setattr(occasional_stops, 'geocode_address', lambda *a, **kw: result)
    assert routing_env[0].post('/api/routes/verify-stop-address',json={'indirizzo':'Via Roma'}).status_code == 400


@pytest.mark.parametrize('endpoint', ['optimize','recalculate-manual'])
@pytest.mark.parametrize('change', [dict(geocoding_token=None),dict(geocoding_token='fake'),
    dict(indirizzo='Altro indirizzo'),dict(lat=45),dict(lat=None),dict(lon=None),
    dict(stato_geocodifica='da_verificare'),dict(cliente_nome=' ')])
def test_bypass_and_changed_address_rejected_before_routing(routing_env, endpoint, change):
    data = payload(routing_env)
    data['consegne'] = [dict(verified_stop(routing_env[2].id), **change)]
    response = routing_env[0].post('/api/routes/'+endpoint,json=data)
    assert response.status_code == 400, response.text
    assert not routing_env[-1]
    assert routing_env[1].query(RoutePlan).count() == 0


def test_attestation_cannot_cross_tenant_or_override_registry(routing_env):
    data = payload(routing_env)
    data['consegne'] = [verified_stop(routing_env[3].id)]
    assert routing_env[0].post('/api/routes/optimize',json=data).status_code == 400
    customer = routing_env[4]
    customer.stato_geocodifica='da_verificare'
    routing_env[1].commit()
    data['consegne'] = [verified_stop(routing_env[2].id, customer_id=customer.id)]
    response = routing_env[0].post('/api/routes/optimize',json=data)
    assert response.status_code == 400 and 'cliente' in response.json()['detail']


@pytest.mark.parametrize('endpoint', ['optimize','recalculate-manual'])
@pytest.mark.parametrize('mixed', [True,False])
def test_route_round_trip_program_history_and_features(routing_env, endpoint, mixed):
    client, db, owner, *_ = routing_env
    owner.has_time_windows=owner.has_ztl=owner.needs_tail_lift=False
    db.commit()
    data=payload(routing_env)
    stop=verified_stop(owner.id,peso_kg=25,colli=3,tempo_scarico_min=12,note='Cancello B',
                       scarico_mattina_da='09:00',scarico_mattina_a='10:00',ztl=True,sponda=True)
    data['consegne']=(data['consegne'] if mixed else [])+[stop]
    before=db.query(Customer).count()
    response=client.post('/api/routes/'+endpoint,json=data)
    assert response.status_code == 200,response.text
    route_id=response.json()['id']
    assert client.post(f'/api/routes/{route_id}/program',json={}).status_code==200
    saved=client.get(f'/api/routes/{route_id}').json()
    row=next(d for d in saved['consegne'] if d['customer_id'] is None)
    for field in ['cliente_nome','indirizzo','lat','lon','peso_kg','colli','tempo_scarico_min','note','geocoding_token']:
        assert row[field]==stop[field]
    assert row['scarico_mattina_da'] is None and not row['ztl'] and not row['sponda']
    assert row['ordine'] and row['arrivo_stimato'] and row['km_tappa']>0 and row['minuti_tappa']>0
    assert saved['google_maps_url'] and saved['traffic_status']=='updated'
    assert db.query(Customer).count()==before
    db.get(RoutePlan,route_id).status='completato';db.commit()
    assert client.get(f'/api/routes/{route_id}').json()['consegne']==saved['consegne']
    data.update(route_id=route_id,consegne=saved['consegne'])
    assert client.post('/api/routes/recalculate-manual',json=data).status_code==409


def test_final_persistence_barrier(routing_env):
    from app.routers.routes import save_route_result
    from app.schemas import RoutePlanIn
    data=payload(routing_env)
    with pytest.raises(HTTPException) as error:
        save_route_result(routing_env[1],routing_env[2],RoutePlanIn(**data),
                          {'ordered':[dict(verified_stop(routing_env[2].id),lat=None)]},routing_env[6])
    assert error.value.status_code==400


@pytest.mark.parametrize('action',['complete','missed'])
def test_driver_lifecycle_and_pod_for_occasional_delivery(routing_env, storage, action):
    from app.routers import driver
    from app.services.usage_limits import start_route_usage
    client,db,owner,*_=routing_env
    owner.delivery_signature_enabled = True
    owner.needs_photo_proof = True
    person=Driver(user_id=owner.id,nome='Autista');db.add(person);db.flush()
    account=DriverAccount(driver_id=person.id,email='occasional@example.test',password_hash='test')
    db.add(account);db.commit()
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver]=lambda:account
    data=payload(routing_env)
    data.update(driver_id=person.id,consegne=[verified_stop(owner.id)])
    response=client.post('/api/routes/recalculate-manual',json=data)
    assert response.status_code==200,response.text
    route=db.get(RoutePlan,response.json()['id'])
    route.data_giro=date.today()
    start_route_usage(db,route);db.commit()
    assert db.get(RouteUsage,route.id).deliveries==1
    info=client.get(f'/api/driver/routes/{route.id}')
    assert info.status_code==200
    delivery=route.deliveries[0]
    row=info.json()['consegne'][0]
    assert row['customer_id'] is None and row['indirizzo']==delivery.indirizzo
    body=dict(signature_data=image_data(),signed_by_name='Rossi',delivery_photo_data=image_data('JPEG'),
              note_operatore='Cancello B',motivo_mancata='Assente')
    result=client.post(f'/api/driver/delivery/{delivery.id}/{action}',json=body)
    assert result.status_code==200,result.text
    state=db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    assert state.status==('completata' if action=='complete' else 'mancata')
    if action=='complete':
        assert state.signature_object_key and state.delivery_photo_object_key
        assert storage.objects[state.pod_object_key].startswith(b'%PDF')
        assert client.get(f'/api/driver/delivery/{delivery.id}/evidence/pod').status_code==200
        PdfReader = pytest.importorskip('pypdf').PdfReader
        pdf=PdfReader(io.BytesIO(storage.objects[state.pod_object_key]))
        text=' '.join(page.extract_text() for page in pdf.pages)
        assert delivery.cliente_nome in text and delivery.indirizzo in text


def test_capacity_and_plan_quota_include_occasional_stops(routing_env, monkeypatch):
    from app.services import usage_limits
    client,db,owner,_,_,_,vehicle,_=routing_env
    vehicle.capacita_kg=10;db.commit()
    data=payload(routing_env);data['consegne']=[verified_stop(owner.id,peso_kg=25)]
    assert client.post('/api/routes/optimize',json=data).status_code==400
    data['consegne'][0]['peso_kg']=5
    result=client.post('/api/routes/optimize',json=data)
    assert result.status_code==200,result.text
    route=db.get(RoutePlan,result.json()['id'])
    monkeypatch.setattr(usage_limits,'usage_summary',lambda *a:{'routes':{'used':0,'limit':10},'deliveries':{'used':10,'limit':10}})
    with pytest.raises(HTTPException) as error:usage_limits.start_route_usage(db,route)
    assert error.value.status_code==403
    assert db.get(RouteUsage,route.id) is None
