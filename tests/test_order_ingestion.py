"""Real acquisition APIs on isolated databases; no production services."""
import io
import pytest
from copy import deepcopy
from openpyxl import Workbook
from test_orders import orders
from app.order_models import Order,OrderSource,OrderImportRun

CSV='NOrdine;RagioneSociale;IndSped;Pedana;NColli\nEXT-1;Recipient;Via Roma 1;No;3\n'

@pytest.fixture
def ingestion(orders):
    from app.routers.order_sources import router
    from app.services.order_source_security import _attempts
    _attempts.clear();orders[0].app.include_router(router)
    return orders


def setup(ctx,kind='file'):
    client=ctx[0]
    result=client.post('/api/order-sources',json={'name':'ERP export','kind':kind,'software':'Custom ERP'})
    assert result.status_code==201,result.text
    src=result.json()
    if kind=='file': response=client.post(f"/api/order-sources/{src['id']}/upload",files={'file':('orders.csv',CSV.encode(),'text/csv')})
    else: response=client.post(f"/api/order-sources/{src['id']}/sample",json={'orders':[{'external_id':'EXT-1','number':'ORD-1','recipient_name':'Recipient','delivery_address':'Via Roma 1'}]})
    assert response.status_code==200,response.text
    upload=response.json();rid=upload['run_id']
    result=client.put(f"/api/order-sources/{src['id']}",json={'version':src['version'],'mapping':upload['suggested_mapping']})
    assert result.status_code==200,result.text
    src=result.json()
    preview=client.post(f"/api/order-sources/{src['id']}/runs/{rid}/preview")
    assert preview.status_code==200 and preview.json()['status']=='preview_ready',preview.text
    result=client.post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'activate','run_id':rid})
    assert result.status_code==200,result.text
    return result.json(),rid


def api_source(ctx):
    src,rid=setup(ctx,'api')
    result=ctx[0].post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'rotate'})
    assert result.status_code==200,result.text
    return result.json(),{'Authorization':'Bearer '+result.json()['credential']}


def test_file_preview_confirmation_repeat_and_false(ingestion):
    client,db,*_=ingestion;src,rid=setup(ingestion)
    assert db.query(Order).count()==0
    path=f"/api/order-sources/{src['id']}/runs/{rid}/commit"
    assert client.post(path,json={'confirm':False}).status_code==422
    result=client.post(path,json={'confirm':True});assert result.status_code==200,result.text
    order=db.query(Order).one();assert order.operational_data['tail_lift'] is False
    assert order.operational_data['packages']==3 and order.customer_id is None
    assert client.post(path,json={'confirm':True}).json()['id']==rid
    upload=client.post(f"/api/order-sources/{src['id']}/upload",files={'file':('same.csv',CSV.encode())}).json()
    path=f"/api/order-sources/{src['id']}/runs/{upload['run_id']}"
    assert client.post(path+'/preview').json()['report']['unchanged']==1
    assert client.post(path+'/commit',json={'confirm':True}).status_code==200
    assert db.query(Order).count()==1


def test_api_idempotency_updates_preserve_corrections_and_original(ingestion):
    client,db,*_=ingestion;src,headers=api_source(ingestion)
    body={'batch_id':'batch-1','orders':[{'external_id':'EXT-1','number':'ORD-1','recipient_name':'Recipient','delivery_address':'Original address','packages':3,'tail_lift':False}]}
    result=client.post('/api/order-ingestion',json=body,headers=headers);assert result.status_code==200,result.text
    oid=db.query(Order).one().id;original=deepcopy(db.get(Order,oid).original_payload)
    assert client.post('/api/order-ingestion',json=body,headers=headers).json()['id']==result.json()['id']
    changed=deepcopy(body);changed['orders'][0]['packages']=4
    assert client.post('/api/order-ingestion',json=changed,headers=headers).status_code==409
    order=client.get(f'/api/orders/{oid}').json()
    assert client.put(f'/api/orders/{oid}',json={**order['operational_data'],'version':order['version'],'packages':99}).status_code==200
    changed['batch_id']='batch-2';changed['orders'][0]['delivery_address']='New address'
    result=client.post('/api/order-ingestion',json=changed,headers=headers);assert result.status_code==200,result.text
    row=db.get(Order,oid)
    assert row.operational_data['packages']==99 and row.delivery_address=='New address'
    assert row.ingested_payload['packages']==4 and row.original_payload==original
    assert row.address_verification is None
    assert src['credential'] not in client.get('/api/order-sources').text
    assert 'credential_hash' not in client.get('/api/order-sources').text


