"""Management interaction and layout audit; no production services are contacted.
Run before|after; screenshots and computed styles go to test-results/management-design.
The complete Design System migration intentionally restyles the former reference
pages. Functional interactions and root overflow remain regression checks.
Shared component consistency is verified separately by check_design_system.py.
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

REFERENCE = ["dashboard", "clienti", "company", "depositi"]
PAGES = REFERENCE + ["giro", "route-preview", "dashboard-scheduled", "dashboard-in-progress",
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
    mutations, errors, overflow, interactions = [], [], [], []

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
                if path == f"/api/routes/{item['id']}/position":
                    data = dict(route_name=item['nome'], vehicle_name=item['vehicle_name'], next_stop='Cliente Demo', progress=0, state='unavailable', route_status=item['status'], position=None)
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
            for width in (390, 768, 1024, 1440):
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
                        page.evaluate("r => renderRouteResult(r, 'routePreviewResult', false)", dict(ROUTES[0], google_maps_url='https://www.google.com/maps/dir/?api=1', traffic_status='not_requested', energy_quantity_primary=3.57, operating_cost_status='partial'))
                        page.evaluate("showTab('route-preview')")
                    page.wait_for_timeout(150)
                    if phase == "after" and name == "dashboard-in-progress":
                        page.locator("#dashboardInProgressPage [data-ip-picker]").wait_for(state="visible")
                    capture(page, name, width)
                    if name == 'dashboard-in-progress':
                        # Pagina "Giri in corso" con i componenti: scelta del giro, mappa, indicatori, fermate e chat.
                        live=page.locator('#dashboardInProgressPage')
                        assert live.locator('[data-ip-picker] [data-ip-route]').count() >= 1
                        assert live.locator('dl.gf-details dt').count() == 6
                        for label in ('Ingrandisci','Riduci','Segui il mezzo'):
                            assert live.get_by_role('button',name=label,exact=True).count() == 1
                        live.locator('[data-ip-action="chat"]').click()
                        assert live.locator('[data-ip-chat]').is_visible()
                        live.locator('[data-ip-action="chat"]').click()
                        assert live.locator('[data-ip-chat]').is_hidden()
                        live.locator('select[aria-label="Filtra fermate per esito"]').select_option('done')
                        assert live.locator('tr[data-ip-stop]:visible').count() == 0
                        live.locator('select[aria-label="Filtra fermate per esito"]').select_option('all')
                        assert live.locator('tr[data-ip-stop]:visible').count() == 1
                        interactions.append(f'{width}: giro in corso, indicatori, controlli mappa, chat e filtro esiti')
                    if name == 'route-preview':
                        preview=page.locator('#routePreviewResult')
                        assert preview.locator('.gf-routing-costs > div').count() == 3
                        assert preview.locator('[data-preview-metrics] .gf-stat-strip__cell').count() == 6
                        assert preview.locator('[data-preview-layout] > [data-preview-map]').count() == 1
                        assert preview.locator('[data-preview-summary] [data-preview-program]').is_visible()
                        assert preview.locator('[data-preview-summary] button', has_text='Aggiorna ETA').is_visible()
                        assert preview.locator('[data-preview-summary] a', has_text='Apri in Google Maps').get_attribute('href').startswith('https://www.google.com/maps/')
                        stops=preview.locator('[data-preview-stops]').bounding_box()
                        layout=preview.locator('[data-preview-layout]').bounding_box()
                        assert stops['y']+stops['height'] <= layout['y']+1
                        assert abs(stops['width']-layout['width']) < 2
                        preview.locator('[data-preview-stop-actions] summary').first.click()
                        assert preview.locator('[data-preview-stop-actions] [data-preview-stop-tools]').first.is_visible()
                        preview.locator('[data-preview-map-jump]').click()
                        preview.locator('[data-preview-back]').click()
                        assert page.locator('#tab-giro').is_visible()
                        page.evaluate("showTab('route-preview')")
                        interactions.append(f'{width}: preview costs, full-width stops, map, actions and navigation')
                    if name == "storico":
                        # Storico: settimana a 7 card, tabella del giorno, ricerca, filtri, CSV e pannello del giro.
                        history=page.locator('#tab-storico')
                        page.locator('#historySearch').wait_for(state='visible')
                        assert history.locator('#historyWeek .gf-grid[data-cols="7"] > .gf-panel').count() == 7
                        assert history.locator('#historyDayList tbody tr').count() == len(ROUTES)
                        page.locator('#historySearch').fill('Milano 3')
                        assert history.locator('#historyWeekSection').is_hidden()
                        assert history.locator('#historyResultsList tbody tr').count() == 1
                        history.locator('#historyActiveFilters .gf-chip').click()
                        assert history.locator('#historyWeekSection').is_visible()
                        history.get_by_role('button', name='Filtri').click()
                        page.locator('#historyFilterDialog').wait_for(state='visible')
                        page.locator('#historyStatus').select_option('completato')
                        page.locator('#historyFilterDialog').get_by_role('button', name='Mostra i giri').click()
                        assert page.locator('#historyFilterCount').inner_text() == '1'
                        assert history.locator('#historyResultsList tbody tr').count() == 1
                        with page.expect_download() as download:
                            history.get_by_role('button', name='Esporta', exact=True).click()
                        content=Path(download.value.path()).read_text(encoding='utf-8-sig')
                        assert 'Giro Milano 3' in content and 'Giro Milano 1' not in content
                        history.get_by_role('button', name='Azzera tutto').click()
                        assert history.locator('#historyWeekSection').is_visible()
                        history.locator('#historyDayList').get_by_role('button', name='Apri giro').first.click()
                        dialog=page.locator('#historyRouteDialog')
                        dialog.wait_for(state='visible')
                        assert 'Cliente Demo' in dialog.inner_text()
                        with page.expect_download() as download:
                            dialog.get_by_role('button', name='Esporta fermate (CSV)').click()
                        assert 'Cliente Demo' in Path(download.value.path()).read_text(encoding='utf-8-sig')
                        dialog.get_by_role('button', name='Chiudi').click()
                        assert dialog.is_hidden()
                        # "Giri completati" dalla Dashboard porta allo Storico con il giro già aperto.
                        page.evaluate('openDashboardCompletedPage(3)')
                        dialog.wait_for(state='visible')
                        assert page.locator('#tab-storico').is_visible()
                        dialog.get_by_role('button', name='Chiudi').click()
                        interactions.append(f'{width}: storico settimana, ricerca, filtri, CSV e pannello del giro')
                    if name in REFERENCE:
                        styles = page.evaluate("""() => [...document.querySelectorAll('#app *')].filter(el=>el.getClientRects().length && getComputedStyle(el).visibility!=='hidden').map(el=>{
                          const s=getComputedStyle(el), r=el.getBoundingClientRect();
                          return {tag:el.tagName,id:el.id,box:[r.x,r.y,r.width,r.height],styles:Object.fromEntries([...s].filter(k=>!k.startsWith('--')).map(k=>[k,s.getPropertyValue(k)]))};
                        })""")
                        (output / f"{name}-{width}.json").write_text(json.dumps(styles), encoding="utf-8")
                    excess = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                    if excess > 2:
                        overflow.append(dict(page=name, width=width, excess=excess))
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
                    # Con il layout base la campanella è nell'intestazione a ogni larghezza.
                    trigger = page.locator('#notificationBellBtn')
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
                    # The notifications menu overlaps the right-hand KPI in the new header.
                    # Solo un titolo visibile: il riquadro "Nessun giro in corso" resta nascosto se c'è un giro attivo.
                    page.locator("#tab-dashboard .gf-panel__title:visible").first.click()
                    assert not page.locator("#notificationDropdown").is_visible()
                    interactions.append(f"{width}: notifications open, Escape and outside close")
                # Su mobile il menu è la sidebar a scomparsa del layout base condiviso.
                mobile_menu_button = page.get_by_role("button", name="Apri il menu", exact=True)
                if mobile_menu_button.is_visible():
                    mobile_menu_button.click()
                    page.locator("#gf-shell-sidebar").wait_for(state="visible")
                    page.screenshot(path=str(output / f"mobile-menu-{width}.png"), animations="disabled")
                    page.locator('#gf-shell-sidebar [data-tab="depositi"]').click()
                    assert page.locator("#tab-depositi").is_visible()
                    assert page.locator("[data-gf-shell]").get_attribute("data-gf-shell-open") != "true"
                if phase == "after":
                    page.evaluate("showTab('company')")
                    # Indirizzi vuoti: "Uguali alla sede aziendale" è attivo e i campi sono nascosti (come prima).
                    if page.locator("#gfRefSame").is_checked():
                        assert page.locator("#companyLegalAddressInput").is_hidden()
                        page.locator('label[for="gfRefSame"]').click()
                    assert page.locator("#companyLegalAddressInput").is_visible()
                    assert page.locator("#companyBillingAddressInput").is_visible()
                    page.locator("#companyNameInput").fill("Modifica di prova")
                    page.locator("#companyDiscardChangesBtn").click()
                    page.wait_for_function("document.getElementById('companyNameInput').value === 'Logistica Demo'")
                    interactions.append(f"{width}: company addresses and cancel edits")
                    page.evaluate("showTab('depositi')")
                    page.locator("#depositsBody").get_by_role("button", name="Modifica", exact=False).first.click()
                    assert page.locator("#depNome").input_value() == DEPOSITS[0]["nome"]
                    page.locator("#depositOverlay").get_by_role("button", name="Annulla", exact=True).click()
                    page.locator("#newDepositBtn").click()
                    assert page.locator("#depNome").input_value() == ""
                    page.locator("#depositOverlay").get_by_role("button", name="Annulla", exact=True).click()
                    interactions.append(f"{width}: deposit edit and reset")
                    page.evaluate("showTab('clienti')")
                    page.locator("#customerFilterToggle").click()
                    assert page.locator("#customerAdvancedFilters").is_visible()
                    page.locator("#customerFilterToggle").click()
                    page.locator("#customerGridView").click()
                    assert page.locator("#customerCards").is_visible()
                    page.locator("#customerCards").get_by_role("button", name="Dettagli", exact=True).first.click()
                    # I dettagli si aprono nel pannello laterale; "Tutti i campi" porta al modulo completo.
                    drawer = page.locator("#customerDrawer")
                    drawer.wait_for(state="visible")
                    capture(page, "customer-details", width)
                    drawer.get_by_role("button", name="Modifica dati").click()
                    drawer.locator("[data-cx-full]").click()
                    page.locator("#customerOverlay").wait_for(state="visible")
                    assert page.locator("#cNome").input_value() == "Cliente Demo"
                    page.locator("#customerOverlay").get_by_role("button", name="Annulla", exact=True).click()
                    assert not page.locator("#customerOverlay").is_visible()
                    page.locator("#customerListView").click()
                    interactions.append(f"{width}: customer filters, list/grid, details and edit dialog")
                    page.evaluate("showTab('mezzi')")
                    page.locator('#tab-mezzi .gf-panel__header button[onclick="createFleetVehicle()"]').click()
                    page.locator("#vehicleDrawer").wait_for(state="visible")
                    page.locator("#vFuelType").select_option("elettrico")
                    assert page.locator("#vElectricConsumptionWrap").is_visible()
                    assert not page.locator("#vPrimaryConsumptionWrap").is_visible()
                    page.evaluate("resetVehicleForm()")
                    assert page.locator("#vFuelType").input_value() == "gasolio"
                    page.keyboard.press("Escape")
                    page.locator("#vehicleDrawer").wait_for(state="hidden")
                    interactions.append(f"{width}: vehicle energy fields and reset")
                    page.evaluate("showTab('report')")
                    page.locator("#reportFilterToggleBtn").click()
                    assert page.locator("#reportFilterPanel").is_visible()
                    capture(page, "report-filters", width)
                    page.locator("#reportFilterToggleBtn").click()
                    page.evaluate("showTab('settings')")
                    detail = page.locator('#tab-settings [onclick="toggleSettingsDetail(this)"]').first
                    detail.click()
                    assert detail.get_attribute("aria-expanded") == "true"
                    detail.click()
                    interactions.append(f"{width}: report filters and settings detail")
                page.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        results = dict(errors=errors, overflow=overflow, reference_pages=REFERENCE,
                       widths=[390, 768, 1024, 1440], mutations=mutations, interactions=interactions)
        (output / "audit.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    if phase == "after":
        assert not overflow, "Page overflow"
        assert not mutations, "Unexpected API mutations in presentation checks"
        assert not errors, "Browser script errors"


if __name__ == "__main__":
    main()
