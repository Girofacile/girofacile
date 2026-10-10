from test_company_collaborators import company


def test_order_permissions_are_explicit_and_rechecked(company):
    from app.routers.orders import router
    client,db,owner,other,actor,_,_,login_owner,login_actor=company
    client.app.include_router(router)
    login_owner()
    result=client.post('/api/orders',json={'number':'A'})
    assert result.status_code==201,result.text
    order=result.json()
    login_actor([])
    assert client.get('/api/orders').status_code==403
    login_actor(['orders.read'])
    assert client.get('/api/orders').status_code==200
    assert client.post('/api/orders',json={'number':'B'}).status_code==403
    assert client.put('/api/orders/'+str(order['id']),json={**order['operational_data'],'version':1}).status_code==403
    login_actor(['orders.read','orders.create'])
    assert client.post('/api/orders',json={'number':'B'}).status_code==201
    login_actor(['orders.read','orders.update'])
    assert client.put('/api/orders/'+str(order['id']),json={**order['operational_data'],'version':1,'notes':'Correzione'}).status_code==200
    events=client.get('/api/orders/'+str(order['id'])).json()['events']
    assert events[0]['actor']==f'collaborator:{actor.id}'


def test_matching_requires_explicit_permission_and_customer_creation_grant(company):
    from app.routers.orders import router
    from app.models import Customer
    client,db,owner,other,actor,_,_,login_owner,login_actor=company
    client.app.include_router(router);login_owner()
    order=client.post('/api/orders',json={'number':'MATCH','recipient_name':'Name','delivery_address':'Address'}).json()
    login_actor(['orders.read','orders.update'])
    assert client.get(f"/api/orders/{order['id']}/customers").status_code==403
    assert client.post(f"/api/orders/{order['id']}/customer",json={'version':1,'action':'separate'}).status_code==403
    login_actor(['orders.read','orders.match','customers.read'])
    assert client.get(f"/api/orders/{order['id']}/customers").status_code==200
    before=db.query(Customer).count()
    assert client.post(f"/api/orders/{order['id']}/customer",json={'version':1,'action':'create'}).status_code==403
    assert db.query(Customer).count()==before
    assert client.post(f"/api/orders/{order['id']}/customer",json={'version':1,'action':'separate'}).status_code==200
