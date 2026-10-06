"""Local visual audit; no production services are contacted.

Run with Playwright installed: python tests/check_management_design.py before|after
Screenshots and audit results are saved under test-results/management-design.
The after run compares protected-page geometry and computed styles with before,
and isolates the new stylesheet in the same browser for the pixel comparison.
"""
import json
import os
import sys
import threading
import subprocess
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test-results" / "ui-tools"))
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops

PROTECTED = ["dashboard", "clienti", "company", "depositi"]
PAGES = PROTECTED + ["giro", "route-preview", "dashboard-scheduled", "dashboard-in-progress",
                     "dashboard-completed", "report", "mezzi", "autisti", "storico",
                     "chat-autisti", "settings", "agenti", "plan-account", "billing-account"]
LIMITS = dict(max_customers=500, max_vehicles=10, max_drivers=10, max_deposits=5,
              has_reports=True, has_driver_chat=True, has_agents=True, has_ai=True,
              electric_vehicle_bonus=2)
ME = dict(authenticated=True, role="admin", username="demo", company_name="Logistica Demo",
          company_sector="distribution", workspace_operational=True, onboarding_completed=True,
          plan="business", plan_name="Business", plan_status="active", limits=LIMITS)
VEHICLES = [dict(id=1, nome="Furgone consegne", targa="AB123CD", alimentazione="gasolio",
                consumo_l_100km=8.5, consumo_primario_100km=8.5, capacita_kg=1000,
                capacita_colli=100, stato="Disponibile", toll_class="B")]
DRIVERS = [dict(id=1, nome="Marco", cognome="Rossi", telefono="3331234567",
               email="marco@example.test", patente="B", stato="Disponibile", account_attivo=True)]
DEPOSITS = [dict(id=1, nome="Deposito centrale", indirizzo="Via Roma 1, Milano",
                predefinito=True, lat=45.46, lon=9.19)]
CUSTOMERS = [dict(id=1, nome="Cliente Demo", codice="CLI001", indirizzo="Via Verdi 10, Milano",
                 comune="Milano", cap="20100", provincia="MI", lat=45.47, lon=9.2,
                 verificato=True, tempo_scarico_min=10, telefono="021234567", email="cliente@example.test")]
USAGE = dict(standard_used=1, standard_limit=10, bonus_used=0, electric_bonus=2,
             total_used=1, total_limit=12, bonus_remaining=2, can_add_electric=True,
             can_add_non_electric=True, plan_active=True)
