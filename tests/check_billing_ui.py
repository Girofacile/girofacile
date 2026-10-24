"""Billing page checks in Chromium: next charge header, documents tabs and tax details.

All responses are synthetic. No payment, provider, email or production API is
contacted; the only write (saving tax details) is answered by the fixture.
Screenshots are written under test-results/billing-ui.
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
COMPANY = dict(company_name='Logistica Demo S.r.l.', company_email='amministrazione@example.test',
               billing_email='amministrazione@example.test', company_vat='09876543210',
               company_fiscal_code='09876543210', company_pec='', company_sdi='M5UXCR1',
               company_legal_address='Via Mecenate 76, 20138 Milano (MI)',
               company_billing_address='Via Mecenate 76, 20138 Milano (MI)')
OVERVIEW = dict(
    billing=dict(checkout_enabled=False, subscription=True, cancel_at_period_end=False),
    plan=dict(key='business', name='Business', status='active', monthly_price=59,
              next_charge_at='2026-11-14T00:00:00', next_charge_amount=59),
    company=COMPANY,
    payment_method=dict(configured=False, label='Verifica o aggiorna il metodo nel portale Stripe', provider='Stripe'),
    invoices=[dict(id=7, number='FT 2026/0412', date='2026-10-14', period_start='2026-10-14', period_end='2026-11-13',
                   plan_name='Business', total=71.98, status='paid', pdf_available=True, is_test=False)],
    payments=[dict(id=3, amount=71.98, method='card', status='paid', transaction_id='pi_demo',
                   paid_at='2026-10-14', created_at='2026-10-14', is_test=False),
              dict(id=2, amount=71.98, method='card', status='failed', transaction_id='',
                   paid_at=None, created_at='2026-10-13', is_test=False)],
)


def main():
    output = ROOT / 'test-results' / 'billing-ui'
    output.mkdir(parents=True, exist_ok=True)
    errors, saved = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, executable_path=os.getenv('GF_TEST_BROWSER_EXECUTABLE') or None)
        try:
            for width in (390, 1440):
                page = browser.new_page(viewport={'width': width, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                owner = dict(ME, plan='business', plan_status='active', limits=PLAN_LIMITS['business'], authenticated=True)

                def handle(route):
                    parsed = urlparse(route.request.url)
                    path = parsed.path
                    if parsed.hostname != 'billing.test':
                        route.abort(); return
                    if path == '/api/billing/catalog.js':
                        route.fulfill(content_type='application/javascript', body='window.GF_PLANS=' + json.dumps(CATALOGUE)); return
                    if not path.startswith('/api/'):
                        relative = 'static/dashboard/index.html' if path == '/dashboard' else path.lstrip('/')
                        file = (ROOT / relative).resolve()
                        route.fulfill(path=str(file)) if file.is_relative_to(ROOT) and file.is_file() else route.fulfill(status=404, body='')
                        return
                    if path == '/api/billing/billing-details' and route.request.method == 'PUT':
                        body = json.loads(route.request.post_data or '{}')
                        saved.append(body)
                        route.fulfill(json=dict(ok=True, company=dict(COMPANY, **body, billing_email=body['company_email']))); return
                    if route.request.method not in ('GET', 'HEAD'):
                        route.fulfill(status=405, json={'detail': 'Read-only UI fixture'}); return
                    route.fulfill(json={'/api/me': owner, '/api/billing/overview': OVERVIEW,
                                        '/api/billing/my-plan': dict(owner, billing={}, usage={}),
                                        '/api/notifications/count': dict(unread=0)}.get(path, {}))

                page.route('**/*', handle)
                page.goto('http://billing.test/dashboard', wait_until='networkidle')
                page.evaluate('''async owner => { currentSessionUser=owner; showGestionaleAfterLogin(); acceptCookieNotice();
                                  await openBillingPanel(); }''', owner)
                tab = page.locator('#tab-billing-account')
                assert tab.locator('#billingNextTitleV9').inner_text() == 'Prossimo addebito il 14 novembre 2026'
                assert 'Piano Business' in tab.locator('#billingNextChargeDateV63').inner_text()
                assert tab.locator('#billingPaymentStatusV876').get_attribute('data-status') == 'success'
                assert tab.locator('#billingPaymentMethodV63').inner_text() == 'Carta gestita da Stripe'
                assert tab.locator('#billingLastPaymentV9').inner_text() == 'Ultimo pagamento riuscito'
                assert tab.locator('#billingTabInvoicesV9').inner_text() == 'Fatture (1)'
                assert tab.locator('#billingPanelPaymentsV9').is_hidden()
                tab.locator('#billingTabPaymentsV9').click()
                assert tab.locator('#billingPanelPaymentsV9').is_visible() and tab.locator('#billingPanelInvoicesV9').is_hidden()
                assert tab.locator('#billingPaymentsV63 tr').count() == 2
                assert 'Non riuscito' in tab.locator('#billingPaymentsV63').inner_text()
                assert 'Dati completi' in tab.locator('#billingDetailsCheckV9').inner_text()
                assert tab.locator('#billingDetailsFormV9').is_hidden()
                assert not page.locator('.gf-grid[data-cols="4"]', has=page.locator('#billingPaymentMethodV63')).count()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
                # La pagina non deve chiudere in anticipo il layout: la barra mobile resta nel layout base
                # e compare solo su smartphone.
                assert page.evaluate("document.getElementById('gfMobileBottomNavV62').parentElement.id") == 'app'
                assert page.locator('#gfMobileBottomNavV62').is_visible() == (width < 1024)
                page.screenshot(path=str(output / f'billing-{width}.png'), full_page=True)

                tab.locator('#billingDetailsEditV9').click()
                assert tab.locator('#billingDetailsFormV9').is_visible()
                assert page.locator('#billingSaveBarV9').is_hidden()
                page.fill('#billingCompanySdiV63', '')
                assert page.locator('#billingSaveBarV9').is_visible()
                page.screenshot(path=str(output / f'billing-edit-{width}.png'), full_page=True)
                page.locator('#billingSaveBarV9').get_by_role('button', name='Salva modifiche').click()
                page.wait_for_function("document.getElementById('billingDetailsFormV9').classList.contains('hidden')")
                assert saved[-1]['company_sdi'] == ''
                assert 'Mancano: codice SDI o PEC' in tab.locator('#billingDetailsCheckV9').inner_text()
                assert page.locator('#billingSaveBarV9').is_hidden()
                page.close()
        finally:
            browser.close()
    assert not errors, errors
    print('PASS: billing page at 390/1440 — header, tabs, tax details edit and e-invoice check')


if __name__ == '__main__':
    main()
