"""Read-only plan comparison and entitlement checks in Chromium.

All responses are synthetic. No payment, provider, email or production API is
contacted. Screenshots are written under test-results/plans-ui.
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
from app.services.company_permissions import CATALOG, DEPENDENCIES, permission_presets
from check_management_design import CUSTOMERS, DEPOSITS, DRIVERS, ME, ROUTES, USAGE, VEHICLES

CATALOGUE = {key: dict(value, price_eur=PLAN_PRICES[key]['price_eur'])
             for key, value in PLAN_LIMITS.items()}


def main():
    output = ROOT / 'test-results' / 'plans-ui'
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, writes = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
            executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width in (390, 1440):
                for plan, limits in PLAN_LIMITS.items():
                    context = browser.new_context(viewport={'width': width, 'height': 1000})
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    owner = dict(ME, plan=plan, plan_name=limits['name'], limits=limits,
                                 email='owner@example.test', authenticated=True)
                    seat_limit = limits['max_collaborators']
                    records = [dict(id=i+1, full_name=f'Collaboratore {i+1}',
                        email=f'collaborator{i+1}@example.test', is_active=True,
                        permissions=[], password_setup_required=i > 0,
                        invitation_status='pending' if i > 0 else 'active')
                        for i in range(seat_limit)]
                    used = int(limits['max_orders_per_month'] * .8)
                    usage = dict(month='2026-10', orders=dict(used=used,
                        limit=limits['max_orders_per_month'], warning=True), resources=dict(
                            customers=dict(used=1, limit=limits['max_customers']),
                            collaborators=dict(used=seat_limit, limit=seat_limit)))
                    state = {'active': False}

                    def handle(route):
                        parsed = urlparse(route.request.url)
                        path = parsed.path
                        if parsed.hostname != 'plans.test':
                            route.abort(); return
                        if path == '/api/billing/catalog.js':
                            route.fulfill(content_type='application/javascript',
                                body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                        if not path.startswith('/api/'):
                            relative = {'/dashboard': 'static/dashboard/index.html',
                                        '/': 'static/landing/index.html'}.get(path, path.lstrip('/'))
                            file = (ROOT / relative).resolve()
                            if file.is_relative_to(ROOT) and file.is_file():
                                route.fulfill(path=str(file))
                            else:
                                route.fulfill(status=404, body='')
                            return
                        if route.request.method not in ('GET', 'HEAD'):
                            writes.append({'path': path, 'method': route.request.method})
                            route.fulfill(status=405, json={'detail': 'Read-only UI fixture'}); return
                        data = {
                            '/api/me': dict(owner, authenticated=state['active']),
                            '/api/settings': dict(agents_enabled=True, delivery_signature_enabled=True),
                            '/api/company-profile': dict(owner, company_email='owner@example.test',
                                needs_photo_proof=True, delivery_signature_enabled=True),
                            '/api/billing/my-plan': dict(owner, billing={}, usage=usage),
                            '/api/account-profile': dict(username='demo', email='owner@example.test', role='admin'),
                            '/api/vehicles': VEHICLES, '/api/vehicles/usage': dict(USAGE,
                                standard_limit=limits['max_vehicles'], electric_bonus=limits['electric_vehicle_bonus']),
                            '/api/drivers': DRIVERS, '/api/deposits': DEPOSITS,
                            '/api/customers': CUSTOMERS, '/api/agents': [],
                            '/api/routes': ROUTES, '/api/routes/operativi': ROUTES[:2],
                            '/api/orders': dict(items=[], total=0), '/api/order-sources': [],
                            '/api/notifications': dict(items=[], unread=0),
                            '/api/notifications/count': dict(unread=0),
                            '/api/onboarding/status': dict(completed=True, workspace_operational=True, steps=[]),
                            '/api/resources/availability': dict(vehicles=VEHICLES, drivers=DRIVERS),
                            '/api/collaborators': records,
                            '/api/collaborators/permissions': dict(permissions=CATALOG,
                                dependencies={key: sorted(value) for key, value in DEPENDENCIES.items()},
                                presets=permission_presets()),
                            '/api/driver/admin/chat-threads': [],
                            '/api/driver/admin/unread': dict(total=0, routes=[]),
                        }.get(path, {})
                        route.fulfill(json=data)

                    page.route('**/*', handle)
                    page.goto('http://plans.test/', wait_until='networkidle')
                    cards = page.locator('#publicPricing .pricing-card')
                    assert cards.count() == 3
                    assert cards.nth(1).get_by_text('Consigliato', exact=True).is_visible()
                    for index, (key, info) in enumerate(PLAN_LIMITS.items()):
                        card = cards.nth(index)
                        assert f"{info['max_orders_per_month']} ordini/mese" in card.inner_text()
                        assert f"{info['max_collaborators']} collaboratori aziendali" in card.inner_text()
                        ai = card.locator('li').filter(has_text='Integrazione AI')
                        assert ai.get_attribute('data-included') == str(key == 'pro').lower()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                    if plan == 'starter':
                        page.locator('#publicPricing').screenshot(path=str(output / f'landing-{width}.png'))

                    page.goto('http://plans.test/dashboard', wait_until='networkidle')
                    state['active'] = True
                    page.evaluate('''async owner => {
                        currentSessionUser=owner; showGestionaleAfterLogin(); acceptCookieNotice();
                        await loadSettingsV41(); await loadUniversalFeaturesV89(); await loadPlanInfo();
                        openPlanAccountPage();
                    }''', owner)
                    page.locator('#upgradePlanCards article').first.wait_for(state='visible')
                    assert page.locator('#upgradePlanCards article').count() == 3
                    meter = page.locator('#subscriptionControls [role="progressbar"]')
                    assert meter.get_attribute('aria-valuemax') == str(limits['max_orders_per_month'])
                    assert meter.get_attribute('aria-valuenow') == str(used)
                    assert '80%' in page.locator('#subscriptionControls').inner_text()
                    rows = page.locator('#planComparisonV875 tr')
                    assert rows.filter(has_text='Ordini al mese').inner_text().split()[-3:] == ['300', '1200', '6000']
                    ai_row = rows.filter(has_text='Integrazione AI')
                    assert ai_row.locator('td').all_text_contents() == ['Integrazione AI', 'Non incluso', 'Non incluso', 'Incluso']
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                    page.screenshot(path=str(output / f'account-{plan}-{width}.png'), full_page=True)

                    page.evaluate("showTab('settings'); GFPlanAccess.apply()")
                    for selector in ('#settingDeliverySignature', '#featurePhotoProofV89'):
                        assert page.locator(selector).is_disabled() == (plan == 'starter')
                        if plan == 'starter': assert not page.locator(selector).is_checked()
                    assert page.evaluate("GFPlanAccess.has('has_ai')") == (plan == 'pro')
                    page.screenshot(path=str(output / f'settings-{plan}-{width}.png'), full_page=True)
                    page.evaluate("showTab('giro'); GFPlanAccess.apply()")
                    assert page.locator('[data-plan-feature="has_fleet_planning"]').first.is_disabled() == (plan == 'starter')
                    page.evaluate("showTab('collaboratori')")
                    page.wait_for_function("document.getElementById('collaboratorInviteNew').disabled")
                    assert f'{seat_limit} / {seat_limit}' in page.locator('#collaboratorQuota').inner_text()
                    assert page.locator('#collaboratorsActive').inner_text() == '1'
                    assert page.locator('#collaboratorsPending').inner_text() == str(seat_limit-1)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                    page.screenshot(path=str(output / f'collaborators-{plan}-{width}.png'), full_page=True)
                    checks.append(dict(plan=plan, width=width, orders=limits['max_orders_per_month'],
                                       collaborators=seat_limit))
                    context.close()
        finally:
            browser.close()
    assert not errors, errors
    assert not writes, writes
    (output / 'results.json').write_text(json.dumps(dict(checks=checks, errors=errors, writes=writes), indent=2))
    print(f'PASS: {len(checks)} plan/viewport scenarios; no JavaScript errors or writes')


if __name__ == '__main__':
    main()
