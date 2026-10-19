"""Dashboard mobile browser regression checks with local static files and mocked APIs.

Run explicitly: python tests/check_dashboard_mobile.py
Screenshots and a report are written to test-results/dashboard-mobile.
The map renderer is a local placeholder: these checks cover dashboard layout and
interactions, not Leaflet tiles, coordinates, geocoding, or production services.
"""

import copy
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "test-results" / "ui-tools"))

from playwright.sync_api import expect, sync_playwright

from check_management_design import (
    CUSTOMERS,
    DEPOSITS,
    DRIVERS,
    LIMITS,
    ME,
    QuietHandler,
    USAGE,
    VEHICLES,
)

WIDTHS = (320, 390, 430, 768, 1440)
TODAY = "2026-10-19"
FIXED_TIME = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)


def resources(template, count, kind):
    rows = []
    for index in range(count):
        row = dict(template, id=index + 1)
        if kind == "driver":
            row.update(nome=f"Autista {index + 1}", cognome="Test")
        else:
            row.update(nome=f"Mezzo {index + 1}", targa=f"TEST{index + 1:03d}")
        rows.append(row)
    return rows


def route_fixture(route_id, status):
    return dict(
        id=route_id,
        nome=f"Giro consegne {route_id}",
        data_giro=TODAY,
        status=status,
        driver_id=1,
        vehicle_id=1,
        deposit_id=1,
        driver_name="Autista 1 Test",
        vehicle_name="Mezzo 1 · TEST001",
        totale_km=111.78,
        totale_minuti=95,
        costo_carburante=6.5,
        litri_stimati=3.57,
        consegne_count=3,
        completed_count=1 if status == "in_corso" else 0,
        missed_count=0,
        remaining_count=2 if status == "in_corso" else 3,
        orario_partenza="08:00",
        orario_rientro_stimato="09:35",
        rientro_deposito=True,
        consegne=[dict(
            id=route_id * 10 + index,
            customer_id=1,
            cliente_nome=f"Cliente {index + 1}",
            ordine=index + 1,
            indirizzo="Via Verdi 10, Milano",
            lat=45.47 + index / 1000,
            lon=9.2,
            delivery_status="completata" if index == 0 and status == "in_corso" else "da_consegnare",
            arrivo_stimato="08:25",
            peso_kg=50,
            colli=4,
            tempo_scarico_min=10,
        ) for index in range(3)],
    )


def scenarios():
    free = dict(
        name="all-free",
        company="Supermercati Iorio",
        operational=True,
        drivers=resources(DRIVERS[0], 3, "driver"),
        vehicles=resources(VEHICLES[0], 6, "vehicle"),
        routes=[],
        completed_deliveries=0,
        availability="success",
    )
    mixed = copy.deepcopy(free)
    mixed.update(name="mixed-availability", availability="warning")
    mixed["drivers"][0]["stato"] = "In servizio"
    mixed["drivers"][1]["stato"] = "Non disponibile"
    mixed["vehicles"][0]["stato"] = "In uso"
    mixed["vehicles"][1]["stato"] = "Manutenzione"

    unavailable = copy.deepcopy(free)
    unavailable.update(name="unavailable-resources", availability="warning")
    unavailable["drivers"][0]["stato"] = "Non disponibile"
    unavailable["vehicles"][0]["stato"] = "Manutenzione"

    no_resources = copy.deepcopy(free)
    no_resources.update(name="no-resources", drivers=[], vehicles=[], availability="neutral")

    active = copy.deepcopy(mixed)
    active.update(
        name="active-route",
        routes=[route_fixture(1, "in_corso"), route_fixture(2, "programmato"), route_fixture(3, "programmato")],
        completed_deliveries=1,
    )

    setup = copy.deepcopy(no_resources)
    setup.update(name="incomplete-setup", operational=False)

    large = copy.deepcopy(free)
    large.update(
        name="long-company-large-values",
        company="Supermercati Iorio e Figli Società Cooperativa di Distribuzione Alimentare Nazionale S.p.A.",
        drivers=resources(DRIVERS[0], 123, "driver"),
        vehicles=resources(VEHICLES[0], 175, "vehicle"),
        routes=[route_fixture(index + 1, "in_corso" if index < 123 else "programmato") for index in range(468)],
        completed_deliveries=12345,
        availability="warning",
    )
    for row in large["drivers"][:75]:
        row["stato"] = "In servizio"
    for row in large["vehicles"][:100]:
        row["stato"] = "In uso"
    return [free, mixed, unavailable, no_resources, active, setup, large]