def test_invalid_batch_and_started_update_are_atomic(ingestion):
    client,db,*_=ingestion;src,headers=api_source(ingestion)
    good={'external_id':'X','number':'X'}
    result=client.post('/api/order-ingestion',headers=headers,json={'batch_id':'invalid','orders':[good,{'external_id':'Y'}]})
    assert result.status_code==422 and db.query(Order).count()==0
    assert result.json()['report']['invalid']==1
    assert client.post('/api/order-ingestion',headers=headers,json={'batch_id':'ok','orders':[good]}).status_code==200
    row=db.query(Order).one();row.status='in_consegna';db.commit()
    result=client.post('/api/order-ingestion',headers=headers,json={'batch_id':'blocked','orders':[{'external_id':'NEW','number':'NEW'},{**good,'notes':'changed'}]})
    assert result.status_code==422 and db.query(Order).count()==1
    assert db.get(Order,row.id).operational_data['notes'] is None


def test_revocation_rotation_and_source_isolation(ingestion):
    client,db,owner,other=ingestion;src,headers=api_source(ingestion)
    body={'batch_id':'bad','orders':[{'external_id':'X','number':'X'}]}
    assert client.post('/api/order-ingestion',json=body).status_code==401
    token=src.pop('credential')
    result=client.post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'rotate'})
    assert result.status_code==200 and result.json()['credential']!=token
    assert client.post('/api/order-ingestion',headers=headers,json=body).status_code==401
    current=result.json();headers={'Authorization':'Bearer '+current['credential']}
    assert client.post(f"/api/order-sources/{src['id']}/action",json={'version':current['version'],'action':'revoke'}).status_code==200
    assert client.post('/api/order-ingestion',headers=headers,json=body).status_code==401
    from app.core.dependencies import current_user
    client.app.dependency_overrides[current_user]=lambda:other
    assert client.get('/api/order-sources').json()['total']==0
    assert client.post(f"/api/order-sources/{src['id']}/upload",files={'file':('file.csv',CSV.encode())}).status_code==404


def test_xlsx_values_formulas_size_and_duplicates(ingestion):
    from app.services.order_files import read_file,mapped
    from fastapi import HTTPException
    book=Workbook();sheet=book.active;sheet.append(['Id','Numero','Peso','Sponda']);sheet.append(['0001','N-1','12,5','No'])
    buffer=io.BytesIO();book.save(buffer)
    headers,rows=read_file(buffer.getvalue(),'orders.xlsx')
    row=mapped(rows[0],{'external_id':'Id','number':'Numero','weight_kg':'Peso','tail_lift':'Sponda'})
    assert row['external_id']=='0001' and row['weight_kg']==12.5 and row['tail_lift'] is False
    sheet['D2']='=1+1';buffer=io.BytesIO();book.save(buffer)
    with pytest.raises(HTTPException):read_file(buffer.getvalue(),'orders.xlsx')
    with pytest.raises(HTTPException):read_file(b'x'*(2*1024*1024+1),'big.csv')
    with pytest.raises(HTTPException):read_file(b'id;id\n1;2','duplicate.csv')
    client,db,*_=ingestion;src,headers=api_source(ingestion);duplicate={'external_id':'D','number':'D'}
    assert client.post('/api/order-ingestion',headers=headers,json={'batch_id':'dup','orders':[duplicate,duplicate]}).status_code==422
    assert db.query(Order).count()==0


