"""Design System integration tests with Chromium and committed static assets.

All API responses are synthetic, external requests are blocked, and no write
request is allowed. Screenshots are review artifacts, not historical pixel locks.
Run: python tests/check_design_system.py
"""
import json
import base64
import os
import sys
import threading
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_management_design import CUSTOMERS, DEPOSITS, DRIVERS, LIMITS, ME, ROUTES, USAGE, VEHICLES
from playwright.sync_api import sync_playwright

WIDTHS = (390, 768, 1024, 1440)
HTML_PAGES = (
    "admin/index", "admin/login", "mobile/index", "driver/index", "driver/setup",
    "operator/index", "agent/index", "agent/setup", "tracking/index", "landing/index",
    "legal/index", "legal/privacy-policy", "legal/cookie-policy", "legal/termini-condizioni",
    "legal/sicurezza", "legal/dpa-responsabile-trattamento", "legal/subprocessors",
)
TRACKING_TOKEN = "a" * 64 + "." + "b" * 64
EXECUTION = dict(
    route=dict(ROUTES[0], status="in_corso", driver_nome="Marco Rossi"),
    consegne=[dict(ROUTES[0]["consegne"][0], status="in_attesa", cliente_nome="Cliente Demo")],
    progress=dict(percentuale=0, totale=1, completate=0, mancate=0, rimanenti=1, prossima_idx=0),
    settings=dict(delivery_signature_enabled=True), delivery_signature_enabled=True,
    tempo_scarico_options=[10, 15, 20, 30], motivi_mancata=["assente", "chiuso", "altro"],
)
ADMIN_USER = dict(id=1, username="demo", email="demo@example.test", company_name="Logistica Demo",
                  plan="business", plan_status="active", created_at="2026-10-03T10:00:00Z",
                  is_active=True, customer_code="GF001")
BUTTON_PROPERTIES = ("fontFamily", "fontSize", "fontWeight", "borderRadius", "minHeight",
                     "backgroundColor", "color")
INPUT_PROPERTIES = ("fontFamily", "fontSize", "borderRadius", "minHeight")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def styles(locator, properties):
    return locator.evaluate("(el, names) => {const s=getComputedStyle(el);return Object.fromEntries(names.map(name=>[name,s[name]]));}", list(properties))


def fit(page, selector, minimum_width=0, minimum_height=0):
    element = page.locator(selector)
    element.wait_for(state="visible")
    box = element.bounding_box()
    assert box and box["width"] >= minimum_width and box["height"] >= minimum_height, (selector, box)
    assert box["x"] >= -1 and box["x"] + box["width"] <= page.viewport_size["width"] + 1, (selector, box)
    return box


def root_fit(page, name):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), (
        name, page.viewport_size, page.evaluate("""() => [...document.querySelectorAll('body *')]
          .filter(el=>{const r=el.getBoundingClientRect();return r.width && r.right > innerWidth + 2;})
          .slice(0,20).map(el=>({id:el.id,cls:String(el.className),width:el.getBoundingClientRect().width,
                              right:el.getBoundingClientRect().right}))"""))


def labels(page, selector, width):
    table = page.locator(selector)
    table.wait_for(state="visible")
    page.evaluate("GFDesignSystem.enhance()")
    assert table.get_attribute("data-gf-responsive") == "cards", selector
    cells = table.locator("tbody tr:first-child td")
    assert cells.count() > 1, selector
    for cell in cells.all():
        if not cell.is_visible() or (cell.get_attribute("colspan") or "1") != "1":
            continue
        assert (cell.get_attribute("data-label") or "").strip(), (selector, cell.inner_text())
    if width < 640:
        assert table.locator("tbody tr").first.evaluate("(el) => ['block','grid','flex'].includes(getComputedStyle(el).display)"), selector
        assert table.locator("tbody tr").first.locator("button").count(), selector
        for button in table.locator("tbody tr").first.locator("button").all():
            assert button.is_visible(), (selector, button.inner_text())
            box = button.bounding_box()
            assert box and box["x"] >= -1 and box["x"] + box["width"] <= width + 1, (selector, box)


def draw_signature(page, selector):
    page.locator(selector).scroll_into_view_if_needed()
    box = fit(page, selector, minimum_width=220, minimum_height=100)
    page.mouse.move(box["x"] + 20, box["y"] + 30)
    page.mouse.down()
    page.mouse.move(box["x"] + 70, box["y"] + 55, steps=5)
    page.mouse.up()


