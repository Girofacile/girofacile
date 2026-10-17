"""Actual fleet API and dashboard at four widths; no real providers or messages."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'test-results'/'ui-tools'))
os.environ['DATABASE_URL']='sqlite://';os.environ['ALLOW_SQLITE_LEGACY']='true'
from playwright.sync_api import sync_playwright
from pytest import MonkeyPatch
from test_agents_feature import env
from test_routing_architecture import routing_env
from test_fleet_planning import fleet
from check_management_design import ME,LIMITS,USAGE


def main():
    output=ROOT/'test-results'/'fleet-responsive';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,channel=os.getenv('GF_TEST_BROWSER_CHANNEL') or None)
        for width in (390,768,1024,1440):
            with MonkeyPatch.context() as mp:
                generator=env.__wrapped__(mp,output)
                base=next(generator)
                ctx,data=fleet.__wrapped__(routing_env.__wrapped__(base,mp))
                client,db,user,_,customer,depot,vehicle,_=ctx
                from app.models import Vehicle,Driver
                vehicles=[dict(id=v.id,nome=v.nome,alimentazione='gasolio',consumo_l_100km=8,available=True) for v in db.query(Vehicle)]
                drivers=[dict(id=d.id,nome=d.nome,cognome='',full_name=d.nome,available=True) for d in db.query(Driver)]
                deposits=[dict(id=depot.id,nome=depot.nome,indirizzo=depot.indirizzo,lat=depot.lat,lon=depot.lon)]
                page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                def handle(route):
                    parsed=urlparse(route.request.url);path=parsed.path
                    if parsed.hostname!='fleet.test':route.abort();return
                    if path.startswith(('/api/fleet-planning','/api/routes','/api/resources')):
                        response=client.request(route.request.method,path+('?' + parsed.query if parsed.query else ''),content=route.request.post_data_buffer,headers={'Content-Type':'application/json'})
                        route.fulfill(status=response.status_code,body=response.text,content_type='application/json');return
                    if path=='/api/billing/catalog.js':route.fulfill(content_type='application/javascript',body='window.GF_PLANS='+json.dumps({k:dict(LIMITS,name=k,price_eur=29) for k in ('starter','business','pro')}));return
                    if not path.startswith('/api/'):
                        file=(ROOT/('static/dashboard/index.html' if path=='/dashboard' else path.lstrip('/'))).resolve()
                        if file.is_relative_to(ROOT) and file.is_file():route.fulfill(path=str(file))
                        else:route.fulfill(status=404,body='')
                        return
                    result={'/api/me':{'authenticated':False},'/api/settings':{},'/api/sector-config':{},'/api/customers':[],
                            '/api/vehicles':vehicles,'/api/drivers':drivers,'/api/deposits':deposits,'/api/agents':[],
                            '/api/vehicles/usage':USAGE,'/api/notifications':{'items':[],'unread':0},'/api/notifications/count':{'unread':0},
                            '/api/driver/admin/chat-threads':[],'/api/driver/admin/unread':{'total':0,'routes':[]},
                            '/api/onboarding/status':{'completed':True,'workspace_operational':True,'steps':[]}}.get(path,{})
                    route.fulfill(json=result)
                page.route('**/*',handle)
                page.goto('http://fleet.test/dashboard',wait_until='networkidle')
                page.evaluate("owner=>{currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();showTab('giro');}",ME)
                page.evaluate("fixtures=>{vehiclesCache=fixtures.vehicles;driversCache=fixtures.drivers;document.getElementById('routeDeposit').innerHTML='<option value=1>Depot</option>';}",{'vehicles':vehicles,'drivers':drivers})
                page.locator('#routeDate').fill('2099-01-15');page.locator('#routeStart').fill('08:00');page.locator('#routeStart').blur()
                page.evaluate('refreshResourceAvailability()')
                page.locator('[data-planning-mode-card]').filter(has_text='Più mezzi').click()  # card "Più mezzi" del layout C4
                assert page.locator('#planningMode').input_value()=='fleet'
                assert page.get_by_role('radio',name='Più mezzi',exact=True).is_checked()
                assert page.locator('#fleetSetup').is_visible()
                assert page.evaluate("document.getElementById('planStepTitle1').compareDocumentPosition(document.getElementById('planningModeTitle')) & Node.DOCUMENT_POSITION_FOLLOWING")
                for i in range(2):
                    page.locator(f'#fleetVehicle{i}').select_option(str(vehicles[i]['id']))
                    page.locator(f'#fleetDriver{i}').select_option(str(drivers[i]['id']))
                # Il radio nativo permette anche il cambio da tastiera; conserva le risorse.
                page.get_by_role('radio',name='Più mezzi',exact=True).focus()
                page.keyboard.press('ArrowLeft')
                assert page.locator('#planningMode').input_value()=='single'
                assert page.locator('#singleVehicleField').is_visible()
                assert page.locator('#fleetSetup').is_hidden()
                page.keyboard.press('ArrowRight')
                assert page.locator('#planningMode').input_value()=='fleet'
                for i in range(2):
                    assert page.locator(f'#fleetVehicle{i}').input_value()==str(vehicles[i]['id'])
                    assert page.locator(f'#fleetDriver{i}').input_value()==str(drivers[i]['id'])
                page.locator('#fleetStrategy').select_option('balanced')
                assert page.locator('#singleVehicleField').is_hidden()
                page.locator('#openCustomerStepBtn').click()
                assert page.evaluate('routePlanningMissingFieldsV68()')==[]
                assert page.locator('#customerPlanningStep').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/f'setup-{width}.png'),full_page=True)
                page.evaluate('rows=>{deliveries=rows;renderDeliveries();}',data['consegne'][:6])
                page.evaluate('optimizeRoute()')
                page.get_by_role('heading',name='Controlla la suddivisione').wait_for()
                assert page.locator('[data-fleet-stop]').count()==6
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/f'preview-{width}.png'),full_page=True)
                # Flusso attuale (dal 13/10): sposta una consegna, conferma l'avviso, ricalcola, poi un solo "Pianifica giri".
                move=page.locator('[data-fleet-move]').first
                move.select_option(move.locator('option:not([value=""])').first.get_attribute('value'))
                page.get_by_role('button',name='Sposta comunque',exact=True).click()
                assert page.locator('[data-fleet-plan]').is_disabled()
                page.locator('[data-fleet-recalc]').click()
                page.wait_for_function("document.getElementById('fleetMessage')?.textContent.includes('Nuove fermate')")
                page.locator('[data-fleet-plan]').click()
                page.locator('[data-fleet-review] .gf-badge[data-status="success"]',has_text='Giri programmati').wait_for()
                page.locator('[data-open]').first.click()
                page.wait_for_function("document.getElementById('planningMode').value==='single'")
                assert page.locator('#singleVehicleField').is_visible()
                assert not errors,errors
                page.close()
                try:next(generator)
                except StopIteration:pass
        browser.close()
    print('Fleet setup, preview, manual move, save and program passed at 390/768/1024/1440px')

if __name__=='__main__':main()