def test_dry_run_rate_limit_and_rollback(ingestion,monkeypatch):
    client,db,*_=ingestion;src,headers=api_source(ingestion)
    body={'batch_id':'dry','dry_run':True,'orders':[{'external_id':'D','number':'D','packages':4}]}
    assert client.post('/api/order-ingestion',json=body,headers=headers).status_code==200
    assert db.query(Order).count()==0
    from app.services import order_ingestion
    actual=order_ingestion.apply_orders
    def fail(*args): actual(*args);raise RuntimeError('Synthetic failure')
    monkeypatch.setattr(order_ingestion,'apply_orders',fail)
    body['dry_run']=False
    result=client.post('/api/order-ingestion',json=body,headers=headers)
    assert result.status_code==422 and db.query(Order).count()==0
    source=db.get(OrderSource,src['id']);source.configuration={**source.configuration,'_rate_count':60};db.commit()
    assert client.post('/api/order-ingestion',json={**body,'batch_id':'rate'},headers=headers).status_code==429


def test_stale_preview_expiry_and_activation_guard(ingestion):
    from datetime import datetime,timedelta
    client,db,*_=ingestion;src,rid=setup(ingestion)
    path=f"/api/order-sources/{src['id']}/runs/{rid}"
    assert client.post(path+'/commit',json={'confirm':True}).status_code==200
    upload=client.post(f"/api/order-sources/{src['id']}/upload",files={'file':('orders.csv',CSV.encode())}).json()
    path=f"/api/order-sources/{src['id']}/runs/{upload['run_id']}"
    assert client.post(path+'/preview').status_code==200
    row=db.query(Order).one();row.version+=1;db.commit()
    result=client.post(path+'/commit',json={'confirm':True})
    assert result.status_code==422 and result.json()['report']['invalid']==1
    item=db.get(OrderImportRun,upload['run_id']);item.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert client.post(path+'/preview').status_code==410
    source=db.get(OrderSource,src['id'])
    result=client.post(f"/api/order-sources/{src['id']}/action",json={'version':source.version,'action':'activate','run_id':rid})
    assert result.status_code==410  # completed imports have no retained staged payload
    result=client.post(f"/api/order-sources/{src['id']}/action",json={'version':source.version,'action':'remove'})
    assert result.status_code==200 and db.query(Order).count()==1
    assert client.post(f"/api/order-sources/{src['id']}/upload",files={'file':('orders.csv',CSV.encode())}).status_code==409


def test_delete_source_removes_connection_and_preserves_acquired_orders(ingestion):
    client,db,*_=ingestion;src,rid=setup(ingestion)
    result=client.post(f"/api/order-sources/{src['id']}/runs/{rid}/commit",json={'confirm':True})
    assert result.status_code==200,result.text
    order=db.query(Order).one();old_source_id=order.source_id
    response=client.delete(f"/api/order-sources/{src['id']}?version={src['version']}")
    assert response.status_code==200 and response.json()['deleted'] is True,response.text
    assert db.get(OrderSource,old_source_id) is None
    db.refresh(order)
    archive=db.get(OrderSource,order.source_id)
    assert archive is not None and archive.kind=='archive' and archive.name=='ERP export'
    assert archive.credential_hash is None and archive.configuration=={'archived':True}
    assert db.query(OrderImportRun).filter_by(source_id=old_source_id).count()==0
    assert client.get('/api/order-sources').json()['total']==0
    assert client.post(f"/api/order-sources/{old_source_id}/upload",files={'file':('orders.csv',CSV.encode())}).status_code==404
    assert client.get(f"/api/orders/{order.id}").json()['source_name']=='ERP export'


def test_source_ids_and_tenants_are_independent(ingestion):
    client,db,owner,other=ingestion
    first,h1=api_source(ingestion);second,h2=api_source(ingestion)
    body={'batch_id':'same','orders':[{'external_id':'SAME','number':'SAME'}]}
    for h in (h1,h2):assert client.post('/api/order-ingestion',headers=h,json=body).status_code==200
    assert db.query(Order).count()==2
    assert client.post('/api/order-ingestion',headers=h1,json={**body,'batch_id':'unknown','orders':[{'external_id':'X','number':'X','user_id':other.id}]}).status_code==422
    assert db.query(Order).count()==2


def test_body_limit_precedes_multipart_parser():
    from fastapi import FastAPI,Request
    from fastapi.testclient import TestClient
    from app.services.order_source_security import IngestionBodyLimit
    app=FastAPI();called=[]
    @app.post('/api/order-sources/1/upload')
    async def endpoint(request:Request):
        called.append(True);return {'size':len(await request.body())}
    app.add_middleware(IngestionBodyLimit)
    with TestClient(app) as client:
        response=client.post('/api/order-sources/1/upload',content=b'x'*(2*1024*1024+65537))
        assert response.status_code==413 and not called
        assert client.post('/api/order-sources/1/upload',content=b'abc').json()=={'size':3}


