"""Sidebar upgrade card in Chromium: next plan per owner, hidden on Pro, for collaborators
and while the "Azienda e sistema" group is open. All responses are synthetic.
Screenshots are written under test-results/sidebar-upgrade.
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
    output = ROOT / 'test-results' / 'sidebar-upgrade'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for plan in ('starter', 'business', 'pro'):
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                owner = dict(ME, plan=plan, plan_status='active', limits=PLAN_LIMITS[plan], authenticated=True)

                def handle(route):
                    parsed = urlparse(route.request.url)
                    if parsed.hostname != 'upgrade.test':
                        route.abort(); return
                    if parsed.path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                    if not parsed.path.startswith('/api/'):
                        relative = 'static/dashboard/index.html' if parsed.path == '/dashboard' else parsed.path.lstrip('/')
                        file = (ROOT / relative).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    route.fulfill(json={'/api/me': owner, '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[])}.get(parsed.path, [] if parsed.path.rstrip('/').split('/')[-1] in ('vehicles', 'drivers', 'deposits', 'customers', 'agents', 'operativi', 'routes') else {}))

                page.route('**/*', handle)
                page.goto('http://upgrade.test/dashboard', wait_until='networkidle')
                # Avvio reale della Dashboard dopo l'accesso: il riquadro deve comparire senza aprire il profilo.
                page.evaluate('async () => { acceptCookieNotice(); await checkLogin(); document.getElementById("onboardingOverlay")?.classList.add("hidden"); }')
                card = page.locator('#sidebarUpgrade')
                if plan == 'pro':
                    assert card.is_hidden()
                else:
                    expected = {'starter': 'Business', 'business': 'Pro'}[plan]
                    assert card.is_visible()
                    assert card.locator('#sidebarUpgradeTitle').inner_text() == f'Passa a {expected}'
                    assert card.locator('#sidebarUpgradeButton').get_attribute('data-plan') == expected.lower()
                    if plan == 'business':
                        assert '6.000 ordini' in card.inner_text()
                    # Il riquadro sta sopra il piè di pagina, dentro la barra laterale.
                    footer = page.locator('.gf-sidebar__footer').bounding_box()
                    box = card.bounding_box()
                    assert box['y'] + box['height'] <= footer['y'] + 1
                    # Le voci usano lo spazio libero senza mai far scorrere la barra.
                    page.wait_for_timeout(150)
                    assert page.evaluate("(()=>{const s=document.querySelector('.gf-sidebar');return s.scrollHeight<=s.clientHeight})()")
                    assert page.locator('.gf-sidebar').get_attribute('data-row-size') in ('36', '40', '44', '48')
                    page.locator('.gf-sidebar').screenshot(path=str(output / f'{plan}.png'))
                    page.locator('[data-sidebar-group="sistema"] > summary').click()
                    assert card.is_hidden()
                    # Il piè di pagina resta in fondo alla barra anche senza il riquadro.
                    side = page.locator('.gf-sidebar').bounding_box()
                    footer = page.locator('.gf-sidebar__footer').bounding_box()
                    assert footer['y'] + footer['height'] >= side['y'] + side['height'] - 40
                    page.locator('.gf-sidebar').screenshot(path=str(output / f'{plan}-sistema-aperto.png'))
                    page.locator('[data-sidebar-group="sistema"] > summary').click()
                    assert card.is_visible()
                    page.evaluate("document.body.classList.add('company-collaborator'); window.GFCompanyAccess={isCollaborator:()=>true}; renderSidebarUpgrade(currentSessionUser.plan)")
                    assert card.is_hidden()
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: sidebar upgrade — next plan, hidden on Pro, collaborators and open company group')


if __name__ == '__main__':
    main()