def launch_options():
    executable = os.getenv("GF_TEST_BROWSER_EXECUTABLE")
    if not executable and Path("/usr/bin/chromium").is_file():
        executable = "/usr/bin/chromium"
    if executable:
        return dict(headless=True, executable_path=executable)
    channel = os.getenv("GF_TEST_BROWSER_CHANNEL") or ("chrome" if os.name == "nt" else None)
    return dict(headless=True, channel=channel)


def owner_for(case):
    return dict(
        ME,
        company_name=case["company"],
        company_city="Milano",
        workspace_operational=case["operational"],
        onboarding_completed=case["operational"],
    )


def api_handler(case, mutations, blocked_external):
    owner = owner_for(case)
    routes = case["routes"]
    by_id = {str(row["id"]): row for row in routes}

    def handle(request_route):
        request = request_route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if parsed.hostname != "127.0.0.1":
            blocked_external.add(parsed.hostname or request.url)
            request_route.abort()
            return
        if path == "/api/billing/catalog.js":
            catalog = {key: dict(LIMITS, name=key.title(), price_eur=price)
                       for key, price in [("starter", 29), ("business", 59), ("pro", 99)]}
            request_route.fulfill(content_type="application/javascript", body="window.GF_PLANS=" + json.dumps(catalog))
            return
        if not path.startswith("/api/"):
            request_route.continue_()
            return
        if request.method not in ("GET", "HEAD"):
            mutations.append(dict(path=path, method=request.method))
        data = {
            "/api/me": dict(owner, authenticated=False),
            "/api/sector-config": {},
            "/api/settings": dict(agents_enabled=False, delivery_signature_enabled=True),
            "/api/vehicles": case["vehicles"],
            "/api/drivers": case["drivers"],
            "/api/deposits": DEPOSITS,
            "/api/customers": CUSTOMERS,
            "/api/agents": [],
            "/api/routes": routes,
            "/api/routes/operativi": [row for row in routes if row["status"] != "completato"],
            "/api/dashboard/completed-deliveries-today": dict(count=case["completed_deliveries"]),
            "/api/vehicles/usage": USAGE,
            "/api/resources/availability": dict(vehicles=case["vehicles"], drivers=case["drivers"]),
            "/api/company-profile": dict(owner, company_email="demo@example.test"),
            "/api/account-profile": dict(name="Demo", email="demo@example.test", role="admin"),
            "/api/onboarding/status": dict(completed=case["operational"], workspace_operational=case["operational"], steps=[]),
            "/api/notifications": dict(items=[], unread=0),
            "/api/notifications/count": dict(unread=0),
            "/api/driver/admin/chat-threads": [],
            "/api/driver/admin/unread": dict(total=0, routes=[]),
            "/api/billing/my-plan": dict(owner, billing={}, usage={"resources": {"customers": {"used": len(CUSTOMERS)}}}),
            "/api/orders": dict(items=[], total=0, counts={}),
            "/api/orders/summary": dict(counts={}, total=0),
            "/api/order-planning/selection": dict(order_ids=[], orders=[]),
        }.get(path, {})
        route_match = re.fullmatch(r"/api/routes/(\d+)", path)
        if route_match:
            data = by_id.get(route_match.group(1), {})
        if "/chat/" in path:
            data = dict(messages=[], items=[])
        request_route.fulfill(content_type="application/json", body=json.dumps(data))

    return handle


