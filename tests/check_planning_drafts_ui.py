"""Giri in bozza in Chromium: avviso lasciando la pianificazione, voce nella sidebar solo con bozze,
pagina con la tabella, ripresa ed eliminazione; una vecchia selezione già pianificata va in bozza all'accesso.

Le API sono simulate in memoria (nessun dato reale). Schermate in test-results/planning-drafts-ui.
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
STOP = dict(cliente_nome='DEMO Bar Zi Teresa', indirizzo='Corso Garibaldi 60, Portici', lat=40.815, lon=14.339,
            stato_geocodifica='verificato', peso_kg=10, colli=2)
LISTS = ('vehicles', 'drivers', 'deposits', 'customers', 'agents', 'operativi', 'routes')
EMPTY = dict(order_ids=[], configuration={}, stops=None, routes=[], requested_dates=[])


def open_dashboard(browser, width, height, store, errors):
    page = browser.new_page(viewport={'width': width, 'height': height})
    page.on('pageerror', lambda e: errors.append(str(e)))
    owner = dict(ME, plan='business', plan_status='active', limits=PLAN_LIMITS['business'], authenticated=True)

    def handle(route):
        parsed = urlparse(route.request.url)
        path, method = parsed.path, route.request.method
        if parsed.hostname != 'drafts.test':
            route.abort(); return
        if path == '/api/billing/catalog.js':
            route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
        if not path.startswith('/api/'):
            file = (ROOT / ('static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/'))).resolve()
            route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
            return
        if path == '/api/planning-drafts' and method == 'POST':
            body = json.loads(route.request.post_data); store['posts'].append(body)
            if body['source'] == 'orders':
                store['selection'] = dict(EMPTY, version=store['selection']['version'] + 1)
            draft = dict(id=store['next'], source=body['source'], name='Giro del 28/10', data_giro='2026-10-28',
                         planning_mode='single', vehicles=1, stops=len(body.get('stops') or []) or 13, orders=13 if body['source'] == 'orders' else 0,
                         stage=body.get('stage', 'configurazione'), fleet_plan_id=None, updated_at='2026-10-27T10:00:00',
                         _stops=body.get('stops'), _configuration=body.get('configuration') or {})
            store['next'] += 1; store['drafts'].append(draft)
            route.fulfill(status=201, json={k: v for k, v in draft.items() if not k.startswith('_')}); return
        if path == '/api/planning-drafts':
            route.fulfill(json=dict(drafts=[{k: v for k, v in d.items() if not k.startswith('_')} for d in store['drafts']], routes=store.get('routes', []))); return
        if path.startswith('/api/planning-drafts/') and path.endswith('/resume'):
            draft = next(d for d in store['drafts'] if d['id'] == int(path.split('/')[3]))
            store['drafts'].remove(draft)
            route.fulfill(json=dict(source=draft['source'], configuration=draft['_configuration'], stops=draft['_stops'],
                                    stage=draft['stage'], fleet_plan_id=None, dropped=0)); return
        if path.startswith('/api/planning-drafts/') and method == 'DELETE':
            store['drafts'] = [d for d in store['drafts'] if d['id'] != int(path.split('/')[3])]
            route.fulfill(json=dict(ok=True)); return
        if path == '/api/order-planning/selection':
            route.fulfill(json=store['selection']); return
        data = {'/api/me': owner, '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[]),
                '/api/resources/availability': dict(vehicles=[], drivers=[]),
                '/api/orders': dict(items=[], total=0, page=1, page_size=25, counts={}, metrics={})}
        route.fulfill(json=data.get(path, [] if path.rstrip('/').split('/')[-1] in LISTS else {}))

    page.route('**/*', handle)
    page.goto('http://drafts.test/dashboard', wait_until='networkidle')
    page.evaluate('async () => { acceptCookieNotice(); await checkLogin(); document.getElementById("onboardingOverlay")?.classList.add("hidden"); showTab("dashboard"); }')
    return page


def main():
    output = ROOT / 'test-results' / 'planning-drafts-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width, height in ((1440, 900), (390, 844)):
                store = dict(drafts=[], next=1, posts=[], selection=dict(EMPTY, version=3))
                page = open_dashboard(browser, width, height, store, errors)
                item = page.locator('#sidebarDraftsItem')
                page.wait_for_timeout(300)
                # Nessuna bozza: la voce non compare nella sidebar e non c'è nulla in Dashboard/Ordini.
                assert item.is_hidden()
                assert page.locator('[data-planning-drafts]').count() == 0

                # Pianificazione dai clienti, poi si va su Ordini: "Annulla" resta, "OK" manda il giro in bozza.
                page.evaluate('s => { showTab("giro"); deliveries=[s]; customerDirectoryPlanning=true; renderDeliveries(); }', STOP)
                messages = []
                page.once('dialog', lambda d: (messages.append(d.message), d.dismiss()))
                page.evaluate('showTab("ordini")')
                assert 'stai per mandare questo giro in bozza' in messages[0]
                assert page.locator('#tab-giro').is_visible() and not store['posts']
                page.once('dialog', lambda d: d.accept())
                page.evaluate('showTab("ordini")')
                page.locator('#tab-ordini').wait_for(state='visible')
                assert store['posts'][-1]['source'] == 'customers' and store['posts'][-1]['stage'] == 'configurazione'
                assert page.evaluate('deliveries.length') == 0
                # Ora la voce "Giri in bozza" compare nella sidebar (Attività) con il numero di bozze.
                page.wait_for_function('!document.getElementById("sidebarDraftsItem").classList.contains("gf-hidden")')
                assert page.locator('#sidebarDraftsBadge').inner_text() == '1'

                # La pagina: tabella con fase, origine e azioni.
                page.evaluate('showTab("bozze")')
                table = page.locator('#planningDraftsTable')
                table.locator('tbody tr').first.wait_for()
                assert page.locator('#workspacePageTitle').inner_text() == 'Giri in bozza'
                assert table.locator('tbody tr').count() == 1
                assert 'Configurazione del giro' in table.inner_text() and 'Da clienti' in table.inner_text()
                assert page.locator('#planningDraftsStats').is_visible()
                page.screenshot(path=str(output / f'bozze-{width}.png'), full_page=True)

                # Riprendi: torna in pianificazione con le stesse consegne, la voce sparisce.
                table.get_by_role('button', name='Riprendi').click()
                page.locator('#tab-giro').wait_for(state='visible')
                page.wait_for_function('deliveries.length === 1')
                assert page.evaluate('deliveries[0].cliente_nome') == STOP['cliente_nome'] and page.evaluate('customerDirectoryPlanning') is True
                page.wait_for_function('document.getElementById("sidebarDraftsItem").classList.contains("gf-hidden")')

                # Elimina dalla pagina: conferma, tabella vuota e voce nascosta.
                page.once('dialog', lambda d: d.accept())
                page.evaluate('showTab("bozze")')
                table.get_by_role('button', name='Elimina').wait_for()
                page.once('dialog', lambda d: d.accept())
                table.get_by_role('button', name='Elimina').click()
                table.get_by_text('Nessun giro in bozza').wait_for()
                assert item.is_hidden()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
                page.close()

                # Ordini rimasti selezionati da un giro già portato in pianificazione: all'accesso vanno in bozza.
                store = dict(drafts=[], next=1, posts=[], selection=dict(EMPTY, version=7, order_ids=list(range(1, 14)),
                                                                         configuration={'data_giro': '2026-11-03', 'planning_mode': 'fleet'}))
                page = open_dashboard(browser, width, height, store, errors)
                page.wait_for_function('!document.getElementById("sidebarDraftsItem").classList.contains("gf-hidden")')
                assert store['posts'] == [dict(source='orders', selection_version=7, stage='configurazione')]
                assert store['selection']['order_ids'] == []
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: giri in bozza at 390/1440 — leave warning, sidebar item only with drafts, page table, resume, delete, stale selection parked')


if __name__ == '__main__':
    main()
