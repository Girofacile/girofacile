"""Collaborator password setup on synthetic APIs, at desktop and mobile widths.

No email, payment or production service is contacted. Playwright intercepts
every request and accepts mutations only in an in-memory invitation fixture.
Run: python tests/check_collaborator_invitation_ui.py
"""
import base64
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (390, 768, 1024, 1440)
ORIGIN = "https://invites.test"
TOKEN = "i" * 64
PASSWORD = "Orbit!River47Cedar#"
NEXT_PASSWORD = "Harbor!Quartz93Waves#"
API_INVALID_MESSAGE = "Invito non valido o scaduto. Richiedi un nuovo invito al titolare."
INVALID_MESSAGE = "Invito non valido, scaduto o già utilizzato. Richiedi un nuovo invito al titolare della tua azienda."
POLICY_MESSAGE = "La password contiene informazioni personali. Scegli una password diversa."
INFO = dict(
    ok=True, email="collaboratore@example.test", full_name="Collaboratore Demo",
    company_name="Logistica Demo <img src=x onerror=alert(1)>",
    password_context=["Collaboratore Demo", "collaboratore@example.test", "Logistica Demo"],
    expires_at="2030-10-11T12:00:00+00:00",
)


def assert_fits(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Page overflow"
    for selector in ("#invitePassword", "#inviteConfirmPassword", "#inviteSubmit", "#inviteRetry", "#inviteLogin"):
        control = page.locator(selector)
        if control.is_visible():
            box = control.bounding_box()
            assert box and box["x"] >= -1 and box["x"] + box["width"] <= page.viewport_size["width"] + 1, selector
            assert box["height"] >= 43, (selector, "Touch target is too small", box["height"])


def wait_intercepted(page, state, key):
    """Wait for Playwright to deliver the held route without a fixed sleep."""
    deadline = time.monotonic() + 5
    while state[key] is None and time.monotonic() < deadline:
        page.wait_for_timeout(10)
    assert state[key] is not None, "Expected intercepted invitation request"
    return state[key]


def main():
    output = ROOT / "test-results" / "collaborator-invitation-ui"
    output.mkdir(parents=True, exist_ok=True)
    errors, dialogs, unexpected_requests, checks = [], [], [], []
    counters = dict(info=0, accept=0)

    def capture(page, scenario, width):
        assert_fits(page)
        page.screenshot(path=str(output / f"{scenario}-{width}.png"), full_page=True, animations="disabled")
        if os.getenv("GF_INVITE_PREVIEW") == "1" and scenario in ("ready", "success") and width in (390, 1440):
            preview = page.screenshot(type="jpeg", quality=70, animations="disabled")
            print(f"GF_INVITE_PREVIEW:{scenario}:{width}:" + base64.b64encode(preview).decode("ascii"), flush=True)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                for width in WIDTHS:
                    def open_fixture(mode="ready", token=True, hold_info=False):
                        context = browser.new_context(viewport=dict(width=width, height=1000), device_scale_factor=1)
                        page = context.new_page()
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
                        state = dict(info=0, accept=0, mode=mode, hold_info=hold_info, pending_info=None,
                                     hold_accept=False, pending_accept=None)
                        page.add_init_script("""
                            window.__inviteRequestChecks = [];
                            const nativeFetch = window.fetch.bind(window);
                            window.fetch = function(input, options = {}) {
                                const address = new URL(typeof input === 'string' ? input : input.url, location.origin);
                                if (address.pathname.startsWith('/api/')) {
                                    window.__inviteRequestChecks.push({
                                        path: address.pathname,
                                        method: options.method || 'GET',
                                        hasFragment: !!location.hash,
                                        sameOrigin: address.origin === location.origin,
                                        hasQuery: !!address.search,
                                        private: options.credentials === 'omit' &&
                                                 options.cache === 'no-store' &&
                                                 options.referrerPolicy === 'no-referrer'
                                    });
                                }
                                return nativeFetch(input, options);
                            };
                        """)

                        def info_response(route):
                            if state["mode"] in ("expired", "used", "revoked", "invalid"):
                                route.fulfill(status=400, json=dict(detail=API_INVALID_MESSAGE))
                            else:
                                route.fulfill(json=INFO)

                        def handle(route):
                            request = route.request
                            parsed = urlparse(request.url)
                            path, method = parsed.path, request.method
                            if parsed.hostname != "invites.test":
                                unexpected_requests.append(dict(width=width, category="external", path=path, method=method))
                                route.abort()
                                return
                            if path in ("/api/collaborator-invitations/info", "/api/collaborator-invitations/accept"):
                                assert method == "POST", "Invitation credentials must use POST"
                                assert not parsed.query and not parsed.fragment, "Credentials leaked into request URL"
                                payload = request.post_data_json
                                assert payload["token"] == TOKEN
                                if path.endswith("/info"):
                                    assert set(payload) == {"token"}
                                    state["info"] += 1
                                    counters["info"] += 1
                                    if state["mode"] == "info-network" and state["info"] == 1:
                                        route.abort("failed")
                                    elif state["hold_info"]:
                                        state["pending_info"] = route
                                    else:
                                        info_response(route)
                                else:
                                    assert set(payload) == {"token", "password", "confirm_password"}
                                    assert payload["password"] == payload["confirm_password"]
                                    assert payload["password"] in (PASSWORD, NEXT_PASSWORD)
                                    state["accept"] += 1
                                    counters["accept"] += 1
                                    if state["mode"] == "accept-network" and state["accept"] == 1:
                                        route.abort("failed")
                                    elif state["mode"] in ("policy", "schema") and state["accept"] == 1:
                                        detail = POLICY_MESSAGE if state["mode"] == "policy" else [dict(
                                            loc=["body", "password"], msg="Password non valida", type="value_error"
                                        )]
                                        route.fulfill(status=422, json=dict(detail=detail))
                                    elif state["mode"] == "accept-expired":
                                        route.fulfill(status=400, json=dict(detail=API_INVALID_MESSAGE))
                                    elif state["hold_accept"]:
                                        state["pending_accept"] = route
                                    else:
                                        route.fulfill(json=dict(ok=True, message="Password impostata. Ora puoi accedere con la tua email.",
                                                               redirect_url="/dashboard"))
                                return
                            if path.startswith("/api/") or method not in ("GET", "HEAD"):
                                unexpected_requests.append(dict(width=width, category="unexpected-api", path=path, method=method))
                                route.fulfill(status=405, json=dict(detail="Unexpected API blocked in UI test"))
                                return
                            if path == "/dashboard":
                                route.fulfill(content_type="text/html", body="<h1>Accesso GiroFacile</h1>")
                                return
                            relative = "static/collaborator/setup.html" if path == "/collaborator/setup" else path.lstrip("/")
                            file = (ROOT / relative).resolve()
                            if file.is_relative_to(ROOT) and file.is_file():
                                route.fulfill(path=str(file))
                            else:
                                unexpected_requests.append(dict(width=width, category="missing-asset", path=path, method=method))
                                route.fulfill(status=404, body="")

                        page.route("**/*", handle)
                        page.goto(ORIGIN + "/collaborator/setup" + ("#token=" + (TOKEN if token is True else token) if token else ""), wait_until="domcontentloaded")
                        assert not urlparse(page.url).fragment, "Invitation token remains in the address bar"
                        return context, page, state, info_response

                    def assert_private(page, expected_info, expected_accept):
                        requests = page.evaluate("window.__inviteRequestChecks")
                        assert sum(r["path"].endswith("/info") for r in requests) == expected_info, requests
                        assert sum(r["path"].endswith("/accept") for r in requests) == expected_accept, requests
                        assert all(r["method"] == "POST" and r["sameOrigin"] and r["private"] and
                                   not r["hasFragment"] and not r["hasQuery"] for r in requests), requests
                        assert page.evaluate("Object.keys(localStorage).length === 0 && Object.keys(sessionStorage).length === 0")
                        assert not page.context.cookies(), "Invitation must not automatically create a login session"
                        assert not urlparse(page.url).fragment

                    def ready(page):
                        page.locator("#inviteForm").wait_for(state="visible")
                        assert page.locator("#inviteEmail").input_value() == INFO["email"]
                        assert page.locator("#inviteEmail").get_attribute("readonly") is not None
                        assert page.locator("#inviteName").inner_text() == INFO["full_name"]
                        assert page.locator("#inviteCompany").inner_text() == INFO["company_name"]
                        assert page.locator("#inviteCompany img").count() == 0, "Company identity was injected as HTML"
                        assert page.locator("#inviteError").is_hidden()
                        assert_fits(page)

                    def fill_password(page, value=PASSWORD):
                        page.locator("#invitePassword").fill(value)
                        page.locator("#inviteConfirmPassword").fill(value)
                        assert page.locator("#inviteSubmit").is_enabled()

                    # Loading, no owner-chosen password, mismatch and explicit login.
                    context, page, state, respond = open_fixture(hold_info=True)
                    try:
                        page.locator("#inviteLoading").wait_for(state="visible")
                        assert page.locator("#inviteForm").is_hidden()
                        wait_intercepted(page, state, "pending_info")
                        state["hold_info"] = False
                        respond(state["pending_info"])
                        ready(page)
                        assert page.locator("#invitePassword").input_value() == ""
                        assert page.locator("#inviteConfirmPassword").input_value() == ""
                        page.locator("#invitePassword").fill("password123")
                        page.locator("#inviteConfirmPassword").fill("password123")
                        assert page.locator("#inviteSubmit").is_disabled()
                        assert state["accept"] == 0
                        fill_password(page)
                        page.locator("#inviteConfirmPassword").fill(NEXT_PASSWORD)
                        assert page.locator("#inviteSubmit").is_disabled()
                        assert state["accept"] == 0, "Mismatch should be caught before any acceptance request"
                        page.locator("#inviteConfirmPassword").fill(PASSWORD)
                        capture(page, "ready", width)
                        state["hold_accept"] = True
                        page.locator("#inviteSubmit").click()
                        page.wait_for_function("window.__inviteRequestChecks.some(r => r.path.endsWith('/accept'))")
                        assert page.locator("#inviteSubmit").is_disabled()
                        # Editing input while the request is in flight must not enable
                        # another submission or create two acceptance requests.
                        page.locator("#invitePassword").fill(NEXT_PASSWORD)
                        page.locator("#inviteConfirmPassword").fill(NEXT_PASSWORD)
                        assert page.locator("#inviteSubmit").is_disabled()
                        page.locator("#inviteSubmit").evaluate("el => el.click()")
                        wait_intercepted(page, state, "pending_accept")
                        assert state["accept"] == 1
                        state["pending_accept"].fulfill(json=dict(
                            ok=True, message="Password impostata. Ora puoi accedere con la tua email.",
                            redirect_url="/dashboard",
                        ))
                        page.locator("#inviteSuccess").wait_for(state="visible")
                        assert page.locator("#inviteForm").is_hidden()
                        assert state["info"] == 1 and state["accept"] == 1
                        assert page.locator("#invitePassword").input_value() == ""
                        assert page.locator("#inviteConfirmPassword").input_value() == ""
                        assert page.locator("#inviteLogin").get_attribute("href") == "/dashboard"
                        assert page.url == ORIGIN + "/collaborator/setup", "Password setup must not automatically log in"
                        assert_private(page, 1, 1)
                        capture(page, "success", width)
                        page.locator("#inviteLogin").click()
                        page.wait_for_url(ORIGIN + "/dashboard")
                        assert page.get_by_role("heading", name="Accesso GiroFacile").is_visible()
                        checks.append(dict(width=width, scenario="ready-mismatch-success-explicit-login"))
                    finally:
                        context.close()

                    # Missing, expired, consumed and revoked invitations remain unusable.
                    for mode in ("missing", "malformed-short", "malformed-long", "malformed-chars",
                                 "invalid", "expired", "used", "revoked"):
                        token_for_mode = {
                            "missing": False, "malformed-short": "i" * 31,
                            "malformed-long": "i" * 129, "malformed-chars": "i" * 63 + "!",
                        }.get(mode, True)
                        expected_info = int(mode in ("invalid", "expired", "used", "revoked"))
                        context, page, state, _ = open_fixture(mode=mode, token=token_for_mode)
                        try:
                            page.locator("#inviteError").wait_for(state="visible")
                            assert page.locator("#inviteForm").is_hidden()
                            assert page.locator("#inviteSuccess").is_hidden()
                            assert state["accept"] == 0
                            assert INVALID_MESSAGE in page.locator("#inviteError").inner_text()
                            assert_private(page, expected_info, 0)
                            capture(page, mode, width)
                            checks.append(dict(width=width, scenario=mode))
                        finally:
                            context.close()

                    # Network failures support retry without leaking or replacing the token.
                    context, page, state, _ = open_fixture(mode="info-network")
                    try:
                        page.locator("#inviteError").wait_for(state="visible")
                        page.locator("#inviteRetry").wait_for(state="visible")
                        assert page.locator("#inviteForm").is_hidden()
                        assert_private(page, 1, 0)
                        capture(page, "info-network", width)
                        page.locator("#inviteRetry").click()
                        ready(page)
                        assert state["info"] == 2 and state["accept"] == 0
                        assert_private(page, 2, 0)
                        checks.append(dict(width=width, scenario="info-network-retry"))
                    finally:
                        context.close()

                    # Policy/schema errors and transient acceptance errors keep input editable.
                    for mode in ("policy", "schema", "accept-network"):
                        context, page, state, _ = open_fixture(mode=mode)
                        try:
                            ready(page)
                            fill_password(page)
                            page.locator("#inviteSubmit").click()
                            page.locator("#inviteFormError").wait_for(state="visible")
                            assert page.locator("#invitePassword").input_value() == PASSWORD
                            assert page.locator("#inviteConfirmPassword").input_value() == PASSWORD
                            assert page.locator("#inviteForm").is_visible()
                            assert page.locator("#inviteSubmit").is_enabled()
                            if mode == "policy":
                                assert POLICY_MESSAGE in page.locator("#inviteFormError").inner_text()
                            assert_private(page, 1, 1)
                            capture(page, mode, width)
                            fill_password(page, NEXT_PASSWORD)
                            page.locator("#inviteSubmit").click()
                            page.locator("#inviteSuccess").wait_for(state="visible")
                            assert_private(page, 1, 2)
                            assert state["accept"] == 2
                            checks.append(dict(width=width, scenario=mode))
                        finally:
                            context.close()
                    # A token may expire or be revoked while the password form is open.
                    context, page, state, _ = open_fixture(mode="accept-expired")
                    try:
                        ready(page)
                        fill_password(page)
                        page.locator("#inviteSubmit").click()
                        page.locator("#inviteError").wait_for(state="visible")
                        assert INVALID_MESSAGE in page.locator("#inviteError").inner_text()
                        assert page.locator("#inviteForm").is_hidden()
                        assert page.locator("#inviteSuccess").is_hidden()
                        assert page.locator("#inviteRetry").is_hidden()
                        assert page.locator("#invitePassword").input_value() == ""
                        assert page.locator("#inviteConfirmPassword").input_value() == ""
                        assert_private(page, 1, 1)
                        capture(page, "accept-expired", width)
                        checks.append(dict(width=width, scenario="accept-expired"))
                    finally:
                        context.close()
            finally:
                browser.close()

    finally:
        report = dict(widths=list(WIDTHS), checks=checks, counters=counters, errors=errors,
                      unexpected_requests=unexpected_requests, dialogs=dialogs)
        # The report intentionally contains neither invitation tokens nor passwords.
        serialized = json.dumps(report, indent=2)
        assert TOKEN not in serialized and PASSWORD not in serialized and NEXT_PASSWORD not in serialized
        (output / "audit.json").write_text(serialized, encoding="utf-8")
        print(serialized)
    assert len(checks) == 14 * len(WIDTHS), "Not every responsive scenario completed"
    assert not errors, errors
    assert not unexpected_requests, unexpected_requests
    assert not dialogs, dialogs
    print("Collaborator invitation UI passed: own password, private one-use link, negative tokens, validation, retry and explicit login at 390/768/1024/1440.")


if __name__ == "__main__":
    main()
