"""Collaborator presets, manual grants and mobile navigation with synthetic APIs.

Uses Playwright's bundled Chromium on every platform. No production server,
email or payment provider is contacted. All writes stay in an in-memory fixture.
Run: python tests/check_collaborators_ui.py
"""
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from app.services.company_permissions import CATALOG, DEPENDENCIES, normalize_permissions, permission_presets
from check_management_design import CUSTOMERS, DEPOSITS, DRIVERS, LIMITS, ME, ROUTES, USAGE, VEHICLES

WIDTHS = (390, 768, 1024, 1440)
PRESETS = {item["key"]: item for item in permission_presets()}
OWNER = dict(ME, username="Titolare Demo", email="owner@example.test", company_name="Demo")


def checked_permissions(page):
    return set(page.locator("#collaboratorPermissions input:checked").evaluate_all("(els) => els.map(el => el.value)"))


def assert_fits(page, selector=None):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Page overflow"
    if selector:
        box = page.locator(selector).bounding_box()
        assert box and box["x"] >= -1 and box["x"] + box["width"] <= page.viewport_size["width"] + 1, (selector, box)


def main():
    output = ROOT / "test-results" / "collaborators-ui"
    output.mkdir(parents=True, exist_ok=True)
    errors, unexpected_writes, checks, writes, company_writes, dialogs, invitation_writes = [], [], [], [], [], [], []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for width in WIDTHS:
                    context = browser.new_context(viewport=dict(width=width, height=1000), device_scale_factor=1)
                    page = context.new_page()
                    page.clock.set_fixed_time(datetime(2026, 10, 9, 10, tzinfo=timezone.utc))
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
                    state = dict(records=[], requests=[], fail_list=False, actor=False,
                                 company=dict(OWNER, company_email="owner@example.test"), allow_company_save=False,
                                 fail_invite=True)

                    def handle(route):
                        parsed = urlparse(route.request.url)
                        path, method = parsed.path, route.request.method
                        if parsed.hostname != "collaborators.test":
                            route.abort()
                            return
                        if path == "/api/billing/catalog.js":
                            catalog = {key: dict(LIMITS, name=key.title(), price_eur=price)
                                       for key, price in (("starter", 29), ("business", 59), ("pro", 99))}
                            route.fulfill(content_type="application/javascript", body="window.GF_PLANS=" + json.dumps(catalog))
                            return
                        if not path.startswith("/api/"):
                            relative = "static/dashboard/index.html" if path == "/dashboard" else path.lstrip("/")
                            file = (ROOT / relative).resolve()
                            if file.is_relative_to(ROOT) and file.is_file():
                                route.fulfill(path=str(file))
                            else:
                                route.fulfill(status=404, body="")
                            return
                        state["requests"].append(dict(path=path, method=method))
                        if state["actor"] and (path.startswith("/api/billing/") or path.startswith("/api/collaborators") or path.startswith("/api/onboarding/") or path == "/api/account-profile"):
                            route.fulfill(status=403, json=dict(detail="Operazione riservata al titolare"))
                            return
                        if path == "/api/collaborators/permissions":
                            route.fulfill(json=dict(permissions=CATALOG,
                                                    dependencies={k: sorted(v) for k, v in DEPENDENCIES.items()},
                                                    presets=list(PRESETS.values())))
                            return
                        if path == "/api/collaborators" and method == "GET":
                            if state["fail_list"]:
                                state["fail_list"] = False
                                route.fulfill(status=403, json=dict(detail="Accesso di prova negato"))
                            else:
                                route.fulfill(json=state["records"])
                            return
                        if (path == "/api/collaborators" and method == "POST") or (path == "/api/collaborators/1" and method == "PUT"):
                            payload = route.request.post_data_json
                            # The owner never supplies a collaborator password.
                            assert "password" not in payload, payload
                            previous = state["records"][0] if state["records"] else {}
                            row = dict(payload, id=1, permissions=normalize_permissions(payload["permissions"]), last_login=None,
                                       password_setup_required=True, invitation_status=previous.get("invitation_status", "failed"))
                            state["records"][:] = [row]
                            writes.append(dict(width=width, method=method, path=path, permissions=row["permissions"]))
                            result = dict(row)
                            if method == "POST":
                                result.update(invitation_sent=False, message="Collaboratore salvato, ma l’email di invito non è stata inviata.")
                            route.fulfill(json=result)
                            return
                        if path == "/api/collaborators/1/invite" and method == "POST":
                            assert route.request.post_data is None, "Invitation retries never contain passwords or a public token"
                            row = state["records"][0]
                            assert row["password_setup_required"] and row["is_active"]
                            sent = not state["fail_invite"]
                            state["fail_invite"] = False
                            row["invitation_status"] = "pending" if sent else "failed"
                            invitation_writes.append(dict(width=width, method=method, path=path, sent=sent))
                            route.fulfill(json=dict(row, invitation_sent=sent,
                                                    message="Nuovo invito inviato. Il link precedente non è più valido." if sent else "L’email di invito non è stata inviata. Riprova più tardi."))
                            return
                        if path == "/api/company-profile" and method == "PUT" and state["actor"] and state["allow_company_save"]:
                            state["allow_company_save"] = False
                            payload = route.request.post_data_json
                            state["company"].update(payload)
                            company_writes.append(dict(width=width, name=payload["company_name"]))
                            route.fulfill(json=state["company"])
                            return
                        if method not in ("GET", "HEAD"):
                            unexpected_writes.append(dict(width=width, path=path, method=method))
                            route.fulfill(status=405, json=dict(detail="Unexpected write blocked in UI test"))
                            return
                        data = {
                            "/api/me": dict(OWNER, authenticated=False),
                            "/api/settings": dict(agents_enabled=True, delivery_signature_enabled=False),
                            "/api/sector-config": {},
                            "/api/collaborator/context": {},
                            "/api/collaborator/account": dict(username="Collaboratore Demo", email="demo@example.test", role="Collaboratore"),
                            "/api/vehicles": VEHICLES, "/api/vehicles/usage": USAGE,
                            "/api/drivers": DRIVERS, "/api/deposits": DEPOSITS, "/api/customers": CUSTOMERS,
                            "/api/agents": [], "/api/routes": ROUTES, "/api/routes/operativi": ROUTES[:2],
                            "/api/company-profile": state["company"],
                            "/api/account-profile": dict(username="Titolare Demo", email="owner@example.test", role="admin"),
                            "/api/onboarding/status": dict(completed=True, workspace_operational=True, steps=[]),
                            "/api/resources/availability": dict(vehicles=VEHICLES, drivers=DRIVERS),
                            "/api/notifications": dict(items=[], unread=0),
                            "/api/notifications/count": dict(unread=0),
                            "/api/driver/admin/chat-threads": [], "/api/driver/admin/unread": dict(total=0, routes=[]),
                            "/api/reports/summary": dict(metrics={}, charts={}, insights=[], drivers=[], customers=[], agents=[]),
                            "/api/support/tickets": [],
                        }.get(path, {})
                        for item in ROUTES:
                            if path == f"/api/routes/{item['id']}":
                                data = item
                        if "/chat/" in path:
                            data = dict(messages=[], items=[])
                        route.fulfill(json=data)

                    def capture(name):
                        assert_fits(page)
                        page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True, animations="disabled")
                        if os.getenv("GF_COLLABORATORS_PREVIEW") == "1" and name in ("preset-operator", "operator-company-dirty") and width in (390, 1440):
                            preview = page.screenshot(type="jpeg", quality=70, full_page=False, animations="disabled")
                            print(f"GF_COLLABORATORS_PREVIEW:{name}:{width}:" + base64.b64encode(preview).decode("ascii"), flush=True)

                    def initialize_actor(grants):
                        state["actor"] = True
                        state["requests"].clear()
                        actor = dict(OWNER, is_collaborator=True, is_admin=False, username="Collaboratore Demo",
                                     email="demo@example.test", permissions=list(grants))
                        page.evaluate("async actor => { currentSessionUser=actor;await GFCompanyAccess.initialize(); }", actor)
                        page.wait_for_timeout(100)
                        assert not any(r["path"].startswith(("/api/billing/", "/api/onboarding/", "/api/collaborators")) for r in state["requests"]), state["requests"]

                    def forbidden_areas():
                        state["requests"].clear()
                        visible = page.locator("#app .tab:not(.hidden)").get_attribute("id")
                        page.evaluate("""async () => {
                            showTab('plan-account');showTab('billing-account');showTab('collaboratori');
                            openPlanAccountPage('pro');openUpgradePanelFor('business');renderUpgradeCards();
                            await openBillingPanel();renderSubscriptionControls({});
                            await subscriptionAction('cancel');await checkoutOrChangePlan();
                        }""")
                        assert page.locator("#app .tab:not(.hidden)").get_attribute("id") == visible
                        assert page.locator("#tab-plan-account").is_hidden()
                        assert page.locator("#tab-billing-account").is_hidden()
                        assert page.locator("#tab-collaboratori").is_hidden()
                        assert page.locator("#btnPlanActive").is_hidden()
                        assert page.locator('[data-tab="collaboratori"]').is_hidden()
                        assert not any(r["path"].startswith(("/api/billing/", "/api/onboarding/", "/api/collaborators")) for r in state["requests"]), state["requests"]

                    page.route("**/*", handle)
                    page.goto("http://collaborators.test/dashboard", wait_until="networkidle")
                    page.wait_for_function("!!window.GFCollaborators && !!window.GFCompanyAccess")
                    page.evaluate("owner => {currentSessionUser=owner;showGestionaleAfterLogin();acceptCookieNotice();showTab('collaboratori');}", OWNER)
                    page.wait_for_function("document.getElementById('collaboratorsBody').textContent.includes('Nessun collaboratore')")
                    page.locator("#tab-collaboratori button.btn-primary").first.click()
                    page.locator("#collaboratorName").fill("Collaboratore Demo")
                    page.locator("#collaboratorEmail").fill("demo@example.test")
                    assert page.locator("#collaboratorPassword").count() == 0
                    assert page.locator("#collaboratorSave").inner_text() == "Invia invito"
                    assert page.locator("#collaboratorPreset").input_value() == "operator"
                    assert checked_permissions(page) == set(PRESETS["operator"]["permissions"])
                    assert checked_permissions(page) == {item["key"] for item in CATALOG}
                    assert_fits(page, "#collaboratorDialog")
                    capture("preset-operator")

                    # Starting with a preset must leave every permission editable.
                    page.locator("#collaboratorPermissionsDetails summary").click()
                    page.locator('#collaboratorPermissions input[value="customers.delete"]').uncheck()
                    assert page.locator("#collaboratorPreset").input_value() == "custom"
                    expected = {item["key"] for item in CATALOG} - {"customers.delete"}
                    assert checked_permissions(page) == expected
                    page.locator("#collaboratorSave").click()
                    page.wait_for_function("document.getElementById('collaboratorsTotal').textContent==='1'")
                    assert set(state["records"][0]["permissions"]) == expected
                    page.locator("#collaboratorError").filter(has_text="email di invito non è stata inviata").wait_for(state="visible")
                    assert page.locator("#collaboratorDialog").is_visible()
                    assert page.locator("#collaboratorsPending").inner_text() == "1"
                    assert page.locator("#collaboratorsActive").inner_text() == "0"
                    assert page.locator("#collaboratorSave").inner_text() == "Salva modifiche"
                    # Saving succeeded even when email delivery failed. Retry uses the existing account.
                    page.locator("#collaboratorResendInvite").click()
                    page.locator("#collaboratorError").filter(has_text="Riprova più tardi").wait_for(state="visible")
                    assert page.locator("#collaboratorDialog").is_visible()
                    assert len([item for item in writes if item["width"] == width]) == 1
                    page.locator("#collaboratorResendInvite").click()
                    page.locator("#collaboratorInvitationNote").filter(has_text="Nuovo invito inviato").wait_for(state="visible")
                    assert state["records"][0]["invitation_status"] == "pending"
                    assert checked_permissions(page) == expected
                    capture("pending-invitation")
                    page.locator("#collaboratorDialog").get_by_role("button", name="Annulla", exact=True).click()

                    page.locator("#collaboratorsBody button").first.click()
                    assert page.locator("#collaboratorPreset").input_value() == "custom"
                    assert checked_permissions(page) == expected
                    for key in ("planner", "read_only", "operator"):
                        page.locator("#collaboratorPreset").select_option(key)
                        assert checked_permissions(page) == set(PRESETS[key]["permissions"]), key
                    page.locator("#collaboratorPreset").select_option("read_only")
                    page.locator("#collaboratorPermissionsDetails summary").click()
                    page.locator('#collaboratorPermissions input[value="routes.program"]').check()
                    assert page.locator("#collaboratorPreset").input_value() == "custom"
                    expected = set(normalize_permissions(PRESETS["read_only"]["permissions"] + ["routes.program"]))
                    assert checked_permissions(page) == expected
                    assert page.locator('#collaboratorPermissions input[value="routes.plan"]').is_checked()
                    assert page.locator('#collaboratorPermissions input[value="customers.read"]').is_checked()
                    assert not page.locator('#collaboratorPermissions input[value="customers.delete"]').is_checked()
                    page.locator("#collaboratorSave").click()
                    page.locator("#collaboratorDialog").wait_for(state="hidden")
                    page.locator("#collaboratorsBody").get_by_role("button", name="Gestisci").wait_for(state="visible")
                    page.wait_for_load_state("networkidle")
                    assert set(state["records"][0]["permissions"]) == expected
                    page.locator("#collaboratorSearch").fill("does not exist")
                    assert "Nessun collaboratore" in page.locator("#collaboratorsBody").inner_text()
                    page.locator("#collaboratorSearch").fill("Demo")
                    capture("owner-list")
                    page.locator("#collaboratorStatus").select_option("pending")
                    assert "Invito in attesa" in page.locator("#collaboratorsBody").inner_text()
                    page.locator("#collaboratorStatus").select_option("active")
                    assert "Nessun collaboratore" in page.locator("#collaboratorsBody").inner_text()
                    page.locator("#collaboratorStatus").select_option("")
                    # Legacy and accepted accounts retain their passwords and need no further invitation.
                    state["records"][0].update(password_setup_required=False, invitation_status="accepted")
                    page.evaluate("GFCollaborators.load()")
                    page.wait_for_function("document.getElementById('collaboratorsActive').textContent==='1'")
                    assert page.locator("#collaboratorsPending").inner_text() == "0"
                    page.locator("#collaboratorsBody button").first.click()
                    assert page.locator("#collaboratorResendInvite").is_hidden()
                    assert "ha già scelto" in page.locator("#collaboratorInvitationNote").inner_text()
                    page.locator("#collaboratorDialog").get_by_role("button", name="Annulla", exact=True).click()
                    state["records"][0].update(is_active=False, password_setup_required=True, invitation_status="disabled")
                    page.evaluate("GFCollaborators.load()")
                    page.wait_for_function("document.getElementById('collaboratorsInactive').textContent==='1'")
                    page.locator("#collaboratorStatus").select_option("inactive")
                    assert "Disattivato" in page.locator("#collaboratorsBody").inner_text()
                    page.locator("#collaboratorsBody button").first.click()
                    assert page.locator("#collaboratorResendInvite").is_hidden()
                    assert "disattivato" in page.locator("#collaboratorInvitationNote").inner_text()
                    page.locator("#collaboratorDialog").get_by_role("button", name="Annulla", exact=True).click()
                    page.locator("#collaboratorStatus").select_option("")


                    # Error handling and retry stay available instead of hiding failures.
                    state["fail_list"] = True
                    page.evaluate("GFCollaborators.load()")
                    page.locator("#collaboratorsBody").get_by_role("button", name="Riprova").wait_for(state="visible")
                    assert "Accesso di prova negato" in page.locator("#collaboratorsBody").inner_text()
                    page.locator("#collaboratorsBody").get_by_role("button", name="Riprova").click()
                    page.locator("#collaboratorsBody").get_by_role("button", name="Gestisci").wait_for(state="visible")

                    # Operator sees every operational area, including company/settings.
                    initialize_actor(PRESETS["operator"]["permissions"])
                    assert page.evaluate("GFCompanyAccess.can('company.update') && GFCompanyAccess.can('settings.update')")
                    forbidden_areas()
                    page.evaluate("showTab('company')")
                    # showTab starts the profile GET without awaiting its render.
                    # Networkidle may already belong to the previous page state.
                    page.wait_for_function("""name =>
                        document.getElementById('companyNameInput').value === name &&
                        companyProfileBaselineV29 === companyProfileSignatureV29()
                    """, arg=state["company"]["company_name"])
                    page.locator("#companyNameInput").fill("Demo operatore")
                    assert page.locator("#companyNameInput").input_value() == "Demo operatore"
                    state["requests"].clear()
                    state["allow_company_save"] = True
                    page.locator("#companySaveBar").wait_for(state="visible")
                    assert_fits(page, "#companySaveBar")
                    if width <= 768:
                        bar_box = page.locator("#companySaveBar").bounding_box()
                        nav_box = page.locator(".gf-mobile-bottom-nav-v62").bounding_box()
                        assert nav_box and bar_box["y"] + bar_box["height"] <= nav_box["y"] - 7, (bar_box, nav_box)
                        for control in ("#companySaveChangesBtn", "#companyDiscardChangesBtn"):
                            assert page.locator(control).bounding_box()["height"] >= 44
                    capture("operator-company-dirty")
                    page.locator("#companySaveChangesBtn").click()
                    page.wait_for_function("!companyProfileDirtyV29")
                    page.wait_for_load_state("networkidle")
                    assert page.locator("#companySaveBar").is_hidden()
                    assert not state["allow_company_save"], "Company update was not saved"
                    assert state["company"]["company_name"] == "Demo operatore"
                    assert not any(r["path"].startswith("/api/onboarding/") for r in state["requests"]), state["requests"]
                    assert page.locator(".onboarding-card-v29").is_hidden()
                    for name in ("clienti", "company", "settings"):
                        page.evaluate("name => showTab(name)", name)
                        page.locator("#tab-" + name).wait_for(state="visible")
                    assert page.locator("#settingDeliverySignature").is_enabled()
                    assert not page.locator("#companySaveChangesBtn").evaluate("el => el.classList.contains('collaborator-denied')")
                    if width <= 768:
                        page.get_by_role("button", name="Apri menu mobile", exact=True).click()
                        menu = page.locator("#gfMobileMoreMenuV62")
                        menu.wait_for(state="visible")
                        assert menu.get_by_role("button", name="⌂ Azienda", exact=True).is_visible()
                        assert menu.get_by_role("button", name="⚙ Impostazioni", exact=True).is_visible()
                        assert menu.get_by_role("button", name="♙ Collaboratori", exact=True).is_hidden()
                        menu.get_by_role("button", name="⚙ Impostazioni", exact=True).click()
                        assert page.locator("#tab-settings").is_visible()
                        assert menu.is_hidden()
                    else:
                        assert page.locator('[data-tab="company"]').is_visible()
                        assert page.locator('[data-tab="settings"]').is_visible()
                    capture("operator-settings")

                    state["requests"].clear()
                    page.evaluate("""() => {
                        currentSessionUser={...currentSessionUser,plan:'starter',limits:{...currentSessionUser.limits,has_reports:false}};
                        showTab('report');
                    }""")
                    page.locator("#tab-report").wait_for(state="visible")
                    locked_text = page.locator("#tab-report").inner_text()
                    assert "Contatta il titolare" in locked_text
                    assert "€" not in locked_text and "Business" not in locked_text and "Pro" not in locked_text, locked_text
                    assert page.locator("#tab-report [onclick*=openUpgrade]").count() == 0
                    assert not any(r["path"].startswith("/api/billing/") for r in state["requests"]), state["requests"]
                    capture("operator-unavailable-feature")

                    initialize_actor(PRESETS["read_only"]["permissions"])
                    page.evaluate("showTab('company')")
                    page.locator("#tab-company").wait_for(state="visible")
                    assert page.locator("#companyNameInput").is_disabled()
                    assert page.locator("#companySizeInput").is_disabled()
                    assert page.locator('#tab-company input[type="file"]').is_disabled()
                    assert not page.evaluate("companyProfileDirtyV29")
                    state["requests"].clear()
                    page.evaluate("""async () => {
                        openSupportPanelV49();
                        await submitSupportTicketV60();
                        await generateSupportTicketTextAIv67();
                    }""")
                    assert not any(r["path"].startswith("/api/support/") for r in state["requests"]), state["requests"]
                    assert not dialogs, dialogs
                    page.evaluate("showTab('clienti')")
                    page.locator("#tab-clienti").wait_for(state="visible")
                    page.wait_for_timeout(100)
                    assert page.locator('[onclick="openCustomerModal()"]').is_hidden()
                    assert not page.evaluate("GFCompanyAccess.can('customers.update')")
                    assert not page.evaluate("GFCompanyAccess.allowedTab('settings')")
                    forbidden_areas()
                    capture("read-only-customers")

                    # Reinitialization restores controls after changing grants;
                    # this does not introduce automatic live polling.
                    initialize_actor(PRESETS["operator"]["permissions"])
                    assert page.locator("#companyNameInput").is_enabled()
                    assert page.locator("#companySizeInput").is_enabled()
                    page.evaluate("showTab('clienti')")
                    page.locator('[onclick="openCustomerModal()"]').wait_for(state="visible")
                    state["requests"].clear()
                    page.evaluate("openProfilePanel()")
                    page.locator("#profileOverlay").wait_for(state="visible")
                    assert page.locator(".profile-plan-section").is_hidden()
                    assert page.locator("#profileEmail").get_attribute("readonly") is not None
                    assert not any(r["path"] == "/api/account-profile" for r in state["requests"]), state["requests"]
                    assert_fits(page)
                    page.evaluate("closeProfilePanel()")
                    checks.append(dict(width=width, presets=list(PRESETS), manual_save=True, dependency_expansion=True,
                                       retry=True, invitation_retry=True, password_owner_removed=True, pending_counts=True,
                                       operator_company_settings=True, forbidden_areas=True,
                                       read_only=True, restored_controls=True, own_profile=True))
                    context.close()
            finally:
                browser.close()
    finally:
        report = dict(widths=list(WIDTHS), checks=checks, errors=errors, unexpected_writes=unexpected_writes,
                      writes=writes, invitation_writes=invitation_writes, company_writes=company_writes, dialogs=dialogs)
        (output / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    assert len(checks) == len(WIDTHS), "Not every responsive width completed"
    assert not errors, errors
    assert not unexpected_writes, unexpected_writes
    assert len(writes) == 2 * len(WIDTHS), writes
    assert len(company_writes) == len(WIDTHS), company_writes
    assert len(invitation_writes) == 2 * len(WIDTHS), invitation_writes
    assert not dialogs, dialogs
    print("Collaborator UI passed: presets, manual grants, dependencies, mobile navigation, exclusions, invitation failure/retry, pending counts and own profile at 390/768/1024/1440.")


if __name__ == "__main__":
    main()