def main():
    output = ROOT / "test-results" / "design-system"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors, mutations, checked = [], [], []
    state = dict(surface="kit", customer_error=False)
    def handle(route):
        parsed = urlparse(route.request.url)
        path = parsed.path
        if parsed.hostname != "127.0.0.1":
            route.abort()
            return
        if path == "/api/billing/catalog.js":
            catalog = {key:dict(LIMITS, name=key.title(), price_eur=price)
                       for key, price in (("starter",29),("business",59),("pro",99))}
            route.fulfill(content_type="application/javascript",body="window.GF_PLANS="+json.dumps(catalog))
            return
        if not path.startswith("/api/"):
            route.continue_()
            return
        if route.request.method not in ("GET", "HEAD"):
            mutations.append(dict(path=path, method=route.request.method))
            route.fulfill(status=405,content_type="application/json",body='{"detail":"Write blocked in UI test"}')
            return
        if path == "/api/customers" and state["customer_error"]:
            route.fulfill(status=503,content_type="application/json",body='{"detail":"Servizio di prova temporaneamente indisponibile"}')
            return
        data = {
            "/api/me": dict(ME,authenticated=state["surface"]=="mobile"),
            "/api/customers": CUSTOMERS, "/api/vehicles": VEHICLES, "/api/vehicles/usage": USAGE,
            "/api/drivers": DRIVERS, "/api/deposits": DEPOSITS, "/api/agents": [],
            "/api/routes": ROUTES, "/api/routes/operativi": ROUTES[:2],
            "/api/settings": dict(agents_enabled=True,delivery_signature_enabled=True),
            "/api/company-profile": dict(ME,company_email="demo@example.test"),
            "/api/account-profile": dict(name="Demo",email="demo@example.test",role="admin"),
            "/api/onboarding/status": dict(completed=True,workspace_operational=True,steps=[]),
            "/api/resources/availability": dict(vehicles=VEHICLES,drivers=DRIVERS),
            "/api/notifications": dict(items=[],unread=0),
            "/api/driver/admin/chat-threads": [], "/api/driver/admin/unread": dict(total=0,routes=[]),
            "/api/billing/my-plan": dict(ME,billing={},usage={"resources":{"customers":{"used":1}}}),
            "/api/billing/overview": dict(plan=dict(name="Business",status="active"),company={},invoices=[],payments=[]),
            "/api/reports/summary": dict(metrics={},charts={},insights=[],drivers=[],customers=[],agents=[]),
            "/api/driver/me": dict(authenticated=True,driver_name="Marco Rossi",company_name="Logistica Demo"),
            "/api/driver/routes": [ROUTES[0]],
            "/api/agent/me": dict(authenticated=True,agent_name="Agente Demo",company_name="Logistica Demo"),
            "/api/agent/customers": CUSTOMERS,
            "/api/admin/me": dict(authenticated=True,role="superadmin",display_name="Demo",username="demo",permissions={"all":True}),
            "/api/admin/profile": dict(display_name="Demo",username="demo",email="admin@example.test",avatar_initials="D"),
            "/api/admin/users": [ADMIN_USER],
            "/api/admin/system-errors/summary": dict(new=0),
            "/api/admin/overview": dict(
                kpi=dict(utenti_totali=1,nuovi_questo_mese=1,trial_attivi=0,abbonamenti_paganti=1,
                         mrr_stimato=0,ticket_aperti=0,ticket_totali=0,giri_totali=3,giri_questo_mese=3,
                         clienti_totali=1,scaduti_cancellati=0),
                andamento_iscrizioni=[],distribuzione_piani=[],ultimi_iscritti=[ADMIN_USER],ultimi_ticket=[]),
            "/api/public/tracking": dict(status="in_consegna",scheduled_date="2026-10-03",timezone="Europe/Rome",
                eta=dict(at="2026-10-03T15:35:00+02:00",source="execution",updated_at="2026-10-03T14:10:00+02:00"),
                stops_before=1,completed_at=None,refresh_after_seconds=30),
        }.get(path, {})
        if path.startswith("/api/driver/setup/"):
            data = dict(driver_name="Marco Rossi",email="marco@example.test")
        elif path.startswith("/api/agent/setup/"):
            data = dict(agent_name="Agente Demo",company_name="Logistica Demo")
        elif path.startswith("/api/operator/"):
            data = dict(state="unavailable",position=None) if path.endswith("/position") else EXECUTION
        elif path.startswith("/api/driver/routes/"):
            data = dict(state="unavailable",position=None) if path.endswith("/position") else EXECUTION
        elif "/chat/" in path:
            data = dict(messages=[],items=[]) if "admin" in path else []
        elif path.startswith("/api/routes/"):
            data = next((item for item in ROUTES if path==f"/api/routes/{item['id']}"),{})
        route.fulfill(content_type="application/json",body=json.dumps(data))

    def capture(page, name, width):
        page.evaluate("GFDesignSystem.enhance()")
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(output/f"{name.replace('/','-')}-{width}.png"),full_page=True,animations="disabled")
        root_fit(page,name)
        if os.getenv("GF_DESIGN_PREVIEW") == "1" and name in ("workspace-dashboard","workspace-clienti") and width in (390,1440):
            page.evaluate("window.scrollTo(0,0)")
            preview = page.screenshot(type="jpeg",quality=70,full_page=False,animations="disabled")
            print("GF_DESIGN_PREVIEW:" + name + ":" + str(width) + ":" + base64.b64encode(preview).decode("ascii"),flush=True)
        assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--gf-color-primary').trim().toLowerCase()") == "#0b63f6"
        checked.append(dict(page=name,width=width))

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for width in WIDTHS:
                    page = browser.new_page(viewport=dict(width=width,height=1000),device_scale_factor=1)
                    page.clock.set_fixed_time(datetime(2026,10,3,10,tzinfo=timezone.utc))
                    page.route("**/*",handle)
                    page.on("pageerror",lambda error:errors.append(str(error)))
                    state["surface"] = "kit"
                    page.goto(base+"/docs/design-system/ui-kit.html",wait_until="networkidle")
                    page.wait_for_function("!!window.GFDesignSystem")
                    primary = styles(page.get_by_role("button",name="Crea giro",exact=True),BUTTON_PROPERTIES)
                    field = styles(page.locator("#kitName"),INPUT_PROPERTIES)
                    for action_name in ("Elimina", "Conferma consegna"):
                        action = page.get_by_role("button",name=action_name,exact=True)
                        before_hover = styles(action,("backgroundColor","color"))
                        action.hover()
                        assert styles(action,("backgroundColor","color")) == before_hover,(action_name,width)
                    page.mouse.move(0,0)
                    assert page.evaluate("GFDesignSystem.breakpoints()") == dict(sm=640,md=768,lg=1024,xl=1440)
                    page.locator("#kitSwitch").focus()
                    page.keyboard.press("Space")
                    assert page.locator("#kitSwitch").is_checked()
                    page.locator("#kitDropdown summary").focus()
                    page.keyboard.press("Enter")
                    assert page.locator("#kitDropdown").evaluate("(el)=>el.open")
                    page.keyboard.press("Enter")
                    assert not page.locator("#kitDropdown").evaluate("(el)=>el.open")
                    page.locator("#kitTabDetails").focus()
                    page.keyboard.press("ArrowRight")
                    assert page.locator("#kitTabActivity").get_attribute("aria-selected") == "true"
                    assert page.locator("#kitPanelActivity").is_visible()
                    page.keyboard.press("ArrowLeft")
                    assert page.locator("#kitPanelDetails").is_visible()
                    page.locator("#kitDialogOpen").click()
                    fit(page,"#kitDialog")
                    assert page.locator("#kitDialogName").evaluate("(el)=>el===document.activeElement")
                    page.keyboard.press("Escape")
                    assert not page.locator("#kitDialog").is_visible()
                    assert page.locator("#kitDialogOpen").evaluate("(el)=>el===document.activeElement")
                    page.locator("#kitToast").click()
                    toast_message = page.get_by_text("Esempio completato senza modificare dati.",exact=True)
                    assert toast_message.is_visible()
                    assert toast_message.evaluate("(el)=>!!el.closest('[role=status]')")
                    labels(page,"#kitTable",width)
                    capture(page,"ui-kit",width)
                    state["surface"] = "workspace"
                    page.goto(base+"/static/dashboard/index.html",wait_until="networkidle")
                    page.evaluate("""async me => {
                        currentSessionUser=me;showGestionaleAfterLogin();await initApp();acceptCookieNotice();
                    }""",ME)
                    nav = page.locator("#app .nav-item[data-tab]").evaluate_all("(els)=>els.map(el=>el.dataset.tab)")
                    for name in ("dashboard","clienti","giro","mezzi","autisti","depositi","storico","settings","report"):
                        assert name in nav,name
                    for name in ("dashboard","clienti"):
                        page.evaluate("name=>showTab(name)",name)
                        page.wait_for_timeout(100)
                        primary_button = page.locator(f"#tab-{name} .btn-primary").first
                        assert styles(primary_button,BUTTON_PROPERTIES) == primary,(name,width,styles(primary_button,BUTTON_PROPERTIES),primary)
                        capture(page,"workspace-"+name,width)
                    page.evaluate("setCustomerView('list')")
                    labels(page,"#customerTableWrap table",width)
                    page.locator("#customerListSearch").fill("nessuna corrispondenza di prova")
                    assert page.locator("#customersBody .customer-empty").is_visible()
                    page.locator("#customerListSearch").fill("")
                    page.evaluate("openCustomerModal()")
                    page.locator("#customerOverlay").wait_for(state="visible")
                    assert styles(page.locator("#cNome"),INPUT_PROPERTIES) == field,(width,styles(page.locator("#cNome"),INPUT_PROPERTIES),field)
                    fit(page,"#customerOverlay .modal",minimum_width=200) if page.locator("#customerOverlay .modal").count() else root_fit(page,"customer-modal")
                    page.evaluate("closeCustomerModal()")
                    state["customer_error"] = True
                    assert page.evaluate("async()=>{try{await refreshCustomerDirectory();return false}catch{return true}}")
                    assert "Impossibile caricare" in page.locator("#customerCount").inner_text()
                    state["customer_error"] = False
                    page.evaluate("refreshCustomerDirectory()")
                    assert page.locator("#customersBody tr").count() == 1
                    capture(page,"workspace-customer-retry",width)
                    page.evaluate("showTab('depositi')")
                    page.wait_for_timeout(100)
                    labels(page,"#depositTableWrap table",width)
                    page.locator("#newDepositBtn").click()
                    page.locator("#depositOverlay").wait_for(state="visible")
                    assert styles(page.locator("#depNome"),INPUT_PROPERTIES) == field
                    page.locator("#depositOverlay").get_by_role("button",name="Annulla",exact=True).click()

                    for name in HTML_PAGES:
                        state["surface"] = name.split("/")[0]
                        suffix = "#" + TRACKING_TOKEN if name=="tracking/index" else ""
                        page.goto(base+"/static/"+name+".html"+suffix,wait_until="networkidle")
                        page.wait_for_function("!!window.GFDesignSystem")
                        capture(page,name,width)
                        if name=="admin/index":
                            page.evaluate("navigate('users')")
                            page.locator("#users-tbody tr").first.wait_for(state="visible")
                            labels(page,"#users-table-wrap table",width)
                            capture(page,"admin-users",width)
                        elif name=="agent/index":
                            page.locator("#customersBody tr").first.wait_for(state="visible")
                            labels(page,"table:has(#customersBody)",width)
                            page.evaluate("openCustomerModal(1)")
                            page.locator("#customerModal").wait_for(state="visible")
                            root_fit(page,"agent-customer-modal")
                            page.evaluate("closeCustomerModal()")
                        elif name=="driver/index":
                            page.evaluate("openExecution(1)")
                            page.evaluate("openDone(1);openSignatureModal()")
                            page.locator("#signatureCanvas").wait_for(state="visible")
                            page.wait_for_timeout(150)
                            draw_signature(page,"#signatureCanvas")
                            assert page.evaluate("getSignatureData().startsWith('data:image/png;base64,')")
                            capture(page,"driver-signature",width)
                            page.evaluate("closeSignatureModal();closeModal()")
                        elif name=="operator/index":
                            page.evaluate("openDone(1)")
                            page.locator("#operatorSignatureCanvas").wait_for(state="visible")
                            draw_signature(page,"#operatorSignatureCanvas")
                            page.locator("#operatorSigner").fill("Firmatario Demo")
                            assert page.evaluate("operatorSignaturePayload().signature_data.startsWith('data:image/png;base64,')")
                            capture(page,"operator-signature",width)
                            page.evaluate("closeModals()")
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        report = dict(widths=list(WIDTHS),pages=checked,errors=errors,blocked_writes=mutations)
        (output/"audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report,indent=2))
    assert not errors,"Browser script errors"
    assert not mutations,"Unexpected write request in Design System checks"
    print("Design System passed: components, pilot consistency, portals, retry, keyboard and signature geometry at 390/768/1024/1440.")


if __name__ == "__main__":
    main()