ROUTES = [dict(id=i, nome="Giro Milano " + str(i), data_giro="2026-10-03", status=status,
               vehicle_id=1, driver_id=1, deposit_id=1, driver_name="Marco Rossi",
               vehicle_name="Furgone consegne · AB123CD", totale_km=42, totale_minuti=95,
               costo_carburante=6.5, litri_stimati=3.57, consegne_count=1,
               orario_partenza="08:00", orario_rientro_stimato="09:35", rientro_deposito=True,
               consegne=[dict(id=i, customer_id=1, cliente_nome="Cliente Demo", ordine=1,
                             indirizzo="Via Verdi 10, Milano", lat=45.47, lon=9.2,
                             stato="consegnata" if status == "completato" else "da_consegnare",
                             arrivo_stimato="08:25", peso_kg=50, colli=4, tempo_scarico_min=10)])
          for i, status in enumerate(["programmato", "in_corso", "completato"], 1)]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "after"
    assert phase in ("before", "after")
    output = ROOT / "test-results" / "management-design" / phase
    output.mkdir(parents=True, exist_ok=True)
    # An optional Git ref serves the original HTML without touching the checkout.
    reference_html = subprocess.check_output(["git", "show", sys.argv[2] + ":static/dashboard/index.html"]) if len(sys.argv) > 2 else None
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    mutations, errors, overflow, comparisons, interactions = [], [], [], [], []

    def handle(route):
        path = urlparse(route.request.url).path
        if reference_html and path == "/static/dashboard/index.html":
            route.fulfill(content_type="text/html", body=reference_html)
        elif path == "/api/billing/catalog.js":
            catalog = {key: dict(LIMITS, name=key.title(), price_eur=price)
                       for key, price in [("starter", 29), ("business", 59), ("pro", 99)]}
            route.fulfill(content_type="application/javascript", body="window.GF_PLANS=" + json.dumps(catalog))
        elif path.startswith("/api/"):
            if route.request.method not in ("GET", "HEAD"):
                mutations.append(dict(path=path, method=route.request.method))
            data = {
                "/api/me": dict(ME, authenticated=False),
                "/api/vehicles": VEHICLES, "/api/drivers": DRIVERS, "/api/deposits": DEPOSITS,
                "/api/customers": CUSTOMERS, "/api/agents": [], "/api/routes": ROUTES,
                "/api/routes/operativi": ROUTES[:2], "/api/vehicles/usage": USAGE,
                "/api/settings": dict(agents_enabled=True, delivery_signature_enabled=True),
                "/api/company-profile": dict(ME, company_email="demo@example.test", has_ztl=True,
                                             needs_tail_lift=True, has_time_windows=True),
                "/api/account-profile": dict(name="Demo", email="demo@example.test", role="admin"),
                "/api/onboarding/status": dict(completed=True, workspace_operational=True, steps=[]),
                "/api/resources/availability": dict(vehicles=VEHICLES, drivers=DRIVERS),
                "/api/notifications": dict(items=[], unread=0),
                "/api/driver/admin/chat-threads": [],
                "/api/driver/admin/unread": dict(total=0, routes=[]),
                "/api/reports/summary": dict(metrics={}, charts={}, insights=[], drivers=[], customers=[], agents=[]),
                "/api/billing/my-plan": dict(ME, billing={}, usage={"resources": {"customers": {"used": len(CUSTOMERS)}}}),
                "/api/billing/overview": dict(plan=dict(name="Business", status="active"), company={}, invoices=[], payments=[]),
            }.get(path, {})
            for item in ROUTES:
                if path == f"/api/routes/{item['id']}":
                    data = item
            if "/chat/" in path:
                data = dict(messages=[], items=[])
            route.fulfill(content_type="application/json", body=json.dumps(data))
        elif urlparse(route.request.url).hostname != "127.0.0.1":
            route.abort()
        else:
            route.continue_()

    def capture(page, name, width):
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.evaluate("window.scrollTo(0,0)")
        page.evaluate("document.activeElement?.blur()")
        page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True, animations="disabled")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**({"channel": "chrome"} if os.name == "nt" else {}), headless=True)
            for width in (390, 768, 1440):
                page = browser.new_page(viewport=dict(width=width, height=1000), device_scale_factor=1)
                page.clock.set_fixed_time(datetime(2026, 10, 3, 10, tzinfo=timezone.utc))
                page.route("**/*", handle)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/static/dashboard/index.html", wait_until="networkidle")
                page.evaluate("""async me => {
                    currentSessionUser=me; showGestionaleAfterLogin();
                    await initApp(); acceptCookieNotice();
                }""", ME)
                for name in PAGES:
                    page.evaluate("name => showTab(name)", name)
                    if name == "billing-account":
                        page.evaluate("openBillingPanel()")
                    if name == "route-preview":
                        page.evaluate("r => renderRouteResult(r, 'routePreviewResult', false)", ROUTES[0])
                        page.evaluate("showTab('route-preview')")
                    page.wait_for_timeout(150)
                    if phase == "after" and name == "dashboard-in-progress":
                        page.locator("#dashboardInProgressPage .dash-sub-main").wait_for(state="visible")
                    capture(page, name, width)
                    if name == "dashboard-completed":
                        page.locator('#completedSearch').wait_for(state='visible')
                        page.evaluate("""r => {
                            const demo={...r, consegne:Array.from({length:23},(_,i)=>({...r.consegne[0], id:100+i, ordine:i+1, cliente_nome:'Cliente '+(i+1), delivery_status:i%2?'mancata':'completata', motivo_mancata:i%2?'assente':null}))};
                            renderDashboardCompletedSubpage([demo],demo);
                        }""", ROUTES[2])
                        assert page.locator('#completedTable tbody tr:visible').count() == 10
                        page.get_by_role('button', name='Pagina successiva', exact=True).click()
                        assert page.locator('#completedTable tbody tr:visible').first.inner_text().startswith('11')
                        page.locator('#completedSize').select_option('25')
                        assert page.locator('#completedTable tbody tr:visible').count() == 23
                        page.locator('#completedStatus').select_option('mancata')
                        assert page.locator('#completedTable tbody tr:visible').count() == 11
                        page.locator('#completedSearch').fill('Cliente 22')
                        assert page.locator('#completedTable tbody tr:visible').count() == 1
                        with page.expect_download() as download:
                            page.locator('#completedExport').click()
                        content=Path(download.value.path()).read_text(encoding='utf-8-sig')
                        assert 'Cliente 22' in content and 'Cliente 20' not in content
                        page.locator('#completedSearch').fill('nessuna corrispondenza')
                        assert page.locator('#completedTable tbody tr:visible').count() == 0
                        assert page.locator('#completedNoMatches').is_visible()
                        page.evaluate('r=>renderDashboardCompletedSubpage([r],r)',ROUTES[2])
                        interactions.append(f'{width}: completed pagination, search, status and filtered CSV')
                    if name in PROTECTED:
                        styles = page.evaluate("""() => [...document.querySelectorAll('#app *')].filter(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden').map(el=>{
                          const s=getComputedStyle(el), r=el.getBoundingClientRect();
                          return {tag:el.tagName,id:el.id,box:[r.x,r.y,r.width,r.height],styles:Object.fromEntries([...s].filter(k=>!k.startsWith('--')).map(k=>[k,s.getPropertyValue(k)]))};
                        })""")
                        (output / f"{name}-{width}.json").write_text(json.dumps(styles), encoding="utf-8")
                    excess = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                    if excess > 2:
                        overflow.append(dict(page=name, width=width, excess=excess))
                    if phase == "after" and name in PROTECTED:
                        old = output.parent / "before" / f"{name}-{width}.png"
                        previous = Image.open(old).convert("RGB")
                        current = Image.open(output / f"{name}-{width}.png").convert("RGB")
                        # Chromium can differ by one channel level in gradient rasterization.
                        delta = max(hi for lo, hi in ImageChops.difference(previous, current).getextrema()) if previous.size == current.size else 255
                        old_styles = output.parent / "before" / f"{name}-{width}.json"
                        import re
                        normalize = lambda value: re.sub(r"http://127\.0\.0\.1:\d+", "http://local.test", value)
                        exact_styles = old_styles.exists() and normalize(old_styles.read_text(encoding="utf-8")) == normalize((output / f"{name}-{width}.json").read_text(encoding="utf-8"))
                        # Isolate the new stylesheet within the same render session:
                        # WebP scaling can vary slightly between Chrome processes.
                        # The original computed-style snapshot also guards markup
                        # geometry, typography, backgrounds and the shared shell.
                        page.evaluate("document.querySelector('link[href*=\"management.css\"]').disabled=true")
                        isolated_path = output / f"{name}-{width}-without-management.png"
                        page.screenshot(path=str(isolated_path), full_page=True, animations="disabled")
                        isolated = Image.open(isolated_path).convert("RGB")
                        isolated_delta = max(hi for lo, hi in ImageChops.difference(current, isolated).getextrema()) if current.size == isolated.size else 255
                        page.evaluate("document.querySelector('link[href*=\"management.css\"]').disabled=false")
                        comparisons.append(dict(page=name, width=width, identical=isolated_delta <= 1 and exact_styles,
                                                max_pixel_delta=delta, isolated_pixel_delta=isolated_delta, exact_styles=exact_styles))
                # Exercise menus from protected pages. All requests remain mocked.
                page.evaluate("showTab('dashboard')")
                page.evaluate("openProfilePanel()")
                page.locator("#profileOverlay").wait_for(state="visible")
                capture(page, "profile", width)
                page.evaluate("closeProfilePanel(); openSupportPanelV49()")
                page.locator("#supportTicketModalV60").wait_for(state="visible")
                capture(page, "support", width)
                page.evaluate("closeSupportTicketModalV60(); showTab('clienti'); openCustomerModal()")
                page.locator("#customerOverlay").wait_for(state="visible")
                capture(page, "customer-form", width)
                page.evaluate("closeCustomerModal(); openCustomerImportModal()")
                capture(page, "customer-import", width)
                page.evaluate("closeCustomerImportModal(); showTab('autisti'); openNewDriverModal()")
                capture(page, "driver-form", width)
                page.evaluate("closeDriverModal(); showTab('dashboard'); toggleNotificationsDropdown()")
                if phase == "after":
                    page.evaluate("showNotificationsDropdownV30(false)")
                    trigger = page.locator('.gf-mobile-top-actions-v62 [aria-label="Notifiche"]') if width < 821 else page.locator('#notificationBellBtn')
                    trigger.click()
                    page.locator("#notificationDropdown").wait_for(state="visible")
                    assert trigger.get_attribute("aria-expanded") == "true"
                # Capture without clicking outside, which intentionally dismisses the menu.
                page.screenshot(path=str(output / f"notifications-{width}.png"), animations="disabled")
                page.evaluate("showNotificationsDropdownV30(false)")
                if phase == "after":
                    trigger.click()
                    page.keyboard.press("Escape")
                    assert not page.locator("#notificationDropdown").is_visible()
                    assert trigger.get_attribute("aria-expanded") == "false"
                    trigger.click()
                    page.locator("#tab-dashboard .dash-kpi-card").last.click()
                    assert not page.locator("#notificationDropdown").is_visible()
                    interactions.append(f"{width}: notifications open, Escape and outside close")
                if width < 821:
                    page.get_by_role("button", name="Apri menu mobile").click()
                    page.locator("#gfMobileMoreMenuV62").wait_for(state="visible")
                    page.screenshot(path=str(output / f"mobile-menu-{width}.png"), animations="disabled")
                    page.locator("#gfMobileMoreMenuV62").get_by_role("button", name="Depositi").click()
                    assert page.locator("#tab-depositi").is_visible()
                    assert not page.locator("#gfMobileMoreMenuV62").is_visible()
                if phase == "after":
                    page.evaluate("showTab('company')")
                    page.locator(".company-address-details summary").click()
                    assert page.locator("#companyLegalAddressInput").is_visible()
                    page.locator(".company-address-details summary").click()
                    page.locator("#companyNameInput").fill("Modifica di prova")
                    page.locator("#tab-company").get_by_role("button", name="Annulla modifiche").click()
                    page.wait_for_function("document.getElementById('companyNameInput').value === 'Logistica Demo'")
                    interactions.append(f"{width}: company details and cancel edits")
                    page.evaluate("showTab('depositi')")
                    page.locator(".deposit-edit").first.click()
                    assert page.locator("#depNome").input_value() == DEPOSITS[0]["nome"]
                    page.locator("#newDepositBtn").click()
                    assert page.locator("#depNome").input_value() == ""
                    interactions.append(f"{width}: deposit edit and reset")
                    page.evaluate("showTab('clienti')")
                    page.locator("#customerFilterToggle").click()
                    assert page.locator("#customerAdvancedFilters").is_visible()
                    page.locator("#customerFilterToggle").click()
                    page.locator("#customerGridView").click()
                    assert page.locator("#customerCards").is_visible()
                    page.locator("#customerCards").get_by_role("button", name="Dettagli", exact=True).first.click()
                    page.locator("#customerDetailsDialog").wait_for(state="visible")
                    capture(page, "customer-details", width)
                    page.locator("#customerDetailsDialog").get_by_role("button", name="Modifica cliente").click()
                    page.locator("#customerOverlay").wait_for(state="visible")
                    assert page.locator("#cNome").input_value() == "Cliente Demo"
                    page.locator("#customerOverlay").get_by_role("button", name="Annulla", exact=True).click()
                    assert not page.locator("#customerOverlay").is_visible()
                    page.locator("#customerListView").click()
                    interactions.append(f"{width}: customer filters, list/grid, details and edit dialog")
                    page.evaluate("showTab('mezzi')")
                    page.locator("#vFuelType").select_option("elettrico")
                    assert page.locator("#vElectricConsumptionWrap").is_visible()
                    assert not page.locator("#vPrimaryConsumptionWrap").is_visible()
                    page.locator("#tab-mezzi").get_by_role("button", name="Nuovo", exact=True).click()
                    assert page.locator("#vFuelType").input_value() == "gasolio"
                    interactions.append(f"{width}: vehicle energy fields and reset")
                    page.evaluate("showTab('report')")
                    page.locator("#reportFilterToggleBtn").click()
                    assert page.locator("#reportFilterPanel").is_visible()
                    capture(page, "report-filters", width)
                    page.locator("#reportFilterToggleBtn").click()
                    page.evaluate("showTab('settings')")
                    page.locator(".settings-expand").first.click()
                    assert page.locator(".settings-expand").first.get_attribute("aria-expanded") == "true"
                    page.locator(".settings-expand").first.click()
                    interactions.append(f"{width}: report filters and settings detail")
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        results = dict(errors=errors, overflow=overflow, protected=comparisons, mutations=mutations, interactions=interactions)
        (output / "audit.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    if phase == "after":
        assert all(item["identical"] for item in comparisons), "Protected page visual regression"
        assert not [item for item in overflow if item["page"] not in PROTECTED], "Page overflow"
        assert not errors, "Browser script errors"


if __name__ == "__main__":
    main()
