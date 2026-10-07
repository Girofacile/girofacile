"""Browser layout smoke tests for electric benefits; run explicitly, not during pytest.

Uses the committed HTML/CSS/JS and a local HTTP server with mocked API responses.
No deployed app, production database or paid provider is contacted.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
import json
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.plan_catalog import PLAN_LIMITS, PLAN_PRICES
from app.services.plans import _vehicle_usage_report


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    from playwright.sync_api import sync_playwright

    owner = SimpleNamespace(plan="business", plan_status="active", plan_expires_at=None)
    fleet = _vehicle_usage_report(owner, 11, 1)
    catalog = {key: {**limits, "price_eur": PLAN_PRICES[key]["price_eur"]}
               for key, limits in PLAN_LIMITS.items()}
    me = {"authenticated": True, "role": "admin", "username": "browser-test",
          "company_name": "Verifica mobilità", "company_sector": "distribution",
          "workspace_operational": True, "onboarding_completed": True,
          "plan": "business", "plan_name": "Business", "plan_status": "active",
          "limits": PLAN_LIMITS["business"]}
    vehicle = {"id": 1, "nome": "Veicolo elettrico", "alimentazione": "elettrico",
               "consumo_kwh_100km": 20, "consumo_primario_100km": 0,
               "consumo_l_100km": 0, "capacita_kg": 1000, "capacita_colli": 100,
               "ha_sponda": False, "accesso_ztl": False, "toll_class": "B"}

    output = ROOT / "test-results" / "electric-responsive"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def handle(route):
        path = urlparse(route.request.url).path
        if path == "/api/billing/catalog.js":
            route.fulfill(content_type="application/javascript",
                          body="window.GF_PLANS = " + json.dumps(catalog) + ";")
            return
        if path.startswith("/api/"):
            data = {
                "/api/me": me, "/api/vehicles/usage": fleet, "/api/vehicles": [vehicle],
                "/api/billing/my-plan": {**me, "usage": {"resources": {"vehicles": {
                    **fleet, "used": fleet["total_used"], "limit": fleet["total_limit"]}}},
                    "billing": {"checkout_enabled": False}},
                "/api/company-profile": me,
                "/api/onboarding/status": {"completed": True, "workspace_operational": True},
            }.get(path, [] if any(word in path for word in (
                "customers", "deposits", "drivers", "agents", "routes", "notifications")) else {})
            route.fulfill(content_type="application/json", body=json.dumps(data))
        elif urlparse(route.request.url).hostname != "127.0.0.1":
            route.abort()
        else:
            route.continue_()

    def fit(page, selector):
        locator = page.locator(selector)
        assert locator.count(), f"Missing element: {selector}"
        visible = 0
        for element in locator.all():
            if not element.is_visible():
                continue
            visible += 1
            box = element.bounding_box()
            assert box and box["width"] > 0, selector
            assert box["x"] >= -1 and box["x"] + box["width"] <= page.viewport_size["width"] + 1, (
                selector, page.viewport_size, box)
            assert element.evaluate("(el) => el.scrollWidth <= el.clientWidth + 2"), selector
        assert visible, f"All elements hidden: {selector}"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for width in (320, 390, 768, 1024, 1440):
                    page = browser.new_page(viewport={"width": width, "height": 1000})
                    page.route("**/*", handle)
                    # Filled below with the committed component IDs.
                    check_pages(page, base, width, output, fit)
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("Electric mobility browser layouts passed at 320, 768 and 1440 pixels.")


def check_pages(page, base, width, output, fit):
    import re
    page.goto(base + "/static/landing/index.html", wait_until="networkidle")
    title = page.get_by_role("heading", name=re.compile("Più spazio alla mobilità elettrica"))
    assert title.count() == 1
    for index, key in enumerate(PLAN_LIMITS):
        card = page.locator("#publicPricing .pricing-card").nth(index)
        assert card.get_by_text(re.compile(r"\+" + str(PLAN_LIMITS[key]["electric_vehicle_bonus"]) +
                                           r"\s+veicol")).count()
    fit(page, "#publicPricing .pricing-card")
    fit(page, ".electric-inner")
    fit(page, "#electricPlanBonuses .electric-plan-bonus")
    page.screenshot(path=str(output / f"landing-overflow-check-{width}.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), page.evaluate("""() =>
        [...document.querySelectorAll('body *')].filter(el => {
          const box=el.getBoundingClientRect();return box.width && box.right > innerWidth + 2;
        }).slice(0,25).map(el => ({tag:el.tagName,id:el.id,cls:el.className,
          right:el.getBoundingClientRect().right,width:el.getBoundingClientRect().width}))""")
    title.scroll_into_view_if_needed()
    page.screenshot(path=str(output / f"landing-{width}.png"), full_page=True)

    page.goto(base + "/static/dashboard/index.html", wait_until="networkidle")
    page.evaluate("""async () => {
        showGestionaleAfterLogin(false);
        document.querySelectorAll("#app .tab").forEach(el => el.classList.add("hidden"));
        document.getElementById("tab-mezzi").classList.remove("hidden");
        await loadVehicles();
        resetVehicleForm();
        createFleetVehicle();
    }""")
    panel = page.locator("#tab-mezzi")
    page.locator("#vehicleDrawer").wait_for(state="visible")
    usage = panel.locator("details.fleet-usage")
    if usage.count() and not usage.evaluate("(el) => el.open"):
        usage.locator("summary").click()
    assert panel.get_by_text("Mezzi inclusi nel piano", exact=False).count()
    assert panel.get_by_text("Bonus mobilità elettrica", exact=False).count()
    assert panel.get_by_text(re.compile(r"10\s*/\s*10")).count()
    assert panel.get_by_text(re.compile(r"1\s*/\s*2")).count()
    page.locator("#vFuelType").select_option("elettrico")
    hint = panel.get_by_text("Questo veicolo rientra nel bonus mobilità elettrica", exact=False).first
    hint.wait_for(state="visible")
    # Check each new quota card and the form message in the actual responsive page.
    for text in ("Mezzi inclusi nel piano", "Bonus mobilità elettrica"):
        node = panel.get_by_text(text, exact=False).first
        box = node.bounding_box()
        assert box and 0 <= box["x"] and box["x"] + box["width"] <= width + 1
    fit(page, "#vehicleUsageSummary .gf-vehicle-usage-card")
    fit(page, "#vehicleElectricBonusHint")
    fit(page, "#vFuelType")
    hint.scroll_into_view_if_needed()
    page.screenshot(path=str(output / f"dashboard-form-{width}.png"), full_page=True)

    page.goto(base + "/static/mobile/index.html", wait_until="networkidle")
    page.evaluate("async () => { showView('altro'); await showSubView('mezzi'); }")
    mobile_panel = page.locator("#subViewContent")
    assert mobile_panel.get_by_text("Mezzi inclusi nel piano", exact=False).count()
    assert mobile_panel.get_by_text("Bonus mobilità elettrica", exact=False).count()
    assert mobile_panel.get_by_text(re.compile(r"10\s*/\s*10")).count()
    assert mobile_panel.get_by_text(re.compile(r"1\s*/\s*2")).count()
    fit(page, "#subViewContent")
    fit(page, "#subViewContent .gf-vehicle-usage-card")
    page.screenshot(path=str(output / f"mobile-mezzi-{width}.png"), full_page=True)
    page.evaluate("async () => { await openAddVehicle(); }")
    fuel = page.locator("#mModalBody select:has(option[value='elettrico'])")
    fuel.select_option("elettrico")
    modal_hint = page.locator("#mModalBody").get_by_text(
        "Questo veicolo rientra nel bonus mobilità elettrica", exact=False).first
    modal_hint.wait_for(state="visible")
    fit(page, "#mModalBody")
    fit(page, "#mobileVehicleBonusHint")
    fit(page, "#mModalBody select:has(option[value='elettrico'])")
    page.screenshot(path=str(output / f"mobile-form-{width}.png"), full_page=True)
    page.evaluate("closeMModal(); openLogin(); mobileToggleSignup(true);")
    for key in PLAN_LIMITS:
        card = page.locator(f".plan-card[data-plan='{key}']")
        assert card.get_by_text(re.compile(r"\+" + str(PLAN_LIMITS[key]["electric_vehicle_bonus"]) +
                                           r"\s+veicol")).count()
    fit(page, ".plan-card[data-plan]")
    page.screenshot(path=str(output / f"mobile-plans-{width}.png"), full_page=True)



if __name__ == "__main__":
    main()
