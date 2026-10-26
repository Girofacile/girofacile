"""Planning page in Chromium: with "Più mezzi" the fuel cost box disappears (costs live in the vehicle cards).

All responses are synthetic; nothing is written. Screenshots go to test-results/fleet-fuel-ui.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from app.services.plan_catalog import PLAN_LIMITS, PLAN_PRICES
from check_management_design import ME

CATALOGUE = {key: dict(value, price_eur=PLAN_PRICES[key]['price_eur']) for key, value in PLAN_LIMITS.items()}
VEHICLES = [dict(id=1, nome='Peugeot 2008', alimentazione='benzina', consumo_l_100km=8.5, available=True),
            dict(id=2, nome='Peugeot Expert', alimentazione='gasolio', consumo_l_100km=9, available=True)]
DRIVERS = [dict(id=1, nome='Alessandro', cognome='Paglietta', full_name='Alessandro Paglietta', available=True),
           dict(id=2, nome='Samuele', cognome='Siviglia', full_name='Samuele Siviglia', available=True)]


def main():
    output = ROOT / 'test-results' / 'fleet-fuel-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={'width': width, 'height': height})
                page.on('pageerror', lambda e: errors.append(str(e)))
                owner = dict(ME, plan='business', plan_status='active', limits=PLAN_LIMITS['business'], authenticated=True)

                def handle(route):
                    parsed = urlparse(route.request.url)
                    path = parsed.path
                    if parsed.hostname != 'fuel.test':
                        route.abort(); return
                    if path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                    if not path.startswith('/api/'):
                        file = (ROOT / ('static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/'))).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    data = {'/api/me': owner, '/api/vehicles': VEHICLES, '/api/drivers': DRIVERS,
                            '/api/resources/availability': dict(vehicles=VEHICLES, drivers=DRIVERS),
                            '/api/vehicles/fuel-prices/current': dict(benzina=dict(price=2.042), gasolio=dict(price=1.9)),
                            '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[])}
                    route.fulfill(json=data.get(path, [] if path.rstrip('/').split('/')[-1] in ('deposits', 'customers', 'agents', 'routes') else {}))

                page.route('**/*', handle)
                page.goto('http://fuel.test/dashboard', wait_until='networkidle')
                page.evaluate('async () => { acceptCookieNotice(); await checkLogin(); document.getElementById("onboardingOverlay")?.classList.add("hidden"); showTab("giro"); }')
                page.evaluate('v => { vehiclesCache = v; resourcesAvailabilityCache = {vehicles: v, drivers: []}; }', VEHICLES)
                page.locator('#routeDate').fill('2099-01-15'); page.locator('#routeStart').fill('08:00'); page.locator('#routeStart').blur()
                page.evaluate('refreshResourceAvailability()')
                page.locator('#routeVehicle option[value="1"]').wait_for(state='attached')
                page.locator('#routeVehicle').select_option('1')
                box = page.locator('#routeEnergyPriceBoxV895')
                fuel = page.locator('#statFuelGroup')
                assert box.is_visible() and fuel.is_visible()
                page.locator('[data-planning-mode-card="fleet"]').click()
                assert page.locator('#planningMode').input_value() == 'fleet'
                # Più mezzi: niente riquadro costo né prezzo nella barra; la mappa prende tutta la riga.
                assert box.is_hidden() and fuel.is_hidden()
                assert page.locator('#statDeliveries').is_visible()
                map_panel = page.locator('section[aria-labelledby="planningMapTitle"]')
                grid_width = map_panel.evaluate('el => el.parentElement.getBoundingClientRect().width')
                assert abs(map_panel.bounding_box()['width'] - grid_width) < 2, (map_panel.bounding_box()['width'], grid_width)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                map_panel.scroll_into_view_if_needed()
                page.screenshot(path=str(output / f'piu-mezzi-{width}.png'))
                page.locator('[data-planning-mode-card="single"]').click()
                state = page.evaluate('[document.getElementById("routeVehicle").value, document.getElementById("routeEnergyPriceBoxV895").className, document.getElementById("statFuelGroup").hidden]')
                assert box.is_visible() and fuel.is_visible(), state
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: fuel cost box only with one vehicle; fleet mode keeps costs in the vehicle cards (390/1440)')


if __name__ == '__main__':
    main()
