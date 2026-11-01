"""Sidebar upgrade card in Chromium: next plan per owner, hidden on Pro, for collaborators
shrunk on short windows and hidden only when even the short version does not fit. All responses are synthetic.
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
                # Scala dell'interfaccia bloccata a 1 (vedi sotto), così le altezze qui sotto sono quelle reali.
                page = browser.new_page(viewport={'width': 1700, 'height': 1000})
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
                page.add_style_tag(content=':root{--gf-ui-scale:1 !important}')
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
                    no_scroll = "(()=>{const s=document.querySelector('.gf-sidebar');return s.scrollHeight<=s.clientHeight})()"
                    fit = lambda: page.locator('.gf-sidebar').get_attribute('data-upgrade-fit')
                    text = card.locator('#sidebarUpgradeText')
                    # All'avvio tutti e quattro i gruppi sono aperti, voci compatte, riquadro intero e niente scorrimento.
                    page.wait_for_timeout(150)
                    assert page.locator('.gf-sidebar__group:not([open])').count() == 0
                    assert page.locator('.gf-sidebar').get_attribute('data-row-size') is None
                    assert fit() == 'yes' and text.is_visible()
                    assert page.evaluate(no_scroll)
                    page.locator('.gf-sidebar').screenshot(path=str(output / f'{plan}.png'))
                    short = card.locator('#sidebarUpgradeShort')
                    # Finestra più bassa: il riquadro si riduce a una riga di descrizione breve, mai tagliata.
                    page.set_viewport_size({'width': 1700, 'height': 900})
                    page.wait_for_timeout(150)
                    assert fit() == 'compact' and card.is_visible() and text.is_hidden() and short.is_visible()
                    assert short.evaluate("e => e.scrollWidth <= e.clientWidth")
                    assert page.evaluate(no_scroll)
                    page.locator('.gf-sidebar').screenshot(path=str(output / f'{plan}-ridotto-900.png'))
                    # Ancora più bassa: restano titolo e pulsante.
                    page.set_viewport_size({'width': 1700, 'height': 880})
                    page.wait_for_timeout(150)
                    assert fit() == 'mini' and card.is_visible() and text.is_hidden() and short.is_hidden()
                    assert page.evaluate(no_scroll)
                    # Ancora più bassa: solo ora sparisce; il piè di pagina resta in fondo alla barra.
                    page.set_viewport_size({'width': 1700, 'height': 820})
                    page.wait_for_timeout(150)
                    assert fit() == 'no' and card.is_hidden()
                    assert page.evaluate(no_scroll)
                    side = page.locator('.gf-sidebar').bounding_box()
                    footer = page.locator('.gf-sidebar__footer').bounding_box()
                    assert footer['y'] + footer['height'] >= side['y'] + side['height'] - 40
                    # I gruppi restano chiudibili: chiudendone uno torna lo spazio e il riquadro ricompare.
                    page.locator('[data-sidebar-group="risorse"] > summary').click()
                    assert card.is_visible()
                    assert page.evaluate(no_scroll)
                    page.locator('.gf-sidebar').screenshot(path=str(output / f'{plan}-risorse-chiuso-820.png'))
                    page.locator('[data-sidebar-group="risorse"] > summary').click()
                    page.set_viewport_size({'width': 1700, 'height': 1000})
                    page.wait_for_timeout(150)
                    assert fit() == 'yes' and card.is_visible()
                    page.evaluate("document.body.classList.add('company-collaborator'); window.GFCompanyAccess={isCollaborator:()=>true}; renderSidebarUpgrade(currentSessionUser.plan)")
                    assert card.is_hidden()
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: sidebar upgrade — groups open, next plan, compact then hidden only when it does not fit')


if __name__ == '__main__':
    main()
