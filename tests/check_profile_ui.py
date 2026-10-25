"""Account profile window in Chromium: two columns, save bar only after a change.

All responses are synthetic; the only write (PUT /api/account-profile) is answered by
the fixture. Screenshots are written under test-results/profile-ui.
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
ACCOUNT = dict(username='Mario Rossi', email='mario.rossi@example.test', role='Amministratore')
LISTS = ('vehicles', 'drivers', 'deposits', 'customers', 'agents', 'operativi', 'routes')


def main():
    output = ROOT / 'test-results' / 'profile-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors, saved = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={'width': width, 'height': height})
                page.on('pageerror', lambda error: errors.append(str(error)))
                owner = dict(ME, plan='business', plan_status='active', limits=PLAN_LIMITS['business'], authenticated=True,
                             company_name='Supermercati Demo')
                usage = dict(month='2026-10', orders=dict(used=52, limit=1200), resources=dict(
                    customers=dict(used=16, limit=500), collaborators=dict(used=1, limit=5)))

                def handle(route):
                    parsed = urlparse(route.request.url)
                    path = parsed.path
                    if parsed.hostname != 'profile.test':
                        route.abort(); return
                    if path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                    if not path.startswith('/api/'):
                        relative = 'static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/')
                        file = (ROOT / relative).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    if path == '/api/account-profile' and route.request.method == 'PUT':
                        body = json.loads(route.request.post_data or '{}'); saved.append(body)
                        route.fulfill(json=dict(ok=True, account=dict(ACCOUNT, **body))); return
                    data = {'/api/me': owner, '/api/account-profile': ACCOUNT,
                            '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[]),
                            '/api/billing/my-plan': dict(owner, billing={}, usage=usage),
                            '/api/vehicles/usage': dict(standard_used=5, standard_limit=10, bonus_used=1, electric_bonus=2)}
                    route.fulfill(json=data.get(path, [] if path.rstrip('/').split('/')[-1] in LISTS else {}))

                page.route('**/*', handle)
                page.goto('http://profile.test/dashboard', wait_until='networkidle')
                page.evaluate('async () => { acceptCookieNotice(); await checkLogin(); document.getElementById("onboardingOverlay")?.classList.add("hidden"); await openProfilePanel(); }')
                modal = page.locator('#profileOverlay .gf-modal')
                modal.locator('#planUsageRows .gf-bar-chart__row').first.wait_for()
                assert modal.get_by_role('button', name='Salva profilo').count() == 0
                assert page.locator('#profileSaveBar').is_hidden()
                assert modal.locator('#planUsageRows .gf-bar-chart__row').count() == 4
                assert modal.locator('#planStatusLabel').inner_text() == 'Attivo'
                assert modal.locator('#profileRoleBadge').inner_text() == 'Amministratore'
                assert modal.locator('#btnPlanActive').inner_text() == 'Gestisci piano'
                if width > 1000:
                    # Su computer sta tutto senza scorrere.
                    assert page.evaluate("(()=>{const b=document.querySelector('#profileOverlay .gf-modal__body');return b.scrollHeight<=b.clientHeight+1})()")
                page.screenshot(path=str(output / f'profile-{width}.png'))

                page.fill('#profileName', 'Mario Rossi Junior')
                bar = page.locator('#profileSaveBar')
                assert bar.is_visible()
                # La barra è sopra lo sfondo della finestra: il centro della barra è cliccabile.
                assert page.evaluate("(()=>{const b=document.getElementById('profileSaveBar').getBoundingClientRect();return document.getElementById('profileSaveBar').contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2))})()")
                page.screenshot(path=str(output / f'profile-modifica-{width}.png'))
                bar.get_by_role('button', name='Annulla').click()
                assert page.input_value('#profileName') == 'Mario Rossi'
                assert bar.is_hidden()

                page.fill('#profileEmail', 'nuova@example.test')
                bar.get_by_role('button', name='Salva modifiche').click()
                page.wait_for_function("document.getElementById('profileSaveBar').classList.contains('hidden')")
                assert saved[-1] == dict(username='Mario Rossi', email='nuova@example.test')
                assert page.locator('#profileOverlay').is_visible()

                page.fill('#profileName', 'Da scartare')
                page.evaluate('closeProfilePanel()')
                assert bar.is_hidden()
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: profile window at 390/1440 — compact layout, save bar after changes, cancel, save and close')


if __name__ == '__main__':
    main()
