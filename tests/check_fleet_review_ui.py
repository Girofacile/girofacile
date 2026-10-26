"""Fleet review page ("Controlla la suddivisione", variante C) in Chromium with a synthetic plan.

Renders GFFleetReview directly; no API writes. Screenshots go to test-results/fleet-review-ui.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from check_management_design import ME

STOPS = [
    ('Caffetteria La Corte', 'Via Roma 32, Giugliano in Campania', 40.928, 14.195, dict(sponda=True)),
    ('Bar Zi Teresa', 'Corso Garibaldi 60, Portici', 40.815, 14.339, {}),
    ('Bistrot Luna', 'Via Santa Lucia 7, Napoli', 40.833, 14.247, {}),
    ('Trattoria Aurora', 'Via Duomo 82, Napoli', 40.852, 14.259, dict(ztl=True)),
    ('Bar Mergellina', 'Corso Umberto I 55, Napoli', 40.847, 14.262, {}),
    ('Hotel Capri Palace', 'Via Provinciale 2, Anacapri', 40.553, 14.216, {}),
]


def plan():
    consegne = [dict(cliente_nome=n, indirizzo=a, lat=la, lon=lo, **f) for n, a, la, lo, f in STOPS]
    route = lambda res, idx, km, cost, back, extra=None: dict(
        resource=res, stop_indexes=idx, fuel_cost=cost, vehicle_name=['Iveco Daily', 'Renault Master'][res],
        driver_name=['Ciro Esposito', 'Salvatore De Luca'][res],
        result=dict(total_km=km, total_min=200, return_time=back, depot_coord=dict(lat=40.882, lon=14.300),
                    ordered=[dict(arrivo_stimato=f'{8 + j:02d}:15', lat=consegne[i]['lat'], lon=consegne[i]['lon']) for j, i in enumerate(idx)]),
        traffic=extra)
    late = dict(status='updated', total_min=230, return_time='12:40',
                late=[dict(stop_index=2, fine_servizio='10:22', lateness_min=22, window=dict(start='07:00', end='10:00'))])
    return dict(id=7, version=1, status='preview', warnings=[],
                configuration=dict(consegne=consegne, resources=[dict(vehicle_id=1, driver_id=1), dict(vehicle_id=2, driver_id=2)]),
                resource_capabilities=[dict(has_tail_lift=False, has_ztl_access=True), dict(has_tail_lift=True, has_ztl_access=False)],
                routes=[route(0, [0, 1, 2], 64.8, 31.2, '12:35', late), route(1, [3, 4], 52.1, 26.4, '12:10')],
                unassigned=[dict(index=5, reason='Nessun mezzo arriva entro la fascia 09:00–11:00.')])


def main():
    output = ROOT / 'test-results' / 'fleet-review-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={'width': width, 'height': height})
                page.on('pageerror', lambda e: errors.append(str(e)))

                def handle(route):
                    parsed = urlparse(route.request.url)
                    path = parsed.path
                    if parsed.hostname in ('unpkg.com', 'tile.openstreetmap.org'):
                        route.continue_(); return
                    if parsed.hostname != 'fleet-review.test':
                        route.abort(); return
                    if not path.startswith('/api/'):
                        file = (ROOT / ('static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/'))).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    if path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS={}'); return
                    data = {'/api/me': {'authenticated': False},
                            '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[])}
                    route.fulfill(json=data.get(path, [] if path.rstrip('/').split('/')[-1] in ('vehicles', 'drivers', 'deposits', 'customers', 'agents', 'routes') else {}))

                page.route('**/*', handle)
                page.goto('http://fleet-review.test/dashboard', wait_until='domcontentloaded')
                page.wait_for_function('window.GFFleetReview && typeof showTab==="function"')
                page.evaluate("owner=>{currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();document.getElementById('onboardingOverlay')?.classList.add('hidden');showTab('route-preview');}", ME)
                page.evaluate('''p=>{window.__moves=[];window.__params={plan:p,assignment:[0,0,0,1,1,null],dirty:false,busy:false,manualAdjusted:false,permission:true,
                    onMove:(i,to)=>{GFFleetReview.warning(()=>window.__moves.push([i,to]));},onUndo(){},onRecalc(){},onPlan(){},onBack(){}};
                    GFFleetReview.render(window.__params);}''', plan())
                review = page.locator('[data-fleet-review]')
                review.get_by_role('heading', name='Confronto dei giri').wait_for()
                assert review.locator('tbody tr[data-fleet-lane]').count() == 2
                # Come le altre pagine: titolo, freccia indietro e "Pianifica giri" nella barra in alto.
                assert page.locator('#workspacePageTitle').inner_text() == 'Controlla la suddivisione'
                assert page.locator('#workspacePageTitle').is_visible() or width < 1000
                assert page.locator('#workspaceTopbarBack').is_visible()
                assert page.locator('#fleetTopbarActionsHost [data-fleet-plan]').is_visible()
                assert review.locator('h1, [data-fleet-back]').count() == 0
                # Niente avvisi grandi in alto: fuori orario e non assegnate sono solo in "Da sistemare".
                assert review.locator(':scope > .gf-alert').count() == 0
                # Giro 1 scelto: tre fermate, avvisi come etichette sulla fermata.
                assert review.locator('.gf-stop[data-fleet-stop]').count() == 3
                assert review.locator('[data-fleet-warning="tail-lift"]').count() == 1
                assert review.locator('[data-fleet-warning="late"]').count() == 1
                # "Da sistemare": solo la non assegnata e la fuori orario.
                fixes = review.locator('.gf-list .gf-list-item')
                assert fixes.count() == 2, fixes.all_inner_texts()
                assert review.locator('.gf-list [data-fleet-warning]').count() == 0
                assert review.locator('[data-fleet-assign="5"]').inner_text() == 'Assegna al giro 1'
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                # Mappa: tutti i giri, quello scelto in evidenza (Leaflet da unpkg, come in produzione).
                review.locator('[data-fleet-pin]').first.wait_for(timeout=20000)
                assert review.locator('[data-fleet-pin]').count() == 5
                page.wait_for_timeout(1500)
                page.screenshot(path=str(output / f'suddivisione-{width}.png'), full_page=True)

                # Vedi giro 2: cambia il giro mostrato e l'etichetta del pulsante Assegna.
                review.locator('[data-fleet-select="1"]').click()
                assert review.locator('[data-fleet-select="1"]').get_attribute('aria-pressed') == 'true'
                assert review.locator('.gf-stop[data-fleet-stop]').count() == 2
                assert review.locator('[data-fleet-warning="ztl"]').count() == 1
                assert review.locator('[data-fleet-assign="5"]').inner_text() == 'Assegna al giro 2'
                review.locator('[data-fleet-assign="5"]').click()
                page.get_by_role('button', name='Sposta comunque', exact=True).click()
                assert page.evaluate('window.__moves') == [[5, 1]]
                # Dopo uno spostamento: nessun avviso in alto, solo la barra in basso con "Ripianifica giri".
                page.evaluate('() => GFFleetReview.render({...window.__params, assignment:[0,1,0,1,1,null], dirty:true, manualAdjusted:true})')
                assert review.locator(':scope > .gf-alert').count() == 0
                bar = review.locator('.gf-savebar')
                assert bar.is_visible() and bar.get_by_role('button', name='Ripianifica giri').is_visible()
                assert page.locator('#fleetTopbarActionsHost [data-fleet-plan]').is_disabled()
                page.screenshot(path=str(output / f'suddivisione-spostata-{width}.png'))
                page.evaluate('() => GFFleetReview.render(window.__params)')
                if width > 1000:
                    # Trascinamento di una fermata sulla riga di un altro giro.
                    review.locator('.gf-stop[data-fleet-stop="3"] [data-fleet-drag]').drag_to(review.locator('tbody tr[data-fleet-lane="0"]'))
                    page.get_by_role('button', name='Sposta comunque', exact=True).click()
                    assert page.evaluate('window.__moves') == [[5, 1], [3, 0]]
                    page.screenshot(path=str(output / f'suddivisione-giro2-{width}.png'), full_page=True)
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: fleet review at 390/1440 — comparison table, selected route, fixes list, assign and drag')


if __name__ == '__main__':
    main()
