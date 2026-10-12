"""Actual company APIs and signed provider deliveries on an isolated database."""
import base64
import hashlib
import hmac
import json
import pytest
from cryptography.fernet import Fernet
from test_order_ingestion import ingestion, CSV
from test_orders import orders
from app.order_models import Order, OrderSource, OrderImportRun

SECRET='only-a-test-webhook-secret-123456'

@pytest.fixture
def connectors(ingestion,monkeypatch):
    monkeypatch.setenv('ORDER_CONNECTOR_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('ORDER_INBOUND_ADDRESS','test@inbound.postmarkapp.com')
    monkeypatch.setenv('ORDER_INBOUND_PASSWORD','test-password-for-inbound-webhook-123456789')
    return ingestion


def create(ctx,provider='shopify'):
    response=ctx[0].post('/api/order-sources/connectors',json={'name':'Store','provider':provider,'store':'demo.myshopify.com' if provider=='shopify' else 'demo.example.com','secret':SECRET})
    assert response.status_code==201,response.text
    return response.json()


def order_body(provider='shopify'):
    if provider=='shopify':
        return {'id':123,'name':'#1001','shipping_address':{'first_name':'Mario','last_name':'Rossi','address1':'Via Roma 1','city':'Roma','zip':'00100','country':'Italy'},'line_items':[{'title':'Prodotto','quantity':2}]}
    return {'id':123,'number':'1001','shipping':{'first_name':'Mario','last_name':'Rossi','address_1':'Via Roma 1','city':'Roma','postcode':'00100','country':'IT'},'line_items':[{'name':'Prodotto','quantity':2}]}


def deliver(ctx,src,body,event='evt-1',secret=SECRET,store=None):
    raw=json.dumps(body).encode();provider=src['connector']['provider']
    signature=base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()
    if provider=='shopify':
        headers={'X-Shopify-Hmac-Sha256':signature,'X-Shopify-Shop-Domain':store or 'demo.myshopify.com','X-Shopify-Topic':'orders/create','X-Shopify-Webhook-Id':event}
    else:
        headers={'X-WC-Webhook-Signature':signature,'X-WC-Webhook-Source':store or 'https://demo.example.com/','X-WC-Webhook-Topic':'order.created','X-WC-Webhook-Delivery-ID':event}
    path='/api/order-connectors/hooks/'+ctx[1].get(OrderSource,src['id']).key
    return ctx[0].post(path,content=raw,headers={'Content-Type':'application/json',**headers})


@pytest.mark.parametrize('provider',['shopify','woocommerce'])
def test_signed_orders_dedupe_and_preferences(connectors,provider):
    client,db,*_=connectors;src=create(connectors,provider)
    assert 'connector_secret' not in client.get('/api/order-sources').text
    assert SECRET not in json.dumps(db.get(OrderSource,src['id']).configuration)
    response=deliver(connectors,src,order_body(provider))
    assert response.status_code==200,response.text
    assert response.json()['status']=='completed'
    row=db.query(Order).one();assert row.recipient_name=='Mario Rossi' and row.customer_id is None
    assert row.status=='da_verificare' and row.requested_date is None and row.operational_data['packages'] is None
    assert deliver(connectors,src,order_body(provider)).json()==response.json()
    assert db.query(Order).count()==1
    assert deliver(connectors,src,order_body(provider),event='invalid',secret='wrong').status_code==401
    assert deliver(connectors,src,order_body(provider),event='wrong-store',store='evil.example.com').status_code==401
    body=order_body(provider);body['id']=456
    assert deliver(connectors,src,body).status_code==409
    assert db.query(Order).count()==1


def email_body(src,text='Numero ordine: EMAIL-1\nDestinatario: Mario Rossi\nIndirizzo: Via Roma 1, Roma'):
    return {'OriginalRecipient':src['connector']['address'],'MessageID':'email-event-1','TextBody':text,'Attachments':[]}


def email_deliver(client,body,authorized=True):
    headers={'Authorization':'Basic '+base64.b64encode(b'girofacile:test-password-for-inbound-webhook-123456789').decode()} if authorized else {}
    return client.post('/api/order-connectors/email',json=body,headers=headers)


def test_email_unavailable_even_with_server_configuration(connectors):
    client,db,*_=connectors
    response=client.post('/api/order-sources/connectors',json={'name':'Email','provider':'email'})
    assert response.status_code==503 and 'sviluppo' in response.json()['detail']
    assert email_deliver(client,{}).status_code==503
    assert email_deliver(client,{},False).status_code==503
    assert db.query(OrderSource).count()==0 and db.query(Order).count()==0


def test_pause_and_tenant_ownership(connectors):
    from app.core.dependencies import current_user
    client,db,owner,other=connectors;src=create(connectors)
    result=client.post(f"/api/order-sources/{src['id']}/action",json={'version':src['version'],'action':'pause'})
    assert result.status_code==200
    assert deliver(connectors,src,order_body()).status_code==503
    client.app.dependency_overrides[current_user]=lambda:other
    assert client.get('/api/order-sources').json()['items']==[]
    assert client.put(f"/api/order-sources/{src['id']}/fields",json={'version':2,'excluded_fields':[]}).status_code==404
    assert db.query(Order).count()==0


def test_no_infrastructure_no_fake_connection(connectors,monkeypatch):
    client=connectors[0]
    monkeypatch.delenv('ORDER_CONNECTOR_KEY')
    response=client.post('/api/order-sources/connectors',json={'name':'Store','provider':'shopify','store':'demo.myshopify.com','secret':SECRET})
    assert response.status_code==503
    monkeypatch.delenv('ORDER_INBOUND_ADDRESS')
    assert client.post('/api/order-sources/connectors',json={'name':'Email','provider':'email'}).status_code==503
    assert connectors[1].query(OrderSource).count()==0


def test_bad_signature_large_payload_and_unsigned_ping(connectors):
    client,db,*_=connectors;src=create(connectors,'woocommerce');key=db.get(OrderSource,src['id']).key
    path='/api/order-connectors/hooks/'+key
    assert client.post(path,content=b'x'*2097153).status_code==413
    assert client.post(path,content='webhook_id=1',headers={'Content-Type':'application/x-www-form-urlencoded'}).json()['ping']
    assert db.query(Order).count()==0
    assert not db.get(OrderSource,src['id']).configuration.get('connector_received')


def test_missing_address_is_reported_not_imported(connectors):
    client,db,*_=connectors;src=create(connectors);body=order_body();body.pop('shipping_address')
    response=deliver(connectors,src,body)
    assert response.status_code==200 and response.json()['status']=='failed'
    assert db.query(Order).count()==0
    report=client.get(f"/api/order-sources/{src['id']}/runs").json()
    assert report['items'][0]['report']['error']


def test_existing_email_is_development_and_cannot_resume(connectors):
    client,db,owner,*_=connectors
    src=OrderSource(user_id=owner.id,key='existing-email',name='Email',kind='api',status='active',configuration={'connector':'email','inbound_address':'old@example.com','validated':True})
    db.add(src);db.commit()
    public=client.get('/api/order-sources').json()['items'][0]
    assert public['status']=='development'
    assert 'address' not in public['connector']
    assert client.post(f"/api/order-sources/{src.id}/action",json={'version':src.version,'action':'resume'}).status_code==503
    assert email_deliver(client,{'OriginalRecipient':'old@example.com'}).status_code==503


def test_connector_permissions_and_owner_only_configuration(connectors):
    from types import SimpleNamespace
    from fastapi import Request, HTTPException
    from app.core.dependencies import current_user
    from app.services.company_permissions import authorize
    client,db,owner,*_=connectors
    path='/api/order-sources/connectors'
    request=Request({'type':'http','method':'POST','path':path,'headers':[],'route':SimpleNamespace(path=path)})
    with pytest.raises(HTTPException):
        authorize(request,SimpleNamespace(permissions_json=json.dumps(['orders.read','orders.import'])))
    authorize(request,SimpleNamespace(permissions_json=json.dumps(['orders.read','orders.integrations'])))
    def collaborator(request:Request):
        request.state.company_collaborator=SimpleNamespace(id=123)
        return owner
    client.app.dependency_overrides[current_user]=collaborator
    assert client.post(path,json={'name':'Email','provider':'email'}).status_code==403
    assert db.query(OrderSource).count()==0
