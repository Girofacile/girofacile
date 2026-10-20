"""Flusso completo ordine → giro nel browser: selezione, pianificazione, anteprima, programmazione.

Usa l'API reale (ordini, pianificazione, giri, mezzi, autisti, depositi) su un database
isolato, l'ottimizzatore vero e i provider stradali simulati di routing_env. Nessuna
chiamata esterna, nessuna email (l'autista non ha indirizzo).
Esecuzione: python tests/check_route_flow_e2e.py
"""
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tests'))
os.environ['DATABASE_URL'] = 'sqlite://'; os.environ['ALLOW_SQLITE_LEGACY'] = 'true'
from playwright.sync_api import expect, sync_playwright
from pytest import MonkeyPatch
from test_agents_feature import env
from test_routing_architecture import routing_env
from test_order_planning import planning, ready
from check_management_design import ME, LIMITS, USAGE
from check_orders_ui import select_ready

API_PREFIXES = ('/api/orders', '/api/order-planning', '/api/routes', '/api/resources',
                '/api/vehicles', '/api/drivers', '/api/deposits', '/api/driver/')
DRIVER_PASSWORD = 'E2e-Collaudo-9x!'
# Numeri con il punto decimale accanto a un'unità: nel gestionale vanno con la virgola.
DOT_DECIMAL = re.compile(r'\b\d+\.\d+\s?(km|kWh|L|kg|min)\b|€\s?\d+\.\d')
WRONG_PLURAL = re.compile(r'\b1 (fermate|consegne|ordini|colli|mezzi)\b')
# Leaflet arriva da CDN: in un test isolato lo sostituiamo con un oggetto inerte.
LEAFLET_STUB = """window.L={map:h=>({setView(){return this},fitBounds(){return this},on(){return this},remove(){h.replaceChildren()},invalidateSize(){},addLayer(){return this},getZoom(){return 9}}),
tileLayer:()=>({addTo(){return this},on(){return this}}),marker:()=>({addTo(){return this},on(){return this},bindPopup(){return this},bindTooltip(){return this},setLatLng(){return this}}),
divIcon:()=>({}),polyline:()=>({addTo(){return this},getBounds(){return {}}}),latLngBounds:()=>({extend(){return this},isValid(){return true},pad(){return this}}),
circleMarker:()=>({addTo(){return this},bindTooltip(){return this}}),featureGroup:()=>({addTo(){return this},getBounds(){return {isValid:()=>true}}}),control:{scale:()=>({addTo(){}})}};"""


def check_text(label, text):
    assert not DOT_DECIMAL.search(text), f'{label}: decimale con il punto → {DOT_DECIMAL.search(text).group(0)!r}'
    assert not WRONG_PLURAL.search(text), f'{label}: plurale errato → {WRONG_PLURAL.search(text).group(0)!r}'
    assert not re.search(r'\b\d{4}-\d{2}-\d{2}\b', text), f'{label}: data in formato ISO'


