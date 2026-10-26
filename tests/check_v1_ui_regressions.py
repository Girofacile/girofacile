"""V1 browser regressions use local pages and intercepted APIs only."""
import csv
import io
import json
import os
import threading
from datetime import datetime, timezone
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from check_management_design import (
    ROOT, QuietHandler, LIMITS, ME, VEHICLES, DRIVERS, DEPOSITS, CUSTOMERS, USAGE, ROUTES,
    sync_playwright,
)

WIDTHS = (390, 768, 900, 1024, 1440)


def main():
    output = ROOT / "test-results" / "v1-ui-regressions"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    archive = [dict(ROUTES[2], id=1000+i, nome=f"Archivio {i:03}", status="completato") for i in range(230)]
    archive[0]["nome"], archive[-1]["nome"] = " \t=1+1", "Giro d'Italia antico"
    driver_route = dict(ROUTES[0], id=42, nome='Giro d\'Italia "Nord"', can_start=True,
                        before_time=True, is_future=False, n_consegne=1, completate=0, mancate=0)
    customers = [dict(c, stato_geocodifica="verificato") for c in CUSTOMERS]
    state = dict(surface="dashboard", fail_history=False, history_pages=[], starts=[], offline=False, outcomes=[])
    errors, checks = [], []

    def handle(route):
        parsed = urlparse(route.request.url)
        path, params = parsed.path, parse_qs(parsed.query)
        if path == "/api/billing/catalog.js":
            catalog = {key: dict(LIMITS, name=key.title(), price_eur=price)
                       for key, price in (("starter", 29), ("business", 59), ("pro", 99))}
            route.fulfill(content_type="application/javascript", body="window.GF_PLANS="+json.dumps(catalog))
        elif path.startswith("/api/"):
            if state["offline"] and path.startswith("/api/driver/") and path != "/api/driver/me":
                route.abort("internetdisconnected")
                return
            if path == "/api/routes":
                if state["fail_history"]:
                    route.fulfill(status=503, content_type="application/json",
                                  body=json.dumps(dict(detail="Storico temporaneamente non disponibile")))
                    return
                page, size = int(params.get("page", ["1"])[0]), int(params.get("page_size", ["100"])[0])
                state["history_pages"].append(page)
                items = archive[(page-1)*size:page*size]
                data = (dict(items=items, total=len(archive), page=page, page_size=size,
                             next_page=page+1 if page*size<len(archive) else None)
                        if params.get("with_meta") == ["true"] else items)
            elif path.startswith("/api/driver/delivery/") and path.endswith("/missed"):
                assert route.request.method == "POST"
                state["outcomes"].append(dict(path=path, body=json.loads(route.request.post_data)))
                data = dict(ok=True)
            elif path == "/api/driver/routes/42/start":
                assert route.request.method == "POST"
                state["starts"].append(path)
                data = dict(ok=True)
            else:
                assert route.request.method in ("GET", "HEAD"), ("Unexpected mutation", path)
                data = {
                    "/api/me": dict(ME, authenticated=state["surface"] == "mobile"),
                    "/api/vehicles": VEHICLES, "/api/drivers": DRIVERS, "/api/deposits": DEPOSITS,
                    "/api/customers": customers, "/api/agents": [], "/api/routes/operativi": ROUTES[:2],
                    "/api/vehicles/usage": USAGE,
                    "/api/settings": dict(agents_enabled=True, delivery_signature_enabled=False),
                    "/api/company-profile": dict(ME, company_email="demo@example.test", has_ztl=True,
                                                 needs_tail_lift=True, has_time_windows=True),
                    "/api/account-profile": dict(name="Demo", email="demo@example.test", role="admin"),
                    "/api/onboarding/status": dict(completed=True, workspace_operational=True, steps=[]),
                    "/api/resources/availability": dict(vehicles=VEHICLES, drivers=DRIVERS),
                    "/api/notifications": dict(items=[], unread=0),
                    "/api/driver/admin/chat-threads": [], "/api/driver/admin/unread": dict(total=0, routes=[]),
                    "/api/reports/summary": dict(metrics={}, charts={}, insights=[], drivers=[], customers=[], agents=[]),
                    "/api/billing/my-plan": dict(ME, billing={}, usage={"resources":{"customers":{"used":1}}}),
                    "/api/driver/me": dict(authenticated=True, driver_name="Marco Rossi", company_name="Logistica Demo"),
                    "/api/driver/routes": [driver_route],
                    "/api/driver/routes/42": dict(route=dict(driver_route, status="in_corso"),
                        consegne=[dict(driver_route["consegne"][0], status="in_attesa")],
                        progress=dict(totale=1, completate=0, mancate=0, rimanenti=1, percentuale=0, prossima_idx=0),
                        settings=dict(delivery_signature_enabled=False), tempo_scarico_options=[10, 15, 20]),
                }.get(path, {})
                if path.startswith("/api/routes/") and path.rsplit("/", 1)[-1].isdigit():
                    rid = int(path.rsplit("/", 1)[-1])
                    data = next((r for r in archive if r["id"] == rid), ROUTES[0])
                if "/position" in path:
                    data = dict(state="unavailable", position=None, route_status="programmato")
                if "/chat/" in path:
                    data = dict(messages=[], items=[])
            route.fulfill(content_type="application/json", body=json.dumps(data))
        elif parsed.hostname != "127.0.0.1":
            route.abort()
        else:
            route.continue_()

    def prepare(browser, width, surface):
        state["surface"] = surface
        page = browser.new_page(viewport=dict(width=width, height=1000), device_scale_factor=1)
        page.clock.set_fixed_time(datetime(2026, 10, 3, 10, tzinfo=timezone.utc))
        page.route("**/*", handle)
        page.on("pageerror", lambda error: errors.append(str(error)))
        return page

    def dashboard(browser, width):
        page = prepare(browser, width, "dashboard")
        page.goto(base+"/static/dashboard/index.html", wait_until="networkidle")
        page.evaluate("""async me => {
            currentSessionUser=me; showGestionaleAfterLogin();
            await initApp(); acceptCookieNotice();
        }""", ME)
        return page

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**({"channel":"chrome"} if os.name == "nt" else {}), headless=True)
            try:
                page = dashboard(browser, 1024)
                state["fail_history"] = True
                page.evaluate("showTab('storico')")
                page.locator("#historyError").wait_for(state="visible")
                assert "temporaneamente" in page.locator("#historyErrorMessage").inner_text()
                assert page.locator("#historyPage").is_hidden()
                state["fail_history"] = False
                state["history_pages"].clear()
                page.locator("#historyError").get_by_role("button", name="Riprova").click()
                page.locator("#historyPage").wait_for(state="visible")
                assert state["history_pages"] == [1, 2, 3]
                # Settimana: al massimo 3 giri per giorno, gli altri con "Mostra altri".
                week = page.locator("#historyWeek")
                more = week.get_by_role("button", name="Mostra altri 227")
                assert more.is_visible() and week.locator("li > button.gf-list-item").count() == 3
                week.screenshot(path=str(output/"storico-settimana.png"))
                more.click()
                assert week.locator("li > button.gf-list-item").count() == 230
                week.get_by_role("button", name="Mostra meno").click()
                assert week.locator("li > button.gf-list-item").count() == 3
                page.locator("#historySearch").fill("Giro d'Italia antico")
                assert page.locator("#historyResultsList tbody tr").count() == 1
                assert "Giro d'Italia antico" in page.locator("#historyResultsList").inner_text()
                page.evaluate("GFHistory.clear()")
                with page.expect_download() as pending:
                    page.locator("#historyPage").get_by_role("button", name="Esporta", exact=True).click()
                content = Path(pending.value.path()).read_text(encoding="utf-8-sig")
                exported = list(csv.DictReader(io.StringIO(content), delimiter=";"))
                assert len(exported) == 230
                assert any(row["Giro"] == "' \t=1+1" for row in exported)
                checks.append("history error/retry, 230 routes, old-route search, safe CSV")
                page.close()
                for width in WIDTHS:
                    page = dashboard(browser, width)
                    page.evaluate("showTab('clienti')")
                    page.locator("#tab-clienti .cx-cb").first.check()
                    bar = page.locator("#customerBulkBar")
                    bar.wait_for(state="visible")
                    box = bar.bounding_box()
                    assert box and box["x"] >= -1 and box["x"]+box["width"] <= width+1, (width, box)
                    nav = page.locator("#gfMobileBottomNavV62")
                    if width <= 1024:
                        assert nav.is_visible()
                        nav_box = nav.bounding_box()
                        assert box["y"]+box["height"] <= nav_box["y"]+1, (width, box, nav_box)
                    else:
                        assert nav.is_hidden()
                    page.screenshot(path=str(output/f"selection-{width}.png"), full_page=True, animations="disabled")
                    checks.append(f"{width}: selection bar inside viewport and above navigation")
                    page.close()
                page = prepare(browser, 390, "mobile")
                page.goto(base+"/static/mobile/index.html", wait_until="networkidle")
                page.locator("#appView").wait_for(state="visible")
                page.evaluate("""() => {
                    showView('giri',document.querySelectorAll('.bnav-btn')[1]);
                    showGiriTab('storico',document.querySelectorAll('.tab-btn')[1]);
                }""")
                page.wait_for_function("document.querySelectorAll('#storicoList .route-history-card').length===230")
                page.locator("#storicoList").get_by_role("button", name="Dettaglio", exact=True).last.click()
                page.locator("#dashRouteDetail").wait_for(state="visible")
                assert page.locator("#view-dashboard").is_visible()
                assert "Giro d'Italia antico" in page.locator("#dashRouteDetail").inner_text()
                checks.append("mobile: 230 archive routes and visible detail")
                page.close()
                page = prepare(browser, 390, "driver")
                page.goto(base+"/static/driver/index.html", wait_until="networkidle")
                page.locator("#driverApp").wait_for(state="visible")
                page.evaluate("GiroFacileGPS.sync=()=>{}")
                page.locator('[data-start-route="42"]').click()
                page.locator("#popupEarly").wait_for(state="visible")
                assert driver_route["nome"] in page.locator("#popupEarlyText").inner_text()
                page.locator("#popupConfirmBtn").click()
                page.locator("#view-execution").wait_for(state="visible")
                assert state["starts"] == ["/api/driver/routes/42/start"]
                checks.append("driver: apostrophe/quotes preserved through confirmation and POST")
                # Rete assente: l'esito resta sul telefono, il giro lo mostra, poi parte al ritorno della rete.
                page.locator("#deliveryList .btn-missed").first.wait_for(state="visible")
                state["offline"] = True
                page.locator("#deliveryList .btn-missed").first.click()
                page.locator("#motivoList .motivo-btn").first.click()
                page.locator("#modalMissed .btn-confirm").click()
                page.locator("#outboxBanner").wait_for(state="visible")
                assert page.locator("#modalMissed").is_hidden()
                assert "1 esito salvato" in page.locator("#outboxBannerText").inner_text()
                assert page.locator("#psMissed").inner_text() == "1"
                assert page.evaluate("JSON.parse(localStorage.getItem('gf-driver-outbox-undefined')).length") == 1
                assert state["outcomes"] == []
                page.screenshot(path=str(output/"driver-offline-outcome-390.png"), full_page=True)
                state["offline"] = False
                page.evaluate("window.dispatchEvent(new Event('online'))")
                page.locator("#outboxBanner").wait_for(state="hidden")
                assert [o["body"]["motivo"] for o in state["outcomes"]] == ["assente"], state["outcomes"]
                assert page.evaluate("JSON.parse(localStorage.getItem('gf-driver-outbox-undefined')).length") == 0
                checks.append("driver: missed outcome kept offline and sent when back online")
                page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        result = dict(checks=checks, errors=errors, widths=WIDTHS, mocked_start_requests=state["starts"])
        (output/"audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    assert not errors, errors


if __name__ == "__main__":
    main()
