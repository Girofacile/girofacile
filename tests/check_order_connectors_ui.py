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
os.environ['APP_BASE_URL']='https://girofacile.test'
from playwright.sync_api import sync_playwright
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base,get_db
from app.models import User, Deposit, Vehicle, Driver, Customer
from app.core.dependencies import current_user
from app.routers.orders import router
from app.routers.order_planning import router as planning_router
from app.routers.order_sources import router as sources_router
from check_management_design import ME,LIMITS,VEHICLES,DRIVERS,DEPOSITS,USAGE


def main():
    from cryptography.fernet import Fernet
    os.environ['ORDER_CONNECTOR_KEY']=Fernet.generate_key().decode()
    os.environ['ORDER_INBOUND_ADDRESS']='uitest@inbound.postmarkapp.com'
    os.environ['ORDER_INBOUND_PASSWORD']='isolated-browser-inbound-password-123456789'
    output=ROOT/'test-results'/'connectors-responsive';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True, channel=os.getenv("GF_TEST_BROWSER_CHANNEL") or None)
        for width in (390,768,1024,1440):
            engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                user=User(username='browser-test',password_hash='test',plan_status='active');db.add(user);db.commit()
                db.add_all([Deposit(user_id=user.id,nome='Depot',indirizzo='Via Roma 1',lat=45.46,lon=9.19),Vehicle(user_id=user.id,nome='Van'),Driver(user_id=user.id,nome='Driver')]);db.commit()
                app=FastAPI();app.include_router(router);app.include_router(planning_router);app.include_router(sources_router)
                app.dependency_overrides[get_db]=lambda:db
                app.dependency_overrides[current_user]=lambda:user
                with TestClient(app) as client:
                    context=browser.new_context(viewport={'width':width,'height':1000})
                    page=context.new_page();errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    def handle(route):
                        parsed=urlparse(route.request.url);path=parsed.path
                        if parsed.hostname!='orders.test':route.abort();return
                        if path.startswith(('/api/orders','/api/order-planning','/api/order-sources')):
                            response=client.request(route.request.method,path+('?' + parsed.query if parsed.query else ''),content=route.request.post_data_buffer,headers={'Content-Type':route.request.headers.get('content-type','application/json')})
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
                    page.evaluate("showTab('ordini-collegamenti')")
                    page.get_by_role('button',name='Collega negozio',exact=True).click()
                    page.locator('#connectorName').fill('Negozio Shopify')
                    page.locator('#connectorStore').fill('demo.myshopify.com')
                    page.locator('#connectorSecret').fill('isolated-test-secret-123456789')
                    page.get_by_role('button',name='Prepara collegamento',exact=True).click()
                    page.wait_for_function("document.getElementById('orderSourceDetail').textContent.includes('Completa il collegamento')")
                    assert page.locator('#orderSourceDetail input[readonly]').input_value().startswith('https://')
                    assert not page.locator('[data-choice="api"][value="requested_date"]').is_checked()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'connector-shopify-{width}.png'),full_page=True)
                    page.evaluate("showTab('ordini-collegamenti')")
                    assert page.locator('#sourceCategories').get_by_text('Email',exact=True).count()==0
                    page.wait_for_function("document.getElementById('sourceMessage').textContent===''")
                    page.evaluate("GFOrderSources.unavailable('email')")
                    assert page.locator('#sourceWizard').get_by_text('Email · In fase di sviluppo',exact=True).is_visible()
                    assert page.locator('#sourceWizard form').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'email-development-{width}.png'),full_page=True)
                    assert not errors,errors
                    context.close()
            engine.dispose()
        browser.close()
    print('Email development notice and Shopify setup, fields and responsive layout passed at 390/768/1024/1440px')

if __name__=='__main__':main()