def run(browser, width, output):
    with MonkeyPatch.context() as mp:
        # Il generatore va conservato: se venisse raccolto, chiuderebbe la sessione del database.
        generator = env.__wrapped__(mp, output)
        base = next(generator)
        ctx = routing_env.__wrapped__(base, mp)
        planning_ctx, driver = planning.__wrapped__(ctx)
        client, db, owner, _, _, depot, vehicle, _ = planning_ctx
        from app.routers import vehicles_drivers
        client.app.include_router(vehicles_drivers.vehicles_router)
        client.app.include_router(vehicles_drivers.drivers_router)
        from app.models import RoutePlan
        from app.order_models import Order
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        order = ready(planning_ctx, 'E2E-1', packages=1, weight_kg=12.5, requested_date=tomorrow)
        ready(planning_ctx, 'E2E-2', delivery_address='Second address', packages=2, weight_kg=8, requested_date=tomorrow)

        page = browser.new_page(viewport={'width': width, 'height': 900})
        errors, api_failures = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.add_init_script(LEAFLET_STUB)

        def handle(route):
            parsed = urlparse(route.request.url); path = parsed.path
            if parsed.hostname != 'flow.test':
                route.abort(); return
            if path.startswith(API_PREFIXES):
                response = client.request(route.request.method, path + ('?' + parsed.query if parsed.query else ''),
                                          content=route.request.post_data_buffer,
                                          headers={'Content-Type': route.request.headers.get('content-type', 'application/json')})
                if response.status_code >= 400:
                    api_failures.append(f'{response.status_code} {route.request.method} {path}: {response.text[:200]}')
                route.fulfill(status=response.status_code, body=response.text, content_type='application/json'); return
            if path == '/api/billing/catalog.js':
                route.fulfill(content_type='application/javascript',
                              body='window.GF_PLANS=' + json.dumps({k: dict(LIMITS, name=k, price_eur=29) for k in ('starter', 'business', 'pro')})); return
            if not path.startswith('/api/'):
                file = (ROOT / {'/dashboard': 'static/dashboard/index.html', '/driver': 'static/driver/index.html'}.get(path, path.lstrip('/'))).resolve()
                if file.is_relative_to(ROOT) and file.is_file(): route.fulfill(path=str(file))
                else: route.fulfill(status=404, body='')
                return
            stub = {'/api/me': ME, '/api/settings': {}, '/api/sector-config': {}, '/api/customers': [],
                    '/api/agents': [], '/api/vehicles/usage': USAGE,
                    '/api/notifications': {'items': [], 'unread': 0}, '/api/notifications/count': {'unread': 0},
                    '/api/driver/admin/chat-threads': [], '/api/driver/admin/unread': {'total': 0, 'routes': []},
                    '/api/onboarding/status': {'completed': True, 'workspace_operational': True, 'steps': []}}.get(path, {})
            route.fulfill(json=stub)

        page.route('**/*', handle)
        page.goto('http://flow.test/dashboard', wait_until='networkidle')
        # Login reale: /api/me risponde come titolare autenticato e l'app esegue initApp().
        page.wait_for_function('typeof vehiclesCache!=="undefined" && vehiclesCache.length>0')
        page.evaluate("acceptCookieNotice();showTab('ordini')")

        # 1. Selezione dell'ordine pronto e passaggio alla pianificazione.
        page.wait_for_function("document.getElementById('ordersResults').textContent.includes('E2E-1')")
        select_ready(page)
        page.locator('#ordersGoPlanning').click()
        dialog = page.locator('#selectedAddressesDialog')
        page.wait_for_function("document.getElementById('tab-giro').offsetParent || document.getElementById('selectedAddressesDialog').open")
        if dialog.is_visible():
            page.locator('#selectedAddressesContinue').click()
        page.locator('#tab-giro').wait_for(state='visible')
        assert page.input_value('#routeDate') == tomorrow, 'la data proposta deve essere quella richiesta dall’ordine'

        # 2. Configurazione: orario, mezzo, autista.
        page.fill('#routeStart', '08:00'); page.locator('#routeStart').dispatch_event('change')
        try:
            expect(page.locator('#routeVehicle')).to_be_enabled()
        except AssertionError:
            raise AssertionError(f'mezzo non selezionabile; errori={errors} api={api_failures} '
                                 f'start={page.input_value("#routeStart")!r} date={page.input_value("#routeDate")!r}')
        page.select_option('#routeVehicle', str(vehicle.id))
        page.select_option('#routeDriver', str(driver.id))
        page.get_by_role('button', name='Calcola percorso', exact=True).click()

        # 3. Anteprima: contenuti e formati.
        preview = page.locator('#tab-route-preview')
        preview.wait_for(state='visible')
        expect(preview).to_contain_text('2 fermate pianificate')
        check_text('anteprima', preview.inner_text())
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'scroll orizzontale in anteprima'
        page.screenshot(path=str(output / f'preview-{width}.png'), full_page=True)

        # 4. Programmazione: giro programmato, ordine assegnato, selezione svuotata.
        page.get_by_role('button', name='Programma giro', exact=True).click()
        page.locator('#tab-dashboard-scheduled').wait_for(state='visible')
        route = db.query(RoutePlan).one()
        db.refresh(route)
        assert route.status == 'programmato', route.status
        expect(page.locator('#tab-dashboard-scheduled')).to_contain_text(route.nome)
        check_text('giri programmati', page.locator('#tab-dashboard-scheduled').inner_text())
        # 5. Dettaglio del giro programmato a pagina intera: barra con icone, mappa, fermate, tabella.
        page.locator('#tab-dashboard-scheduled').get_by_role('button', name='Apri giro').first.click()
        detail = page.locator('[data-scheduled-detail]')
        detail.wait_for(state='visible')
        assert detail.locator('.gf-stat-strip[data-icons="side"] .gf-stat-strip__icon').count() == 5
        assert detail.locator('[data-route-map]').count() == 1
        expect(detail.locator('.gf-stop-list')).to_contain_text('Recipient')
        table = detail.locator('#scheduledStopsTable')
        expect(table).to_be_hidden()
        detail.get_by_role('button', name='Mostra tabella').click()
        expect(table).to_be_visible()
        check_text('dettaglio giro programmato', detail.inner_text())
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'scroll orizzontale nel dettaglio'
        page.screenshot(path=str(output / f'scheduled-detail-{width}.png'), full_page=True)
        back = page.locator('#workspaceTopbarBack')
        expect(back).to_have_attribute('aria-label', 'Torna ai giri programmati')
        back.click()
        page.locator('#tab-dashboard-scheduled [data-cols="7"]').wait_for(state='visible')
        db.refresh(order)
        assert client.get('/api/order-planning/selection').json()['order_ids'] == [], 'selezione non svuotata'
        page.evaluate("showTab('ordini')")
        page.wait_for_function("document.getElementById('ordersResults').textContent.includes('Assegnato')")
        expect(page.locator('#ordersSelection')).to_be_hidden()
        page.screenshot(path=str(output / f'scheduled-{width}.png'), full_page=True)

        # 6. Portale autista (telefono): prima dell'avvio solo "Avvia giro", poi esiti, chiusura e storico.
        if width <= 400:
            from datetime import time as dtime
            from app.models import DriverAccount
            from app.core.security import hash_password
            from app.routers import driver as driver_routes
            client.app.include_router(driver_routes.router)
            driver.email = 'autista@e2e.test'
            db.add(DriverAccount(driver_id=driver.id, email=driver.email, password_hash=hash_password(DRIVER_PASSWORD), is_active=True))
            # Il giro passa a oggi alle 23:59: avviabile, ma "in anticipo" (serve la conferma).
            route.data_giro = date.today(); route.orario_partenza = dtime(23, 59)
            db.commit()
            dialogs = []
            page.on('dialog', lambda d: (dialogs.append(d.message), d.accept()))
            # Accesso reale dell'autista (la pagina di login è comune ai portali): il cookie resta nel client.
            login = client.post('/api/driver/login', json={'email': driver.email, 'password': DRIVER_PASSWORD})
            assert login.status_code == 200, login.text
            page.goto('http://flow.test/driver', wait_until='networkidle')
            expect(page.locator('#dashDriverName')).to_contain_text('ecco i giri assegnati a te')
            detail_api = client.get(f'/api/driver/routes/{route.id}').json()['route']
            assert not {'costo_totale', 'costo_carburante', 'toll_estimated_eur'} & detail_api.keys(), 'costi esposti all’autista'
            page.get_by_role('button', name='Dettaglio').first.click()
            start = page.get_by_role('button', name='▶ Avvia giro per registrare le consegne')
            expect(start).to_be_visible()
            assert page.get_by_role('button', name='Consegnato', exact=True).count() == 0, 'esiti disponibili prima dell’avvio'
            start.click()
            expect(page.locator('#popupEarly')).to_be_visible()
            page.locator('#popupConfirmBtn').click()
            assert page.locator('.gf-routing-costs').count() == 0, 'costi visibili nel portale autista'
            page.get_by_role('button', name='Consegnato', exact=True).click()
            expect(page.locator('#modalDone .gf-upload[data-pod-photo]')).to_be_visible()
            # Validazione nello stile del gestionale, dentro la finestra (nessun avviso del browser).
            page.get_by_role('button', name='Conferma consegna').click()
            expect(page.locator('#modalDone [data-portal-notice]')).to_contain_text('Seleziona il tempo di scarico')
            page.screenshot(path=str(output / f'driver-done-modal-{width}.png'))
            page.get_by_role('button', name='10 min').first.click()
            page.get_by_role('button', name='Conferma consegna').click()
            page.get_by_role('button', name='Mancata', exact=True).click()
            page.get_by_role('button', name='Cliente assente').click()
            page.get_by_role('button', name='Conferma mancata consegna').click()
            expect(page.get_by_text('Giro completato!')).to_be_visible()
            db.refresh(route)
            assert route.status == 'completato', route.status
            page.get_by_role('button', name='Storico').click()
            history = page.locator('body')
            expect(history).to_contain_text('1 consegnata')
            expect(history).to_contain_text('1 mancata')
            check_text('storico autista', history.inner_text())
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'scroll orizzontale nel portale autista'
            assert not dialogs, dialogs
            page.screenshot(path=str(output / f'driver-history-{width}.png'), full_page=True)

        assert not errors, errors
        assert not api_failures, api_failures
        page.close()


def main():
    output = ROOT / 'test-results' / 'route-flow-e2e'; output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, channel=os.getenv('GF_TEST_BROWSER_CHANNEL') or None)
        for width in (1280, 390):
            run(browser, width, output)
        browser.close()
    print('Flusso ordine → giro → autista: selezione, data richiesta, configurazione, anteprima (formati e plurali), '
          'programmazione, dettaglio del giro, avvio dal portale autista, consegna, mancata, chiusura e storico '
          'superati a 1280 e 390px')


if __name__ == '__main__':
    main()