def open_dashboard(page, case, base):
    page.clock.set_fixed_time(FIXED_TIME)
    page.goto(base + "/static/dashboard/index.html", wait_until="networkidle")
    page.evaluate("""async owner => {
        // Isolate map providers while retaining the application map host and layout.
        const placeholder = element => {
            if (!element) return;
            const content = document.createElement('div');
            content.dataset.testMapPlaceholder = 'true';
            content.setAttribute('role', 'img');
            content.setAttribute('aria-label', 'Mappa isolata per verifica del layout');
            content.style.cssText = 'position:absolute;inset:0;background:#e5ede6';
            element.replaceChildren(content);
            element.classList.add('gf-ref-map-ready');
        };
        window.GiroFacileDashboardMap = {
            render: (_id, _rows, element) => placeholder(element),
            renderEmpty: element => placeholder(element),
            reset: () => {}, highlight: () => {}, focusStop: () => {}
        };
        currentSessionUser = owner;
        showGestionaleAfterLogin();
        await initApp();
        acceptCookieNotice();
        applyWorkspaceStateV49(owner.workspace_operational);
        showTab('dashboard');
        await loadDashboardHome();
    }""", owner_for(case))
    expect(page.locator("#gfRefDetailLoading")).to_be_hidden()
    expect(page.locator("body")).to_have_class(re.compile(r"\bgf-dashboard-page-active\b"))
    page.wait_for_function("document.querySelector('#gfRefRouteDrawing [data-test-map-placeholder]') !== null")


def assert_no_overflow(page, label):
    excess = page.evaluate("document.documentElement.scrollWidth - innerWidth")
    assert excess <= 2, f"{label}: root overflows by {excess}px"


def assert_dashboard(page, case, width):
    label = f"{case['name']} at {width}px"
    assert_no_overflow(page, label)
    mobile = width <= 767
    identity = page.locator(".gf-header__mobile-identity")
    overview = page.locator(".gf-dashboard-overview")
    if not mobile:
        expect(identity).to_be_hidden()
        expect(overview).to_be_hidden()
        expect(page.locator("#dashMobileAvailability")).to_be_hidden()
        expect(page.locator("#dashMobileMapToggle")).to_be_hidden()
        expect(page.locator("#workspacePageTitle")).to_be_visible()
        return

    expect(identity).to_be_visible()
    expect(page.locator("#dashMobileCompany")).to_have_text(case["company"])
    expect(page.locator("#dashMobileDate")).to_contain_text("19")
    expect(page.locator("#dashMobileDate")).to_contain_text("2026")
    expect(page.locator("#workspacePageTitle")).to_be_hidden()

    if not case["operational"]:
        expect(page.locator("#workspaceEmptyDashboardV49")).to_be_visible()
        expect(page.locator("#gfRefEmptySetup")).to_be_visible()
        expect(page.locator("#gfRefEmptyChoices")).to_be_hidden()
        expect(page.locator("#gfRefEmptyAction")).to_be_visible()
        return

    expect(overview).to_be_visible()
    expect(page.locator("#dashMobileShortDate")).to_contain_text("19")
    kpis = [page.locator(f"#{name}") for name in
            ("dashTodayProgress", "dashTodayScheduled", "dashTodayCompletedDeliveries")]
    expected = [sum(row["status"] == "in_corso" for row in case["routes"]),
                sum(row["status"] == "programmato" and row["data_giro"] == TODAY for row in case["routes"]),
                case["completed_deliveries"]]
    boxes = []
    for kpi, value in zip(kpis, expected):
        expect(kpi).to_be_visible()
        expect(kpi).to_have_text(str(value))
        card = kpi.locator("xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' gf-stat-strip__cell ')][1]")
        boxes.append(card.bounding_box())
        assert kpi.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), f"{label}: clipped KPI value {value}"
    assert max(box["y"] for box in boxes) - min(box["y"] for box in boxes) <= 2, f"{label}: KPI cards wrap"
    assert boxes[0]["x"] < boxes[1]["x"] < boxes[2]["x"], f"{label}: unexpected KPI order"
    assert max(box["width"] for box in boxes) - min(box["width"] for box in boxes) <= 2, f"{label}: unequal KPI card widths"

    for kind, selector, busy_state in [
        ("drivers", "#dashMobileDriversCount", "In servizio"),
        ("vehicles", "#dashMobileVehiclesCount", "In uso"),
    ]:
        rows = case[kind]
        expected_count = f"{sum(row.get('stato') == busy_state for row in rows)}/{len(rows)}"
        actual = re.sub(r"\s", "", page.locator(selector).inner_text())
        assert actual == expected_count, f"{label}: {kind} {actual} != {expected_count}"
    availability = page.locator("#dashMobileAvailability")
    expect(availability).to_be_visible()
    expect(page.locator("#dashMobileResources")).to_have_attribute("aria-busy", "false")
    expect(availability).to_have_attribute("data-status", case["availability"])
    if case["name"] == "all-free":
        expect(availability).to_contain_text("Disponibili")
    elif case["name"] == "no-resources":
        expect(availability).to_contain_text("configurare")
    elif case["name"] == "unavailable-resources":
        expect(availability).to_contain_text("ridotta")
    else:
        expect(availability).to_contain_text("attività")

    active = expected[0] > 0
    expect(page.locator("#gfRefHeroWrap")).to_have_class(re.compile(r"\bhas-route\b" if active else r"\bis-empty\b"))
    if active:
        expect(page.locator("#gfRefOperationalDetail")).to_be_visible()
        expect(page.locator("#gfRefEmptyState")).to_be_hidden()
        expect(page.locator("#gfRefStopList li")).to_have_count(3)
    else:
        expect(page.locator(".gf-dashboard-mobile-status")).to_be_visible()
        expect(page.locator("#dashMobileResourceHint")).to_be_visible()
        if case["name"] in ("mixed-availability", "unavailable-resources"):
            free_drivers = sum(row.get("stato", "Disponibile") == "Disponibile" for row in case["drivers"])
            free_vehicles = sum(row.get("stato", "Disponibile") == "Disponibile" for row in case["vehicles"])
            hint = page.locator("#dashMobileResourceHint").inner_text()
            assert str(free_drivers) in hint and str(free_vehicles) in hint, f"{label}: unavailable resources counted as free: {hint}"

    nav = page.locator("#gfMobileBottomNavV62")
    expect(nav).to_be_visible()
    expect(nav.locator(":scope > button")).to_have_count(5)
    expect(nav.locator('[data-mobile-tab="dashboard"]')).to_have_attribute("aria-current", "page")
    nav_box = nav.bounding_box()
    assert nav_box["x"] >= 0 and nav_box["x"] + nav_box["width"] <= width + 1, f"{label}: navigation extends off screen"


