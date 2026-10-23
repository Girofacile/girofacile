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
from playwright.sync_api import expect, sync_playwright
from time import sleep
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


def select_ready(page):
    """Seleziona gli ordini pronti aspettando ogni salvataggio, anche su mobile."""
    box=page.get_by_role('checkbox',name='Seleziona ordini di questa pagina',exact=True)
    # Sulle schede mobili l'intestazione resta nel DOM ma ridotta a 1 pixel.
    header_visible=box.count() and box.evaluate("el=>el.closest('thead').getBoundingClientRect().width>2")
    if header_visible:
        box.check()
        expect(box).to_be_enabled()
        return
    # La lista viene ridisegnata durante il salvataggio. Conservare etichette, non
    # nodi DOM, e attendere il nuovo render: in busy tutte le caselle sono disabilitate.
    labels=page.locator(
        'input.order-select:not(.order-select-all):not([disabled]):not(:checked)'
    ).evaluate_all("nodes=>nodes.map(node=>node.getAttribute('aria-label'))")
    for label in labels:
        box=page.get_by_role('checkbox',name=label,exact=True)
        box.check()
        expect(box).to_be_checked()
        expect(box).to_be_enabled()

def main():
    output=ROOT/'test-results'/'orders-responsive';output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True, channel=os.getenv("GF_TEST_BROWSER_CHANNEL") or None)
        for width in (390,768,1024,1440):
            engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                user=User(username='browser-test',password_hash='test',plan='business',plan_status='active');db.add(user);db.commit()
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
                            # Exercise selection latency beyond the former 150 ms polling delay.
                            if path=='/api/order-planning/selection' and route.request.method=='PUT':
                                sleep(0.25)
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
                              '/api/customers':[
                                  {'id':101,'nome':'Cliente verificato','indirizzo':'Via Roma 1','stato_geocodifica':'verificato','lat':45.46,'lon':9.19,'tempo_scarico_min':15},
                                  {'id':102,'nome':'Cliente da verificare','indirizzo':'Via Roma 2','stato_geocodifica':'da_verificare','lat':None,'lon':None}],'/api/deposits':DEPOSITS,'/api/vehicles':VEHICLES,'/api/drivers':DRIVERS,
                              '/api/vehicles/usage':USAGE,'/api/agents':[],'/api/routes':[],
                              '/api/notifications':{'items':[],'unread':0},'/api/notifications/count':{'unread':0},
                              '/api/driver/admin/chat-threads':[],'/api/driver/admin/unread':{'total':0,'routes':[]},
                              '/api/onboarding/status':{'completed':True,'workspace_operational':True,'steps':[]}}.get(path,{})
                        route.fulfill(json=data)
                    page.route('**/*',handle)
                    page.goto('http://orders.test/dashboard',wait_until='networkidle')
                    page.evaluate("owner=>{currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();showTab('dashboard');}",ME)
                    # Su mobile la voce Ordini è nella sidebar a scomparsa del layout base.
                    if page.get_by_role('button',name='Apri il menu',exact=True).is_visible():
                        page.get_by_role('button',name='Apri il menu',exact=True).click()
                    page.locator('button.gf-sidebar__item[data-tab="ordini"]').click()
                    page.wait_for_function("document.getElementById('ordersMessage').textContent.includes('Nessun ordine')")
                    assert page.locator('#ordersVerifyAll').count()==0
                    page.locator('#ordersNew').click()
                    page.locator('#orderField-number').fill('ORD-001')
                    page.locator('#orderField-recipient_name').fill('Destinatario <script>test</script>')
                    page.locator('#orderField-delivery_address').fill('Via Roma 10, Milano')
                    page.locator('#orderFormFields [data-order-form-optional] summary').click()
                    page.locator('#orderField-tail_lift').select_option('false')
                    page.locator('#orderField-time_from').fill('14:00')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderEditorError').textContent.includes('entrambi')")
                    assert page.locator('#orderField-number').input_value()=='ORD-001'
                    page.locator('#orderField-time_to').fill('15:00')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderModalContent').textContent.includes('ORD-001')")
                    assert page.locator('#orderModal').is_visible()
                    assert page.locator('#orderModalContent script').count()==0
                    page.get_by_role('button',name='Modifica dati',exact=True).click()
                    page.locator('#orderFormFields [data-order-form-optional] summary').click()
                    page.locator('#orderField-packages').fill('5')
                    page.locator('#orderSave').click()
                    page.wait_for_function("document.getElementById('orderModalContent').textContent.includes('Modifica dati')")
                    from app.order_models import Order
                    page.evaluate('GFOrders.open('+str(db.query(Order).one().id)+')')
                    assert page.locator('#orderCustomerPanel').count()==0
                    assert page.get_by_role('button',name='Sì, associa').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'detail-{width}.png'),full_page=True)
                    page.locator('#orderModal [data-order-modal-close]').click()
                    page.locator('#orderModal').wait_for(state='hidden')
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
                    created=client.post('/api/orders',json={**order.original_payload,'number':'ORD-002','packages':3}).json()
                    second=db.get(Order,created['id']);second.status='pronto';second.address_verification=order.address_verification;db.commit()
                    page.evaluate('GFOrders.load()')
                    page.locator('#ordersView-table').click()
                    select_ready(page)
                    page.wait_for_function("document.getElementById('ordersSelectionCount').textContent.startsWith('2 ordini')")
                    page.locator('#ordersGoPlanning').click()
                    page.locator('#tab-giro').wait_for(state='visible')
                    expect(page.locator('#orderPlanningBanner')).to_have_count(0)
                    expect(page.locator('#openCustomerStepBtn')).to_have_count(0)
                    page.locator('#routePlanningActions button').click()
                    expect(page.locator('#orderPlanningProceedMessage')).to_contain_text('l’autista')
                    expect(page.locator('#orderPlanningProceedMessage')).to_contain_text('il mezzo')
                    expect(page.locator('#statDeliveries')).to_have_text('2')
                    expect(page.locator('#statColli')).to_have_text('8')
                    assert page.locator('#deliveryWorkbenchStep').is_visible()
                    # Le consegne sono sempre visibili accanto alla scelta di mezzi e autisti.
                    assert page.locator('#deliveryTableArea').is_visible()
                    expect(page.locator('#deliveryBody tr')).to_have_count(2)
                    expect(page.locator('#deliveryBody')).to_contain_text('ORD-002')
                    assert page.locator('#routeStart').input_value()==''
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
                    page.evaluate('GFOrderPlanning.beforeCalculate()')
                    page.wait_for_function("deliveries.length===2")
                    expect(page.locator('#orderPlanningProceedMessage')).to_be_hidden()
                    page.locator('#deliveryTableArea').get_by_role('button',name='Aggiungi fermata occasionale',exact=True).click()
                    assert page.locator('#occasionalStopDialog').is_visible()
                    assert page.locator('#osSave').is_disabled()
                    page.evaluate('closeOccasionalStopModal()')
                    page.locator('#deliveryTableArea').get_by_role('button',name='Aggiungi cliente',exact=True).click()
                    assert page.locator('#planningCustomerDialog').is_visible()
                    assert page.locator('#customerPlanningStep').is_hidden()
                    page.locator('#planningCustomerSearch').fill('Cliente verificato')
                    page.locator('#planningCustomerResults').get_by_role('button',name='+ Aggiungi',exact=True).first.click()
                    page.wait_for_function('deliveries.length===3 && deliveries[2].customer_id===101')
                    page.evaluate('GFOrderPlanning.beforeCalculate()')
                    assert page.evaluate('deliveries.length===3 && deliveries[2].customer_id===101')
                    assert len(client.get('/api/order-planning/selection').json()['stops'])==3
                    page.locator('#planningCustomerDialog').get_by_role('button',name='Chiudi',exact=True).click()
                    page.locator('#deliveryBody tr').last.get_by_role('button',name='Elimina',exact=True).click()
                    page.evaluate('GFOrderPlanning.flush()')
                    assert page.evaluate("deliveries.length===2 && deliveries.reduce((sum,d)=>sum+d.colli,0)===8")
                    expect(page.locator('#routePlanningActions').get_by_role('button',name='Calcola percorso',exact=True)).to_have_count(1)
                    expect(page.locator('#deliveryWorkbenchStep').get_by_role('button',name='Calcola percorso',exact=True)).to_have_count(0)
                    assert page.locator('#deliveryWorkbenchStep').is_visible()
                    assert page.locator('#customerPlanningStep').is_hidden()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'planning-{width}.png'),full_page=True)
                    page.evaluate("showTab('ordini')")
                    page.wait_for_function("document.querySelector('.order-select')?.checked")
                    page.locator('#ordersSearch').fill('inesistente')
                    page.wait_for_function("document.getElementById('ordersMessage').textContent.includes('Nessun ordine')")
                    page.get_by_role('button',name='Collega i tuoi ordini',exact=True).click()
                    assert page.locator('#tab-ordini-collegamenti').is_visible()
                    # L'importazione da file è nella scheda "File Excel o CSV" (E-commerce non è ancora disponibile).
                    page.locator('[data-source-option]').filter(has=page.get_by_role('heading',name='File Excel o CSV',exact=True)).get_by_role('button',name='Carica un file',exact=True).click()
                    page.locator('#orderImportName').fill('Magazzino <script>test</script>')
                    csv_file={'name':'ordini.csv','mimeType':'text/csv','buffer':b'NOrdine;RagioneSociale;IndSped;Pedana;NColli;DataCons\nIMPORT-001;Destinatario;Via Roma 1;No;3;2099-01-16\n'}
                    page.locator('#orderImportFile').set_input_files(csv_file)
                    page.get_by_role('button',name='Continua',exact=True).click()
                    page.locator('#orderImportCommit').wait_for(state='visible')
                    assert not page.locator('#orderImportMapping').evaluate('(n)=>n.open')
                    date_choice=page.locator('[data-choice="import"][value="requested_date"]')
                    assert page.locator('[data-choice="import"][value="recipient_name"]').is_disabled()
                    date_choice.uncheck()
                    assert page.locator('#orderImportCommit').count()==0
                    page.get_by_role('button',name='Aggiorna anteprima',exact=True).first.click()
                    page.locator('#orderImportCommit').wait_for(state='visible')
                    assert 'Data consegna' not in page.locator('#orderImportPreview').inner_text()
                    date_choice.check()
                    page.get_by_role('button',name='Aggiorna anteprima',exact=True).first.click()
                    page.locator('#orderImportCommit').wait_for(state='visible')

                    assert page.locator('#orderImportWizard script').count()==0
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'import-review-{width}.png'),full_page=True)
                    page.locator('#orderImportCommit').click()
                    page.wait_for_function("document.getElementById('orderImportReport').textContent.includes('Importazione completata')")
                    assert db.query(Order).filter_by(external_id='IMPORT-001').count()==1
                    page.get_by_role('button',name='Importa un altro file',exact=True).click()
                    page.locator('#orderImportFile').set_input_files(csv_file)
                    page.get_by_role('button',name='Continua',exact=True).click()
                    page.locator('#orderImportCommit').wait_for(state='visible')
                    assert 'già presenti' in page.locator('#orderImportReport').inner_text()
                    page.locator('#orderImportCommit').click()
                    page.wait_for_function("document.getElementById('orderImportReport').textContent.includes('Importazione completata')")
                    page.get_by_role('button',name='Vai agli ordini importati',exact=True).click()
                    page.wait_for_function("document.getElementById('ordersResults').textContent.includes('IMPORT-001')")
                    imported=db.query(Order).filter_by(external_id='IMPORT-001').one()
                    imported.status='pronto';imported.address_verification={'input_address':imported.delivery_address,'indirizzo':imported.delivery_address,'stato_geocodifica':'verificato','lat':45.47,'lon':9.2,'geocoding_token':sign_stop_address(user.id,imported.delivery_address,45.47,9.2)}
                    db.commit()
                    page.get_by_role('button',name='Deseleziona',exact=True).click()
                    page.wait_for_function("document.getElementById('ordersSelectionCount').textContent.startsWith('0 ordini')")
                    page.evaluate('GFOrders.load()')
                    page.locator('#ordersView-table').click()
                    select_ready(page)
                    page.wait_for_function("document.getElementById('ordersSelectionCount').textContent.startsWith('1 ordine')")
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.locator('#ordersGoPlanning').click()
                    page.locator('#tab-giro').wait_for(state='visible')
                    expect(page.locator('#orderPlanningBanner')).to_have_count(0)
                    expect(page.locator('#statDeliveries')).to_have_text('1')
                    expect(page.locator('#deliveryBody')).to_contain_text('IMPORT-001')
                    page.locator('#routeDate').fill('2099-01-15')
                    page.locator('#routeStart').fill('08:00')
                    page.locator('#routeStart').blur()
                    page.evaluate('refreshResourceAvailability()')
                    page.wait_for_function("document.getElementById('routeVehicle').options.length > 1")
                    page.locator('#routeVehicle').select_option('1')
                    page.locator('#routeDriver').select_option('1')
                    page.evaluate('updateRouteEnergyPricingV895()')
                    page.locator('#routePlanningActions button').click()
                    page.wait_for_function("document.getElementById('orderPlanningProceedMessage').textContent.includes('16/01/2099')")
                    assert page.locator('#orderPlanningProceedMessage').is_visible()
                    assert page.locator('#routePlanningActions button').is_enabled()
                    page.screenshot(path=str(output/f'planning-error-{width}.png'),full_page=True)
                    page.locator('#routeDate').fill('2099-01-16')
                    page.locator('#routeDate').blur()
                    page.evaluate('refreshResourceAvailability()')
                    page.wait_for_function("document.getElementById('routeVehicle').options.length > 1")
                    page.locator('#routeVehicle').select_option('1')
                    page.locator('#routeDriver').select_option('1')
                    page.evaluate('GFOrderPlanning.beforeCalculate()')
                    assert page.evaluate("id=>deliveries.length===1 && deliveries[0].order_refs[0].id===id", imported.id)
                    assert page.locator('#deliveryWorkbenchStep').is_visible()
                    expect(page.locator('#orderPlanningProceedMessage')).to_be_hidden()
                    assert page.locator('#customerPlanningStep').is_hidden()
                    page.evaluate("showTab('ordini-collegamenti')")
                    page.get_by_role('button',name='Configura gestionale',exact=True).click()
                    page.locator('#sourceName').fill('API gestionale')
                    page.get_by_role('button',name='Crea fonte e prosegui',exact=True).click()
                    page.locator('#tab-ordine-fonte').wait_for(state='visible')
                    page.locator('[data-choice="api"][value="requested_date"]').uncheck()
                    page.get_by_role('button',name='Salva dati da importare',exact=True).click()
                    page.wait_for_function("document.getElementById('sourceFieldsMessage').textContent.includes('Scelte salvate')")
                    page.get_by_role('button',name='Esegui test',exact=False).click()
                    page.wait_for_function("document.getElementById('sourceConnectionResult').textContent.includes('verificato')")
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.get_by_role('button',name='Genera chiave API',exact=True).click()
                    page.locator('#sourceToken').wait_for(state='visible')
                    assert page.locator('#sourceToken').input_value().startswith('gf_orders_')
                    page.evaluate("showTab('ordini')")
                    assert page.locator('#sourceToken').count()==0
                    assert db.query(Order).count()==3
                    # Customers use the same selection-first flow, also without time windows.
                    assert page.locator('.gf-sidebar__item[data-tab="giro"]').count()==0
                    page.evaluate("showTab('clienti');gfUniversalFeaturesV891.has_time_windows=false;applyUniversalFeaturesV891();")
                    box=page.locator('#customerResults input[data-cx-cb="101"]')
                    box.wait_for(state='visible')
                    assert page.locator('#customersGoPlanning').is_hidden()
                    box.check()
                    assert page.locator('#customersGoPlanning').is_visible()
                    assert '(1)' in page.locator('#customersGoPlanning').inner_text()
                    page.locator('#customerResults input[data-cx-cb="102"]').check()
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.locator('#customersGoPlanning').click()
                    assert page.locator('#tab-clienti').is_visible()
                    page.locator('#customerResults input[data-cx-cb="102"]').uncheck()
                    page.once('dialog',lambda dialog:dialog.accept())
                    page.locator('#customersGoPlanning').click()
                    page.wait_for_function("deliveries.length===1 && deliveries[0].customer_id===101")
                    assert page.locator('#tab-giro').is_visible()
                    expect(page.locator('#orderPlanningBanner')).to_have_count(0)
                    assert page.evaluate("deliveries[0].tempo_scarico_min===15")
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                    page.screenshot(path=str(output/f'customer-planning-{width}.png'),full_page=True)
                    page.evaluate("showTab('clienti')")
                    page.locator('#tab-clienti').wait_for(state='visible')
                    assert page.locator('#customerResults input[data-cx-cb="101"]').is_checked()
                    # Lazy verification starts only for the chosen orders, then resolves in one dialog.
                    from unittest.mock import patch
                    from fastapi import HTTPException
                    from app.services import orders as order_service
                    calls=[]
                    def lazy_geocode(db_session,user_id,address,**kwargs):
                        calls.append(address)
                        if address.startswith('Ambiguous'):
                            raise HTTPException(422,{'kind':'address','message':'Indirizzo non verificato correttamente','candidate':{'lat':45.2,'lon':9.2,'formatted':address}})
                        return {'indirizzo':address,'stato_geocodifica':'verificato','lat':45.2,'lon':9.2,'geocoding_token':sign_stop_address(user_id,address,45.2,9.2)}
                    with patch.object(order_service,'verify_stop_address',lazy_geocode):
                        page.evaluate("clearRouteWorkspace();showTab('ordini')")
                        page.evaluate('GFOrderPlanning.clear()')
                        created=[]
                        for number,address in [('AUTO-OK','Via valida 1'),('AUTO-BAD','Ambiguous 1'),('AUTO-UNSELECTED','Via non selezionata')]:
                            created.append(client.post('/api/orders',json={'number':number,'recipient_name':'Destinatario','delivery_address':address}).json())
                        page.evaluate("['ordersSearch','ordersStatus','ordersSource','ordersFrom','ordersTo'].forEach(id=>document.getElementById(id).value='');document.getElementById('ordersSearch').value='AUTO-';GFOrders.load()")
                        for number in ['AUTO-OK','AUTO-BAD']:
                            box=page.get_by_role('checkbox',name='Seleziona ordine '+number,exact=True)
                            box.check();expect(box).to_be_checked();expect(box).to_be_enabled()
                        assert calls==[]
                        page.locator('#ordersGoPlanning').click()
                        page.locator('#selectedAddressesDialog').wait_for(state='visible')
                        assert calls==['Via valida 1','Ambiguous 1']
                        assert client.get('/api/orders/'+str(created[2]['id'])).json()['address_verification'] is None
                        page.locator('#selectedAddressesList').get_by_role('button',name='Correggi o scegli posizione',exact=True).click()
                        page.locator('#selectedAddressText').fill('Via valida 1')
                        page.get_by_role('button',name='Verifica indirizzo corretto',exact=True).click()
                        expect(page.locator('#selectedAddressesContinue')).to_be_enabled()
                        assert len(calls)==2  # The corrected identical address reuses the first proof.
                        page.screenshot(path=str(output/f'address-resolution-{width}.png'),full_page=True)
                        page.locator('#selectedAddressesContinue').click()
                        page.locator('#tab-giro').wait_for(state='visible')
                        assert page.evaluate('deliveries.length')==2
                        assert len(calls)==2
                        page.evaluate("showTab('ordini')")
                        manual=client.post('/api/orders',json={'number':'AUTO-MANUAL','recipient_name':'Manual recipient','delivery_address':'Ambiguous 2'}).json()
                        page.evaluate('GFOrders.load()')
                        box=page.get_by_role('checkbox',name='Seleziona ordine AUTO-MANUAL',exact=True)
                        box.check();expect(box).to_be_enabled()
                        page.once('dialog',lambda dialog:dialog.accept())
                        page.locator('#ordersGoPlanning').click()
                        page.locator('#selectedAddressesDialog').wait_for(state='visible')
                        # Leaflet is stubbed to test the explicit confirmation without external tiles.
                        page.evaluate("""window.L={map:host=>({setView(){return this},on(){return this},remove(){host.replaceChildren()},invalidateSize(){}}),tileLayer:()=>({addTo(){}}),marker:()=>({addTo(){return this},on(){return this},setLatLng(){return this},getLatLng(){return {lat:45.2,lng:9.2}}})};""")
                        page.locator('#selectedAddressesList').get_by_role('button',name='Correggi o scegli posizione',exact=True).click()
                        expect(page.locator('#selectedAddressManual')).to_be_enabled()
                        page.locator('#selectedAddressManual').click()
                        expect(page.locator('#selectedAddressesContinue')).to_be_enabled()
                        result=client.get('/api/orders/'+str(manual['id'])).json()
                        assert result['verification_status']=='manual' and result['address_verification']['confirmed_manually']
                        page.locator('#selectedAddressesContinue').click()
                        page.locator('#tab-giro').wait_for(state='visible')
                        assert page.evaluate('deliveries.length')==3
                    assert not errors,errors
                    context.close()
            engine.dispose()
        browser.close()
    print('Orders: create, edit, escaping, filters, independent orders, persisted selection, immediate planning stops and bottom calculation action, three-step file import, repeat without duplicates, imported-order planning errors and recovery, current API setup, credential clearing and layout passed at 390/768/1024/1440px')

if __name__=='__main__':main()
