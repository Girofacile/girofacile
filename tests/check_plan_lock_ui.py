"""Funzioni non incluse nel piano: pop-up con i piani che le includono, nessuna pagina bloccata.

Azienda Starter con risposte sintetiche: nessuna API reale, nessun acquisto.
Screenshot in test-results/plan-lock-ui.
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


def main():
    output = ROOT / 'test-results' / 'plan-lock-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    owner = dict(ME, plan='starter', plan_name='Starter', plan_status='active', limits=PLAN_LIMITS['starter'])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width in (390, 1440):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                page.on('pageerror', lambda error: errors.append(str(error)))

                def handle(route):
                    parsed = urlparse(route.request.url)
                    path = parsed.path
                    if parsed.hostname != 'lock.test':
                        route.abort(); return
                    if path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                    if not path.startswith('/api/'):
                        relative = 'static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/')
                        file = (ROOT / relative).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    if route.request.method not in ('GET', 'HEAD'):
                        route.fulfill(status=405, json={'detail': 'Read-only UI fixture'}); return
                    route.fulfill(json={'/api/me': owner,
                                        # Gestione agenti accesa nelle impostazioni ma esclusa dal piano.
                                        '/api/settings': dict(agents_enabled=True, delivery_signature_enabled=False),
                                        '/api/billing/my-plan': dict(owner, billing={}, usage={}),
                                        '/api/vehicles': [], '/api/drivers': [], '/api/customers': [], '/api/deposits': [], '/api/agents': [],
                                        '/api/notifications/count': dict(unread=0),
                                        '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[])}.get(path, {}))

                page.route('**/*', handle)
                page.goto('http://lock.test/dashboard', wait_until='networkidle')
                page.evaluate('''async owner => { currentSessionUser=owner; _currentPlan='starter'; showGestionaleAfterLogin();
                                  acceptCookieNotice(); }''', owner)
                page.evaluate("settingsV41={agents_enabled:true}; applyAgentsFeature(); showTab('dashboard')")
                title_before = page.locator('#workspacePageTitle').inner_text()

                # Agenti esclusi dal piano: non compare nel menu anche con la gestione accesa.
                assert page.evaluate("document.documentElement.dataset.gfAgents") == 'off'
                assert not page.locator('.gf-sidebar__item[data-tab="agenti"]').is_visible()

                modal = page.locator('#planLockModal')
                for tab, name in (('report', 'Report'), ('chat-autisti', 'Chat autisti'), ('agenti', 'Agenti')):
                    page.evaluate(f"showTab('{tab}')")
                    assert modal.is_visible(), tab
                    assert page.locator('#planLockTitle').inner_text() == name
                    assert 'non incluso nel piano starter' in modal.inner_text().lower()
                    choices = page.locator('#planLockDialog [data-plan-choice]')
                    assert [choices.nth(i).get_attribute('data-plan-choice') for i in range(choices.count())] == ['business', 'pro'], tab
                    assert page.locator('#planLockGo').inner_text() == 'Passa a Business'
                    # Si resta nella pagina di prima: niente pagina bloccata, titolo invariato.
                    assert page.locator('#workspacePageTitle').inner_text() == title_before
                    assert page.evaluate("document.getElementById('tab-dashboard').classList.contains('hidden')") is False
                    if tab == 'report':
                        assert 'IVA' not in modal.inner_text() and '59 € al mese' in modal.inner_text()
                        assert choices.nth(0).locator('li').first.inner_text() == '✓ Report avanzati'
                        assert '6.000 ordini e 1.200 giri al mese' in choices.nth(1).inner_text()
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                        page.screenshot(path=str(output / f'report-{width}.png'))
                        choices.nth(1).click()
                        assert page.locator('#planLockGo').inner_text() == 'Passa a Pro'
                        assert choices.nth(1).get_attribute('data-variant') == 'info' and choices.nth(0).get_attribute('data-variant') is None
                    page.keyboard.press('Escape')
                    assert not modal.is_visible(), tab

                # Funzione solo del Pro: una sola scheda.
                page.evaluate("openPlanLockModal('has_ai')")
                choices = page.locator('#planLockDialog [data-plan-choice]')
                assert choices.count() == 1 and choices.first.get_attribute('data-plan-choice') == 'pro'
                assert 'La trovi nel piano:' in modal.inner_text()
                assert choices.first.locator('li').first.inner_text() == '✓ Integrazione AI'
                assert 'Consigliato' not in modal.inner_text()
                page.screenshot(path=str(output / f'ai-{width}.png'))
                page.locator('#planLockDialog').get_by_role('button', name='Non ora').click()
                assert not modal.is_visible()

                # «Usa più mezzi» con lo Starter: lo stesso pop-up dei piani, non un avviso; la modalità non cambia.
                page.evaluate("showTab('giro')")
                page.evaluate("selectPlanningModeCard('fleet')")
                assert modal.is_visible()
                assert 'Più mezzi' in page.locator('#planLockTitle').inner_text()
                assert choices.first.get_attribute('data-plan-choice') == 'business'
                assert choices.first.locator('li').first.inner_text() == '✓ Suddivisione automatica su più mezzi'
                assert page.evaluate("document.getElementById('planningMode')?.value") != 'fleet'
                page.screenshot(path=str(output / f'piu-mezzi-{width}.png'))
                page.keyboard.press('Escape')
                assert not modal.is_visible()

                # «Passa a Business» porta alla pagina Piani con Business selezionato.
                page.evaluate("showTab('report')")
                page.locator('#planLockGo').click()
                assert not modal.is_visible()
                assert page.evaluate("getVisibleTabV874()") == 'plan-account'
                assert page.evaluate("_selectedUpgradePlan") == 'business'
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: funzioni non incluse a 390/1440 — pop-up con i piani, Agenti nascosto, nessuna pagina bloccata')


if __name__ == '__main__':
    main()
