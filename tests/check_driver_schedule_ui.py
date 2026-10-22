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
    output=ROOT/'test-results'/'driver-schedules';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,channel=os.getenv('GF_TEST_BROWSER_CHANNEL') or None)
        for width in (390,768,1024,1440):
            with MonkeyPatch.context() as mp:
                generator=env.__wrapped__(mp,output)
                base=next(generator)
                ctx,data=fleet.__wrapped__(routing_env.__wrapped__(base,mp))
                client,db,user,_,customer,depot,vehicle,_=ctx
                from app.routers.vehicles_drivers import drivers_router
                client.app.include_router(drivers_router)
                from app.models import Vehicle,Driver
                vehicles=[dict(id=v.id,nome=v.nome,alimentazione='gasolio',consumo_l_100km=8,available=True) for v in db.query(Vehicle)]
                drivers=[dict(id=d.id,nome=d.nome,cognome='',full_name=d.nome,available=True) for d in db.query(Driver)]
                deposits=[dict(id=depot.id,nome=depot.nome,indirizzo=depot.indirizzo,lat=depot.lat,lon=depot.lon)]
                page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                def handle(route):
                    parsed=urlparse(route.request.url);path=parsed.path
                    if parsed.hostname!='fleet.test':route.abort();return
                    if path.startswith(('/api/fleet-planning','/api/routes','/api/resources','/api/drivers')):
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
                page.evaluate("showTab('autisti');editDriver(1)")
                page.locator('#driverFormOverlay [data-schedule-editor] summary').click()
                page.locator('#driverWorkScheduleStart').fill('08:00');page.locator('#driverWorkScheduleEnd').fill('17:00')
                page.locator('#driverWorkSchedule [data-add-break]').click()
                page.locator('#driverWorkScheduleBreak0Start').fill('08:15');page.locator('#driverWorkScheduleBreak0End').fill('08:45')
                page.locator('#driverWorkScheduleBreak0End').blur()
                page.screenshot(path=str(output/f'driver-{width}.png'),full_page=True)
                page.locator('#saveDriverBtn').click()
                page.locator('#driverFormOverlay').wait_for(state='hidden')
                assert db.get(Driver,1).work_schedule['breaks']==[{'start':'08:15','end':'08:45'}]
                # The creation form exposes the same controls and persists an independent schedule.
                page.evaluate('openNewDriverModal()')
                page.locator('#drNome').fill('Nuovo turnista')
                page.locator('#driverFormOverlay [data-schedule-editor]').evaluate('(n)=>n.open=true')
                page.locator('#driverWorkScheduleStart').fill('09:00');page.locator('#driverWorkScheduleEnd').fill('18:00')
                page.locator('#saveDriverBtn').click();page.locator('#driverFormOverlay').wait_for(state='hidden')
                assert db.query(Driver).filter_by(nome='Nuovo turnista').one().work_schedule['start']=='09:00'
                page.evaluate("showTab('giro')")
                page.locator('#routeVehicle').select_option('1');page.locator('#routeDriver').select_option('1')
                page.locator('#singleDriverField [data-schedule-editor] summary').click()
                assert page.locator('#routeDriverScheduleBreak0Start').input_value()=='08:15'
                # Daily override must not overwrite the driver's normal break.
                page.locator('#routeDriverScheduleBreak0End').fill('09:00');page.locator('#routeDriverScheduleBreak0End').blur()
                page.evaluate('rows=>{deliveries=rows;renderDeliveries();}',data['consegne'][:2])
                page.evaluate('optimizeRoute()')
                page.locator('#routePreviewResult .driver-break-row').wait_for()
                assert '09:00' in page.locator('#routePreviewResult .driver-break-row').inner_text()
                assert db.get(Driver,1).work_schedule['breaks'][0]['end']=='08:45'
                assert page.locator('#routePreviewResult [data-preview-stop]').count()==2
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.screenshot(path=str(output/f'single-{width}.png'),full_page=True)
                # Every read-only stop view contains the same break row.
                page.evaluate("renderUnifiedRouteView(lastRouteResult,'routePreviewResult')")
                assert page.locator('#routePreviewResult .driver-break-row').count()==1
                page.evaluate("clearRouteWorkspace();showTab('giro')")
                page.locator('#routeDate').fill('2099-01-16');page.locator('#routeStart').fill('08:00');page.locator('#routeStart').blur()
                page.evaluate('refreshResourceAvailability()')
                page.locator('[data-planning-mode-card]').filter(has_text='Più mezzi').click()  # chip "Più mezzi" (variante B)
                for i in range(2):
                    page.locator(f'#fleetVehicle{i}').select_option(str(vehicles[i]['id']))
                    page.locator(f'#fleetDriver{i}').select_option(str(drivers[i]['id']))
                page.locator('#fleetResources [data-schedule-editor] summary').first.click()
                assert page.locator('#fleetDriverSchedule0Break0Start').input_value()=='08:15'
                page.locator('#fleetStrategy').select_option('balanced')
                assert page.evaluate('routePlanningMissingFieldsV68()')==[]
                page.screenshot(path=str(output/f'fleet-setup-{width}.png'),full_page=True)
                page.evaluate('rows=>{deliveries=rows;renderDeliveries();}',data['consegne'][:6])
                page.evaluate('optimizeRoute()')
                page.locator('.fleet-lane-breaks').first.locator('summary').click()
                page.locator('.fleet-lane-breaks .driver-break-card').first.wait_for()
                assert page.locator('[data-fleet-stop]').count()==6
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.screenshot(path=str(output/f'fleet-{width}.png'),full_page=True)
                assert not errors,errors
                page.close()
                try:next(generator)
                except StopIteration:pass
        browser.close()
    print('Driver create/edit, daily override, single/fleet break rows: 390/768/1024/1440px passed')

if __name__=='__main__':main()