def exercise_mobile_actions(page, output, width):
    toggle = page.locator("#dashMobileMapToggle")
    hero = page.locator("#gfRefHeroWrap")
    drawing = page.locator("#gfRefRouteDrawing")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    collapsed_height = drawing.bounding_box()["height"]
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(hero).to_have_class(re.compile(r"\bis-map-expanded\b"))
    page.wait_for_function("before => document.getElementById('gfRefRouteDrawing').getBoundingClientRect().height > before + 30", arg=collapsed_height)
    assert_no_overflow(page, f"expanded map at {width}px")
    capture(page, output / f"expanded-map-{width}.png")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(hero).not_to_have_class(re.compile(r"\bis-map-expanded\b"))

    for index, target in [(0, "ordini"), (1, "clienti")]:
        page.locator("#gfRefEmptyChoices > button").nth(index).click()
        expect(page.locator(f"#tab-{target}")).to_be_visible()
        expect(page.locator("body")).not_to_have_class(re.compile(r"\bgf-dashboard-page-active\b"))
        expect(page.locator(".gf-header__mobile-identity")).to_be_hidden()
        expect(page.locator("#workspacePageTitle")).to_be_visible()
        assert_no_overflow(page, f"{target} after dashboard action at {width}px")
        page.evaluate("showTab('dashboard')")
        expect(page.locator("#tab-dashboard")).to_be_visible()
        expect(page.locator("body")).to_have_class(re.compile(r"\bgf-dashboard-page-active\b"))
        expect(page.locator("#gfRefDetailLoading")).to_be_hidden()

    page.evaluate("showTab('settings')")
    expect(page.locator("body")).not_to_have_class(re.compile(r"\bgf-dashboard-page-active\b"))
    expect(page.locator("#workspacePageTitle")).to_be_visible()
    page.evaluate("showTab('dashboard')")
    expect(page.locator(".gf-header__mobile-identity")).to_be_visible()
    assert_no_overflow(page, f"returned dashboard at {width}px")