def test_collaborator_permissions_and_owner_only_tokens(ingestion):
    from types import SimpleNamespace
    from fastapi import Request
    from app.core.dependencies import current_user
    from app.services.company_permissions import authorize
    client,db,owner,_=ingestion;src,headers=api_source(ingestion)
    def collaborator(request:Request):
        request.state.company_collaborator=SimpleNamespace(id=42)
        return owner
    client.app.dependency_overrides[current_user]=collaborator
    assert client.post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'rotate'}).status_code==403

    import json
    from fastapi import HTTPException
    importer=SimpleNamespace(permissions_json=json.dumps(['orders.read','orders.import']))
    integrator=SimpleNamespace(permissions_json=json.dumps(['orders.read','orders.integrations']))
    def check(method,path,actor):
        req=Request({'type':'http','method':method,'path':path,'headers':[],'route':SimpleNamespace(path=path)})
        return authorize(req,actor)
    check('POST','/api/order-sources/{source_id}/upload',importer)
    check('POST','/api/order-sources/{source_id}/runs/{run_id}/commit',importer)
    for method,path in [('POST','/api/order-sources'),('PUT','/api/order-sources/{source_id}'),('PUT','/api/order-sources/{source_id}/fields'),('DELETE','/api/order-sources/{source_id}'),('POST','/api/order-sources/{source_id}/action')]:
        with pytest.raises(HTTPException) as error:check(method,path,importer)
        assert error.value.status_code==403
        check(method,path,integrator)
    with pytest.raises(HTTPException):check('POST','/api/order-sources/{source_id}/runs/{run_id}/commit',integrator)


def test_numeric_file_codes_and_api_preview_validate_optional_fields(ingestion):
    from app.services.order_files import mapped
    assert mapped({'ID':123,'N':456},{'external_id':'ID','number':'N'})['external_id']=='123'
    with pytest.raises(ValueError):mapped({'ID':1234567890123456,'N':456},{'external_id':'ID','number':'N'})
    client,db,*_=ingestion;src,_=setup(ingestion,'api')
    sample=client.post(f"/api/order-sources/{src['id']}/sample",json={'orders':[{'external_id':'E','number':'E','recipient_name':'X','delivery_address':'Y','packages':-1}]}).json()
    result=client.post(f"/api/order-sources/{src['id']}/runs/{sample['run_id']}/preview")
    assert result.status_code==200 and result.json()['status']=='preview_invalid'
    assert db.query(Order).count()==0


def test_draft_api_key_generation_before_activation(ingestion):
    """The owner can generate/copy the key first, but ingestion stays blocked until activation."""
    client, db, owner, other = ingestion
    src = client.post('/api/order-sources', json={'name': 'Gestionale demo', 'kind': 'api'}).json()
    result = client.post(f"/api/order-sources/{src['id']}/action",
                         json={'version': src['version'], 'action': 'rotate'})
    assert result.status_code == 200, result.text
    generated = result.json()
    secret = generated['credential']
    assert generated['status'] == 'draft' and secret.startswith('gf_orders_')
    assert secret not in client.get('/api/order-sources').text
    payload = {'batch_id': 'test-key-first', 'orders': [{'external_id': 'TEST-01', 'number': 'TEST-01'}]}
    headers = {'Authorization': 'Bearer ' + secret}
    assert client.post('/api/order-ingestion', headers=headers, json=payload).status_code == 403
    sample = client.post(f"/api/order-sources/{src['id']}/sample",
                         json={'orders': payload['orders']}).json()
    rid = sample['run_id']
    configured = client.put(f"/api/order-sources/{src['id']}",
                            json={'version': generated['version'],
                                  'mapping': {'external_id': 'external_id', 'number': 'number'}})
    assert configured.status_code == 200, configured.text
    current = configured.json()
    preview = client.post(f"/api/order-sources/{src['id']}/runs/{rid}/preview")
    assert preview.status_code == 200 and preview.json()['status'] == 'preview_ready'
    activated = client.post(f"/api/order-sources/{src['id']}/action",
                            json={'version': current['version'], 'action': 'activate', 'run_id': rid})
    assert activated.status_code == 200 and activated.json()['has_credential'] is True
    assert client.post('/api/order-ingestion', headers=headers, json=payload).status_code == 200


