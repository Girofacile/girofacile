"""Tutor del primo giro in Chromium a 1440 px: barra verde, fumetto sul prossimo clic,
attesa sul pulsante di salvataggio con scritte rosse sui campi obbligatori, avanzamento
dai dati salvati, fine al primo giro programmato, uscita e ripresa salvate sul server.

Le API sono simulate in memoria (nessun dato reale). Schermate in test-results/tutor-ui.
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
LISTS = ('customers', 'agents', 'operativi', 'routes')
LABELS = (('company', 'Profilo azienda'), ('deposit', 'Deposito di partenza'), ('vehicle', 'Il primo mezzo'),
          ('driver', 'Un autista'), ('orders', 'Le consegne'), ('route', 'Calcolo del giro'), ('program', 'Programmazione'))


def tutor(store):
    done = dict(company=store.get('company', True), deposit=bool(store['deposits']), vehicle=bool(store['vehicles']), driver=bool(store['drivers']),
                orders=store['orders'] > 0, route=store['route'] is not None, program=store['route'] == 'programmato')
    if done['program']:
        store['state'] = 'completato'
    steps = [dict(key=k, label=label, done=done[k]) for k, label in LABELS]
    current = next((s['key'] for s in steps if not s['done']), None)
    return dict(state=store['state'], steps=steps, current=current, progress=sum(done.values()), total=7)


def open_dashboard(browser, store, errors):
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.on('pageerror', lambda e: errors.append(str(e)))
    owner = dict(ME, plan='business', plan_status='active', limits=PLAN_LIMITS['business'], authenticated=True,
                 company_address='Via Emilia 112, Bologna', onboarding_completed=False)

    def handle(route):
        parsed = urlparse(route.request.url)
        path, method = parsed.path, route.request.method
        if parsed.hostname != 'tutor.test':
            route.abort(); return
        if path == '/api/billing/catalog.js':
            route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
        if not path.startswith('/api/'):
            file = (ROOT / ('static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/'))).resolve()
            route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
            return
        body = json.loads(route.request.post_data or '{}') if method != 'GET' else {}
        if path == '/api/onboarding/tutor':
            if method == 'POST' and store['state'] != 'completato':
                store['state'] = 'chiuso' if body['action'] == 'close' else 'attivo'
                store['tutor_posts'].append(body['action'])
            route.fulfill(json=tutor(store)); return
        if path == '/api/onboarding/status':
            route.fulfill(json=dict(completed=False, dismissed=False, tutor_pending=store['state'] != 'completato',
                                    workspace_operational=True, steps=[], progress=0, total=2, percent=0)); return
        for kind in ('deposits', 'vehicles', 'drivers'):
            if path == f'/api/{kind}':
                if method == 'POST':
                    item = dict(body, id=len(store[kind]) + 1, stato='Disponibile', predefinito=True)
                    store[kind].append(item); route.fulfill(json=item); return
                route.fulfill(json=store[kind]); return
        if path == '/api/planning-drafts':
            drafts = [dict(id=1, source='orders', name='Giro del 30/10', data_giro='2026-10-30', planning_mode='single', vehicles=1,
                           stops=3, orders=3, stage='anteprima', fleet_plan_id=None, updated_at='2026-10-29T10:00:00')] if store['route'] == 'bozza' else []
            route.fulfill(json=dict(drafts=drafts, routes=[])); return
        data = {'/api/me': owner, '/api/resources/availability': dict(vehicles=[], drivers=[]),
                '/api/order-planning/selection': dict(version=1, order_ids=[], configuration={}, stops=None, routes=[]),
                '/api/orders': dict(items=[], total=0, page=1, page_size=25, counts={}, metrics={})}
        route.fulfill(json=data.get(path, [] if path.rstrip('/').split('/')[-1] in LISTS else {}))

    page.route('**/*', handle)
    page.goto('http://tutor.test/dashboard', wait_until='networkidle')
    page.evaluate('async () => { acceptCookieNotice(); await checkLogin(); }')
    return page


def tip_on(page, selector):
    """Il fumetto è aperto e agganciato all'elemento indicato."""
    page.wait_for_function('s => document.querySelector(s)?.hasAttribute("data-gf-tutor-target") && document.getElementById("coachTip").matches(":popover-open")', arg=selector)
    return page.locator('#coachTitle').inner_text()


