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
    assert client.post('/api/orders/verify-addresses',json={}).status_code==403
    assert client.post('/api/orders',json={'number':'B'}).status_code==403
    assert client.put('/api/orders/'+str(order['id']),json={**order['operational_data'],'version':1}).status_code==403
    login_actor(['orders.read','orders.create'])
    assert client.post('/api/orders',json={'number':'B'}).status_code==201
    login_actor(['orders.read','orders.update'])
    assert client.post('/api/orders/verify-addresses',json={'q':'non-existent'}).status_code==200
    assert client.put('/api/orders/'+str(order['id']),json={**order['operational_data'],'version':1,'notes':'Correzione'}).status_code==200
    events=client.get('/api/orders/'+str(order['id'])).json()['events']
    assert events[0]['actor']==f'collaborator:{actor.id}'


def test_customer_endpoints_removed_for_owner_and_collaborators(company):
    from app.routers.orders import router
    from app.models import Customer
    client,db,owner,other,actor,_,_,login_owner,login_actor=company
    client.app.include_router(router)
    login_owner()
    order=client.post('/api/orders',json={'number':'ORD','recipient_name':'Name','delivery_address':'Address'}).json()
    before=db.query(Customer).count()
    assert client.get(f"/api/orders/{order['id']}/customers").status_code==404
    assert client.post(f"/api/orders/{order['id']}/customer",
                       json={'version':1,'action':'create'}).status_code==404
    login_actor(['orders.read','orders.update'])
    assert client.get(f"/api/orders/{order['id']}/customers").status_code==404
    assert db.query(Customer).count()==before


def test_selected_address_resolution_requires_planning_and_edit_permissions(company):
    from app.routers.orders import router
    from app.routers.order_planning import router as planning
    client,db,owner,other,actor,_,_,login_owner,login_actor=company
    client.app.include_router(router);client.app.include_router(planning)
    login_owner()
    row=client.post('/api/orders',json={'number':'SELECTED','recipient_name':'Name','delivery_address':'Address'}).json()
    login_actor(['orders.read'])
    assert client.post('/api/order-planning/verify-selected',json={'version':1,'order_ids':[row['id']]}).status_code==403
    login_actor(['orders.read','orders.plan'])
    state=client.put('/api/order-planning/selection',json={'version':0,'action':'add','order_ids':[row['id']]}).json()
    payload={'version':state['version'],'order_id':row['id'],'order_version':row['version'],
             'action':'manual','address':'Address','recipient_name':'Name','lat':45,'lon':9}
    assert client.post('/api/order-planning/resolve-address',json=payload).status_code==403
    assert client.post('/api/order-planning/resolve-address',json={**payload,'action':'exclude'}).status_code==200