def test_selected_fields_ignore_invalid_values_and_require_recipient(ingestion):
    client,db,*_=ingestion;src,headers=api_source(ingestion)
    path=f"/api/order-sources/{src['id']}/fields"
    assert client.put(path,json={'version':src['version'],'excluded_fields':['delivery_address']}).status_code==422
    response=client.put(path,json={'version':src['version'],'excluded_fields':['requested_date','weight_kg','time_from']})
    assert response.status_code==200,response.text
    configured=response.json()
    assert configured['status']=='active' and configured['has_credential']
    assert 'time_to' in configured['excluded_fields']
    assert client.put(path,json={'version':src['version'],'excluded_fields':[]}).status_code==409
    row={'external_id':'SELECT','number':'SELECT','recipient_name':'Recipient','delivery_address':'Via Roma 1','requested_date':'invalid','weight_kg':'bad','time_to':'bad','tail_lift':False}
    response=client.post('/api/order-ingestion',headers=headers,json={'batch_id':'selected','orders':[row]})
    assert response.status_code==200,response.text
    order=db.query(Order).one()
    assert order.requested_date is None and order.operational_data['weight_kg'] is None
    assert order.operational_data['tail_lift'] is False
    response=client.post('/api/order-ingestion',headers=headers,json={'batch_id':'missing-recipient','orders':[{'external_id':'MISSING','number':'MISSING'}]})
    assert response.status_code==422 and db.query(Order).count()==1
    assert client.get('/api/order-sources').json()['items'][0]['excluded_fields']==configured['excluded_fields']


def test_file_preferences_invalidate_preview_and_allow_missing_excluded_column(ingestion):
    client,db,*_=ingestion;src,rid=setup(ingestion)
    mapping={**src['mapping'],'requested_date':'AbsentDate'}
    src=client.put(f"/api/order-sources/{src['id']}",json={'version':src['version'],'mapping':mapping}).json()
    src=client.put(f"/api/order-sources/{src['id']}/fields",json={'version':src['version'],'excluded_fields':['requested_date']}).json()
    path=f"/api/order-sources/{src['id']}/runs/{rid}"
    assert client.post(path+'/preview').json()['status']=='preview_ready'
    src=client.post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'activate','run_id':rid}).json()
    src=client.put(f"/api/order-sources/{src['id']}/fields",json={'version':src['version'],'excluded_fields':['requested_date','packages']}).json()
    assert client.post(path+'/commit',json={'confirm':True}).status_code==409
    assert client.post(path+'/preview').json()['status']=='preview_ready'
    assert client.post(path+'/commit',json={'confirm':True}).status_code==200
    assert db.query(Order).one().operational_data['packages'] is None


def test_excluding_date_on_reimport_clears_constraint_preserves_original(ingestion):
    client,db,*_=ingestion;src,headers=api_source(ingestion)
    row={'external_id':'DATE','number':'DATE','recipient_name':'Name','delivery_address':'Via Roma 1','requested_date':'2099-01-16'}
    assert client.post('/api/order-ingestion',headers=headers,json={'batch_id':'before-choice','orders':[row]}).status_code==200
    original=deepcopy(db.query(Order).one().original_payload)
    src=client.put(f"/api/order-sources/{src['id']}/fields",json={'version':src['version'],'excluded_fields':['requested_date']}).json()
    assert db.query(Order).one().requested_date is not None
    assert client.post('/api/order-ingestion',headers=headers,json={'batch_id':'after-choice','orders':[row]}).status_code==200
    order=db.query(Order).one()
    assert order.requested_date is None and order.original_payload==original
    src=client.put(f"/api/order-sources/{src['id']}/fields",json={'version':src['version'],'excluded_fields':[]}).json()
    row['requested_date']='invalid'
    assert client.post('/api/order-ingestion',headers=headers,json={'batch_id':'enabled-again','orders':[row]}).status_code==422