def near(page, selector):
    """Il fumetto sta accanto all'elemento (entro 80 px), non in un angolo della pagina."""
    return page.evaluate('''s => { const a=document.querySelector(s).getBoundingClientRect(), t=document.getElementById("coachTip").getBoundingClientRect();
      const gapX=Math.max(0,t.left-a.right,a.left-t.right), gapY=Math.max(0,t.top-a.bottom,a.top-t.bottom); return gapX<80 && gapY<80; }''', selector)


def main():
    output = ROOT / 'test-results' / 'tutor-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            store = dict(state='attivo', deposits=[], vehicles=[], drivers=[], orders=0, route=None, tutor_posts=[])
            page = open_dashboard(browser, store, errors)
            # Account nuovo: barra verde in alto e fumetto sulla voce "Depositi"; nessuna finestra di configurazione.
            assert 'Depositi' in tip_on(page, '#app .gf-sidebar__item[data-tab="depositi"]')
            assert page.locator('#coachBar').is_visible() and 'Passo 2 di 7' in page.locator('#coachBar').inner_text()
            assert near(page, '#app .gf-sidebar__item[data-tab="depositi"]')
            assert page.locator('#onboardingOverlay').is_hidden()
            page.screenshot(path=str(output / '1-barra-e-fumetto.png'))

            # Deposito: voce -> "Nuovo deposito" -> il fumetto aspetta su "Salva deposito".
            page.locator('#app .gf-sidebar__item[data-tab="depositi"]').click()
            tip_on(page, '#newDepositBtn')
            page.locator('#newDepositBtn').click()
            assert 'Salva deposito' in tip_on(page, '#saveDepositBtn')
            page.locator('#saveDepositBtn').click()
            # Campi obbligatori vuoti: scritte rosse nei campi, nessun salvataggio.
            page.locator('#depNome').locator('xpath=ancestor::label[@data-invalid]').wait_for()
            assert page.locator('#depositForm .gf-field[data-invalid] .gf-field__error').first.inner_text() == 'Campo obbligatorio'
            assert not store['deposits']
            page.screenshot(path=str(output / '2-deposito-campi-obbligatori.png'))
            page.fill('#depNome', 'Magazzino centrale')
            page.fill('#depIndirizzo', 'Via Emilia 112, Bologna')
            page.locator('#saveDepositBtn').click()
            # Salvato davvero: il passo si spunta da solo e il fumetto passa ai mezzi.
            assert 'Mezzi' in tip_on(page, '#app .gf-sidebar__item[data-tab="mezzi"]')
            assert 'Passo 3 di 7' in page.locator('#coachBar').inner_text()

            # Mezzo: la finestra laterale è in primo piano, il fumetto le sta sopra sul pulsante "Salva mezzo".
            page.locator('#app .gf-sidebar__item[data-tab="mezzi"]').click()
            tip_on(page, '#newVehicleBtn')
            page.screenshot(path=str(output / '3-nuovo-mezzo.png'))
            page.locator('#newVehicleBtn').click()
            assert 'Salva mezzo' in tip_on(page, '#saveVehicleBtn')
            assert near(page, '#saveVehicleBtn')
            page.locator('#saveVehicleBtn').click()
            page.locator('#vNome').locator('xpath=ancestor::label[@data-invalid]').wait_for()
            assert not store['vehicles']
            page.screenshot(path=str(output / '4-mezzo-salva.png'))
            page.fill('#vNome', 'Furgone bianco')
            assert page.locator('#vNome').locator('xpath=ancestor::label[@data-invalid]').count() == 0
            page.locator('#saveVehicleBtn').click()
            assert 'Autisti' in tip_on(page, '#app .gf-sidebar__item[data-tab="autisti"]')

            # Autista.
            page.locator('#app .gf-sidebar__item[data-tab="autisti"]').click()
            tip_on(page, '#newDriverBtn')
            page.locator('#newDriverBtn').click()
            tip_on(page, '#saveDriverBtn')
            page.locator('#saveDriverBtn').click()
            page.locator('#drNome').locator('xpath=ancestor::label[@data-invalid]').wait_for()
            page.fill('#drNome', 'Marco')
            page.locator('#saveDriverBtn').click()
            assert 'Ordini' in tip_on(page, '#app .gf-sidebar__item[data-tab="ordini"]')
            page.locator('#app .gf-sidebar__item[data-tab="ordini"]').click()
            assert 'Nuovo ordine' in tip_on(page, '#ordersNew')
            page.screenshot(path=str(output / '5-ordini.png'))

            # Ordine e calcolo simulati nel server finto: in pianificazione il fumetto indica "Calcola percorso".
            store['orders'] = 1
            page.evaluate('GFTutor.refresh()')
            page.evaluate('showTab("giro")')
            assert 'Calcola percorso' in tip_on(page, '#routeCalculateBtn')
            store['route'] = 'bozza'
            page.evaluate('async () => { await GFTutor.refresh(); showTab("dashboard"); }')
            assert 'bozza' in tip_on(page, '#sidebarDraftsItem')

            # Primo giro programmato: congratulazioni, poi la guida si chiude e non torna più.
            store['route'] = 'programmato'
            page.evaluate('GFTutor.refresh()')
            page.wait_for_function('document.getElementById("coachTitle").textContent.includes("Complimenti")')
            assert '7 di 7' in page.locator('#coachBar').inner_text()
            page.screenshot(path=str(output / '6-primo-giro-programmato.png'))
            page.locator('#coachDone').click()
            page.wait_for_function('!document.getElementById("coachBar").matches(":popover-open")')
            page.close()
            page = open_dashboard(browser, store, errors)
            page.wait_for_timeout(500)
            assert page.locator('#coachBar').is_hidden() and page.locator('#coachTip').is_hidden()
            page.close()

            # Profilo incompleto: «Azienda» sta nel gruppo chiuso del menu, il fumetto indica prima il gruppo.
            store = dict(state='attivo', company=False, deposits=[], vehicles=[], drivers=[], orders=0, route=None, tutor_posts=[])
            page = open_dashboard(browser, store, errors)
            group = '#app details[data-sidebar-group="sistema"] > summary'
            assert page.evaluate('!document.querySelector(`#app details[data-sidebar-group="sistema"]`).open')
            assert 'Azienda e sistema' in tip_on(page, group) and near(page, group)
            page.screenshot(path=str(output / '0-gruppo-menu-chiuso.png'))
            page.locator(group).click()
            assert 'Azienda' in tip_on(page, '#app .gf-sidebar__item[data-tab="company"]')
            assert near(page, '#app .gf-sidebar__item[data-tab="company"]')
            page.locator('#app .gf-sidebar__item[data-tab="company"]').click()
            assert 'sede' in tip_on(page, '#companyAddressInput')
            page.close()

            # Uscita: confermata, salvata sul server; non ricompare e si riprende da Azienda.
            store = dict(state='attivo', deposits=[], vehicles=[], drivers=[], orders=0, route=None, tutor_posts=[])
            page = open_dashboard(browser, store, errors)
            tip_on(page, '#app .gf-sidebar__item[data-tab="depositi"]')
            page.once('dialog', lambda d: d.accept())
            page.locator('#coachExit').click()
            page.wait_for_function('!document.getElementById("coachBar").matches(":popover-open")')
            assert store['tutor_posts'] == ['close'] and store['state'] == 'chiuso'
            page.close()
            page = open_dashboard(browser, store, errors)
            page.wait_for_timeout(500)
            assert page.locator('#coachBar').is_hidden()
            page.evaluate('showTab("company")')
            page.locator('#tutorResumeBtn').click()
            tip_on(page, '#app .gf-sidebar__item[data-tab="depositi"]')
            assert store['tutor_posts'] == ['close', 'resume']
            page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: tutor 1440 — bar + tip on next click, waits on Save with red required fields, advances on saved data, completes on first programmed route, exit/resume persisted')


if __name__ == '__main__':
    main()
