"""Responsive order interactions against the actual API and an isolated database."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'test-results'/'ui-tools'))
os.environ['DATABASE_URL']='sqlite://'
os.environ['ALLOW_SQLITE_LEGACY']='true'
from playwright.sync_api import sync_playwright
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base,get_db
from app.models import User, Deposit, Vehicle, Driver
from app.core.dependencies import current_user
from app.routers.orders import router
from app.routers.order_planning import router as planning_router
from check_management_design import ME,LIMITS,VEHICLES,DRIVERS,DEPOSITS,USAGE


def main():
    output=ROOT/'test-results'/'orders-responsive';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True, channel=os.getenv("GF_TEST_BROWSER_CHANNEL") or None)
        for width in (390,768,1024,1440):
            engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                user=User(username='browser-test',password_hash='test',plan_status='active');db.add(user);db.commit()
                db.add_all([Deposit(user_id=user.id,nome='Depot',indirizzo='Via Roma 1',lat=45.46,lon=9.19),Vehicle(user_id=user.id,nome='Van'),Driver(user_id=user.id,nome='Driver')]);db.commit()
                app=FastAPI();app.include_router(router);app.include_router(planning_router)
                app.dependency_overrides[get_db]=lambda:db
                app.dependency_overrides[current_user]=lambda:user
                with TestClient(app) as client:
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    def handle(route):
                        parsed=urlparse(route.request.url);path=parsed.path
                        if parsed.hostname!='orders.test':route.abort();return
                        if path.startswith(('/api/orders','/api/order-planning')):
                            response=client.request(route.request.method,path+('?' + parsed.query if parsed.query else ''),content=route.request.post_data,headers={'Content-Type':'application/json'})
                            route.fulfill(status=response.status_code,body=response.text,content_type='application/json');return
                        if path=='/api/billing/catalog.js':
                            route.fulfill(content_type='application/javascript',body='window.GF_PLANS='+json.dumps({k:dict(LIMITS,name=k,price_eur=29) for k in ('starter','business','pro')}));return
                        if not path.startswith('/api/'):
                            relative='static/dashboard/index.html' if path=='/dashboard' else path.lstrip('/')
                            file=(ROOT/relative).resolve()
                            if file.is_relative_to(ROOT) and file.is_file():route.fulfill(path=str(file))
                            else:route.fulfill(status=404,body='')
                            return
                        data={'/api/me':{'authenticated':False},'/api/settings':{},'/api/sector-config':{},
                              '/api/customers':[],'/api/deposits':DEPOSITS,'/api/vehicles':VEHICLES,'/api/drivers':DRIVERS,
                              '/api/vehicles/usage':USAGE,'/api/agents':[],'/api/routes':[],
                              '/api/notifications':{'items':[],'unread':0},'/api/notifications/count':{'unread':0},
                              '/api/driver/admin/chat-threads':[],'/api/driver/admin/unread':{'total':0,'routes':[]},
                              '/api/onboarding/status':{'completed':True,'workspace_operational':True,'steps':[]}}.get(path,{})
                        route.fulfill(json=data)
                    page.route('**/*',handle)
                    page.goto('http://orders.test/dashboard',wait_until='networkidle')
                    page.evaluate("owner=>{currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();showTab('dashboard');}",ME)
                    if page.get_by_role('button',name='Apri menu mobile').is_visible():
                        page.get_by_role('button',name='Apri menu mobile').click()
                        page.get_by_role('button',name='▤ Ordini',exact=True).click()
                    else:
                        page.locator('button.nav-item[data-tab="ordini"]').click()
                    page.wait_for_function("document.getElementById('ordersMessage').textContent.includes('Nessun ordine')")
                    page.locator('#ordersNew').click()
                    page.locator('#orderField-number').fill('ORD-001')
                    page.locator('#orderField-recipient_name').fill('Destinatario <script>test</script>')
                    page.locator('#orderField-delivery_address').fill('Via Roma 10, Milano')
                    page.locator('#orderField-tail_lift').select_option('false')
                    page.locator('#orderField-time_from').fill('14:00')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderEditorError').textContent.includes('entrambi')")
                    assert page.locator('#orderField-number').input_value()=='ORD-001'
                    page.locator('#orderField-time_to').fill('15:00')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderDetail').textContent.includes('ORD-001')")
                    assert page.locator('#orderDetail script').count()==0
                    page.get_by_role('button',name='Correggi dati operativi').click()
                    page.locator('#orderField-packages').fill('5')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderDetail').textContent.includes('Correzione')")
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'detail-{width}.png'),full_page=True)
                    page.locator('#tab-ordine-dettaglio > button').click()
                    page.wait_for_function("document.getElementById('ordersResults').textContent.includes('ORD-001')")
                    page.locator('#ordersView-cards').click()
                    assert page.locator('#ordersResults article').count()==1
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'list-{width}.png'),full_page=True)
                    # A ready order can be selected, persisted and reopened at every viewport.
                    from app.order_models import Order
                    order=db.query(Order).one();order.status='pronto'
                    from app.services.occasional_stops import sign_stop_address
                    order.address_verification={'input_address':order.delivery_address,'indirizzo':order.delivery_address,'stato_geocodifica':'verificato','lat':45.47,'lon':9.2,'geocoding_token':sign_stop_address(user.id,order.delivery_address,45.47,9.2)}
                    db.commit()
                    page.evaluate('GFOrders.load()')
                    page.locator('.order-select').check()
                    page.wait_for_function("document.getElementById('ordersSelectionCount').textContent.startsWith('1 ordini')")
                    page.locator('#ordersGoPlanning').click()
                    page.locator('#orderPlanningBanner').wait_for(state='visible')
                    assert page.locator('#openCustomerStepBtn').inner_text()=='Prosegui'
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.evaluate("fixtures=>{vehiclesCache=fixtures.vehicles;driversCache=fixtures.drivers;document.getElementById('routeDeposit').innerHTML='<option value=1>Depot</option>';}",{'vehicles':VEHICLES,'drivers':DRIVERS})
                    page.locator('#routeDate').fill('2099-01-15')
                    page.locator('#routeStart').fill('08:00')
                    page.locator('#routeStart').blur()
                    page.evaluate('refreshResourceAvailability()')
                    page.wait_for_function("document.getElementById('routeVehicle').options.length > 1")
                    page.locator('#routeVehicle').select_option('1')
                    page.locator('#routeDriver').select_option('1')
                    page.evaluate('updateRouteEnergyPricingV895()')
                    page.locator('#openCustomerStepBtn').click()
                    page.wait_for_function("deliveries.length===1")
                    assert page.evaluate("deliveries[0].order_refs.length===1 && deliveries[0].colli===5")
                    assert page.locator('#deliveryWorkbenchStep').is_visible()
                    assert page.locator('#customerPlanningStep').is_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'planning-{width}.png'),full_page=True)
                    page.evaluate("showTab('ordini')")
                    page.wait_for_function("document.querySelector('.order-select')?.checked")
                    page.locator('#ordersSearch').fill('inesistente')
                    page.wait_for_function("document.getElementById('ordersMessage').textContent.includes('Nessun ordine')")
                    page.locator('#tab-ordini').get_by_role('button',name='Collega i tuoi ordini').click()
                    assert page.locator('#tab-ordini-collegamenti').is_visible()
                    assert not errors,errors
                    context.close()
            engine.dispose()
        browser.close()
    print('Orders: create, edit, escaping, filters, persisted selection, prefilled planning stops and layout passed at 390/768/1024/1440px')

if __name__=='__main__':main()
