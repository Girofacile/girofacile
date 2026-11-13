"""File-first imports and ERP assistance against isolated, real application APIs.

Run with a Playwright Chromium install, or set GF_TEST_BROWSER_EXECUTABLE to a
local Chromium binary. All browser requests are intercepted; no customer data,
production database, email provider or external shop is contacted.
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOW_SQLITE_LEGACY"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["BILLING_MODE"] = "disabled"
os.environ["ERROR_NOTIFICATIONS_ENABLED"] = "false"
os.environ["APP_BASE_URL"] = "https://girofacile.test"

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import current_user
from app.database import Base, get_db
from app.models import SupportTicket, User
from app.order_models import Order, OrderSource
from app.routers.orders import router as orders_router
from app.routers.order_sources import router as sources_router
from app.routers.support import router as support_router
from check_management_design import DEPOSITS, DRIVERS, LIMITS, ME, USAGE, VEHICLES


def check_width(browser, width, output):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(
            username="erp-browser-test", password_hash="test", plan="business",
            plan_status="active", company_name="Trasporti di prova",
            email="login@example.test", company_email="azienda@example.test",
        )
        db.add(user)
        db.commit()
        app = FastAPI()
        for router in (orders_router, sources_router, support_router):
            app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[current_user] = lambda: user
        with TestClient(app) as client:
            context = browser.new_context(viewport={"width": width, "height": 1000})
            page = context.new_page()
            errors = []
            requests = []
            fail_first_request = True
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                nonlocal fail_first_request
                parsed = urlparse(route.request.url)
                path = parsed.path
                if parsed.hostname != "orders.test":
                    route.abort()
                    return
                if path.startswith(("/api/orders", "/api/order-sources", "/api/support")):
                    if path == "/api/support/erp-connection":
                        requests.append(route.request.post_data_json)
                        if fail_first_request:
                            fail_first_request = False
                            route.fulfill(status=503, json={"detail": "Servizio temporaneamente non disponibile. Riprova."})
                            return
                    response = client.request(
                        route.request.method,
                        path + ("?" + parsed.query if parsed.query else ""),
                        content=route.request.post_data_buffer,
                        headers={"Content-Type": route.request.headers.get("content-type", "application/json")},
                    )
                    route.fulfill(status=response.status_code, body=response.text, content_type="application/json")
                    return
                if path == "/api/billing/catalog.js":
                    route.fulfill(content_type="application/javascript", body="window.GF_PLANS=" + json.dumps({
                        key: dict(LIMITS, name=key, price_eur=29)
                        for key in ("starter", "business", "pro")
                    }))
                    return
                if not path.startswith("/api/"):
                    relative = "static/dashboard/index.html" if path == "/dashboard" else path.lstrip("/")
                    file = (ROOT / relative).resolve()
                    if file.is_relative_to(ROOT) and file.is_file():
                        route.fulfill(path=str(file))
                    else:
                        route.fulfill(status=404, body="")
                    return
                route.fulfill(json={
                    "/api/me": {"authenticated": False}, "/api/settings": {},
                    "/api/sector-config": {}, "/api/customers": [],
                    "/api/deposits": DEPOSITS, "/api/vehicles": VEHICLES,
                    "/api/drivers": DRIVERS, "/api/vehicles/usage": USAGE,
                    "/api/agents": [], "/api/routes": [],
                    "/api/notifications": {"items": [], "unread": 0},
                    "/api/notifications/count": {"unread": 0},
                    "/api/driver/admin/chat-threads": [],
                    "/api/driver/admin/unread": {"total": 0, "routes": []},
                    "/api/onboarding/status": {"completed": True, "workspace_operational": True, "steps": []},
                }.get(path, {}))

            page.route("**/*", handle)
            page.goto("http://orders.test/dashboard", wait_until="networkidle")
            owner = dict(ME, company_name=user.company_name, email=user.email, company_email=user.company_email)
            page.evaluate("owner=>{currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();showTab('ordini-collegamenti');}", owner)
            expect(page.locator("#sourceFileOption")).to_be_visible()
            expect(page.locator("#sourceErpOption")).to_be_visible()
            file_box = page.locator("#sourceFileOption").bounding_box()
            erp_box = page.locator("#sourceErpOption").bounding_box()
            # Tre riquadri affiancati: il file è il primo (a sinistra, o sopra quando lo schermo è stretto).
            assert file_box["x"] < erp_box["x"] or file_box["y"] < erp_box["y"]
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            page.screenshot(path=str(output / f"file-first-{width}.png"), full_page=True)

            page.locator("#sourceErpOption").get_by_role("button").click()
            expect(page.locator("#erpRequestForm")).to_be_visible()
            page.locator("#erpRequestSubmit").click()
            assert not requests, "HTML validation must stop an empty request"
            page.locator("#erpSoftware").fill("Gestionale <script>prova</script>")
            page.locator("#erpVersion").fill("2026")
            page.locator("#erpMessage").fill("Riceviamo ordini dai clienti e vorremmo importarli automaticamente.")
            page.locator("#erpPhone").fill("021234567")
            page.locator("#erpRequestNotify").uncheck()
            page.locator("#erpRequestSubmit").click()
            expect(page.locator("#erpRequestStatus")).to_contain_text("temporaneamente")
            expect(page.locator("#erpRequestSubmit")).to_be_enabled()
            expect(page.locator("#erpSoftware")).to_have_value("Gestionale <script>prova</script>")
            assert db.query(SupportTicket).count() == 0
            page.screenshot(path=str(output / f"erp-retry-{width}.png"), full_page=True)

            # Two simultaneous submissions must create only one ticket.
            page.evaluate("""() => {
              const event={preventDefault(){}};
              GFOrderSources.submitErpRequest(event);
              GFOrderSources.submitErpRequest(event);
            }""")
            expect(page.locator("#erpRequestSuccess")).to_contain_text("inviata")
            assert len(requests) == 2
            ticket = db.query(SupportTicket).one()
            assert ticket.user_id == user.id and ticket.email == "azienda@example.test"
            assert ticket.tipo == "collegamento_gestionale" and ticket.status == "aperto"
            assert ticket.notify_on_resolution is False
            assert "Gestionale <script>prova</script>" in ticket.oggetto
            assert "021234567" in ticket.messaggio
            assert db.query(OrderSource).count() == 0
            assert page.locator("#sourceWizard script").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            page.screenshot(path=str(output / f"erp-sent-{width}.png"), full_page=True)

            page.locator("#sourceWizard").get_by_role("button", name="Le mie richieste", exact=True).click()
            expect(page.locator("#supportTicketHistoryV1")).to_contain_text(ticket.oggetto)
            page.evaluate("closeSupportTicketModalV60()")
            page.locator("#ordersConnectionsNewSource").click()
            expect(page.locator("#orderImportFile")).to_be_visible()
            page.locator("#orderImportName").fill("Ordini di prova")
            page.locator("#orderImportFile").set_input_files({
                "name": "ordini.csv", "mimeType": "text/csv",
                "buffer": b"NOrdine;RagioneSociale;IndSped;Pedana;NColli\nPROVA-001;Cliente;Via Roma 1;No;3\n",
            })
            page.get_by_role("button", name="Continua", exact=True).click()
            page.locator("#orderImportCommit").click()
            expect(page.locator("#orderImportReport")).to_contain_text("Importazione completata")
            assert db.query(Order).one().external_id == "PROVA-001"
            assert db.query(OrderSource).one().kind == "file"
            assert not errors, errors
            context.close()
    engine.dispose()


def main():
    os.environ["ORDER_CONNECTOR_KEY"] = Fernet.generate_key().decode()
    output = ROOT / "test-results" / "erp-import-responsive"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        executable = os.getenv("GF_TEST_BROWSER_EXECUTABLE")
        browser = playwright.chromium.launch(
            headless=True, executable_path=executable,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        for width in (390, 768, 1024, 1440):
            check_width(browser, width, output)
        browser.close()
    print("File-first layout, ERP validation/retry/single submission/history, and real CSV import passed at 390/768/1024/1440 px")


if __name__ == "__main__":
    main()