def capture(page, destination):
    page.evaluate("document.fonts.ready")
    page.evaluate("window.scrollTo(0, 0); document.activeElement?.blur()")
    page.screenshot(path=str(destination), full_page=True, animations="disabled")


def exercise_api_error(page, output):
    def fail_vehicles(request_route):
        request_route.fulfill(status=503, content_type="application/json", body='{"detail":"Isolated test failure"}')

    # A failed refresh must clear the previous green availability and counts.
    expect(page.locator("#dashMobileAvailability")).to_have_attribute("data-status", "success")
    page.route("**/api/vehicles", fail_vehicles)
    try:
        page.evaluate("loadDashboardHome()")
        expect(page.locator("#dashMobileAvailability")).to_have_attribute("data-status", "neutral")
        expect(page.locator("#dashMobileAvailability")).to_contain_text("non disponibili")
        expect(page.locator("#dashMobileDriversCount")).to_have_text("—")
        expect(page.locator("#dashMobileVehiclesCount")).to_have_text("—")
        expect(page.locator("#dashMobileResources")).to_have_attribute("aria-busy", "false")
        for selector in ("#dashMobileDriversCount", "#dashMobileVehiclesCount"):
            label = page.locator(selector).locator("..").get_attribute("aria-label")
            assert label and "non disponibile" in label, f"Stale accessible availability label: {label}"
        assert_no_overflow(page, "API error at 390px")
        capture(page, output / "api-error-390.png")
    finally:
        page.unroute("**/api/vehicles", fail_vehicles)
    page.evaluate("loadDashboardHome()")
    expect(page.locator("#dashMobileAvailability")).to_have_attribute("data-status", "success")


def main():
    output = ROOT / "test-results" / "dashboard-mobile"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    results, mutations, errors, blocked_external = [], [], [], set()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch_options())
            for case in scenarios():
                for width in WIDTHS:
                    context = browser.new_context(viewport=dict(width=width, height=1000), device_scale_factor=1)
                    page = context.new_page()
                    page.on("pageerror", lambda error, name=case["name"], size=width: errors.append(dict(case=name, width=size, error=str(error))))
                    page.route("**/*", api_handler(case, mutations, blocked_external))
                    try:
                        open_dashboard(page, case, base)
                        assert_dashboard(page, case, width)
                        capture(page, output / f"{case['name']}-{width}.png")
                        if case["name"] == "all-free" and width <= 767:
                            exercise_mobile_actions(page, output, width)
                            if width == 390:
                                exercise_api_error(page, output)
                                results.append(dict(case="api-error-and-recovery", width=width, passed=True))
                        if case["name"] == "incomplete-setup" and width <= 767:
                            page.locator("#gfRefEmptyAction").click()
                            expect(page.locator("#tab-company")).to_be_visible()
                            expect(page.locator("body")).not_to_have_class(re.compile(r"\bgf-dashboard-page-active\b"))
                        results.append(dict(case=case["name"], width=width, passed=True))
                    except Exception:
                        capture(page, output / f"FAILED-{case['name']}-{width}.png")
                        raise
                    finally:
                        context.close()
            browser.close()
        assert not errors, f"Uncaught browser errors: {errors}"
        assert not mutations, f"Unexpected mutations (all intercepted locally): {mutations}"
    finally:
        server.shutdown()
        server.server_close()
        report = dict(
            results=results,
            browser_errors=errors,
            mocked_mutations=mutations,
            external_hosts_blocked=sorted(blocked_external),
            limitation="Local mocked API fixtures and placeholder map; no production, provider, tile, coordinate or geocoding validation.",
        )
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Passed {len(results)} dashboard cases; screenshots and report: {output}")
    print("Map is a local placeholder; real Leaflet/provider behavior is outside this check.")


if __name__ == "__main__":
    main()
