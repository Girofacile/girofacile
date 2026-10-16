"""Exercise static planning proposals without importing the app or accessing a DB.

Run: python tests/check_planning_previews.py
Requires Playwright 1.55 and Chromium. Uses fictional data and a local-only server.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import Thread
from time import perf_counter
from urllib.parse import unquote, urlsplit, urlunsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("a", "b", "c")
PAGES = {f"/anteprime/pianificazione-{variant}.html" for variant in VARIANTS}
PREVIEW_ASSETS = {"/anteprime/pianificazione-demo.js"}
VIEWPORTS = ((390, 844), (768, 1024), (1024, 900), (1440, 1000))
FIELDS = ("#trip-date", "#trip-time", "#trip-vehicle", "#trip-driver", "#trip-mode")


def allowed_path(path):
    return path in PAGES or path in PREVIEW_ASSETS or path.startswith("/static/design-system/")


class PreviewHandler(SimpleHTTPRequestHandler):
    """Serve only preview documents and the shared design-system files."""
    def do_GET(self):
        if not allowed_path(unquote(urlsplit(self.path).path)):
            self.send_error(404)
            return
        super().do_GET()

    def log_message(self, _format, *args):
        pass


@contextmanager
def preview_server():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(PreviewHandler, directory=str(ROOT))
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def safe_url(value):
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def visible_locator(page, selector):
    for locator in page.locator(selector).all():
        if locator.is_visible():
            return locator
    raise AssertionError(f"No visible element matches {selector!r}")


def action(page, name):
    visible_locator(page, f'[data-action="{name}"]').click()


def select_tab(page, variant, target):
    if variant == "c":
        tab = page.locator(f'[role="tab"][data-target="{target}"]')
        expect(tab).to_be_visible()
        tab.click()
        expect(tab).to_have_attribute("aria-selected", "true")


def organize(page, variant):
    if variant == "a":
        panel = page.locator('[data-step-panel="organize"]')
        if not panel.is_visible():
            action(page, "continue")
        expect(panel).to_be_visible()
    elif variant == "c":
        select_tab(page, variant, "config")


def field_snapshot(page):
    return {selector: page.locator(selector).input_value() for selector in FIELDS}


def assert_fields_preserved(page, expected):
    for selector, value in expected.items():
        expect(page.locator(selector)).to_have_value(value)


def quantity_field(page, variant):
    select_tab(page, variant, "stops")
    return visible_locator(page, '[data-quantity="kg"][data-stop-id="1"]')


def assert_stop_count(page, expected):
    counters = [
        item for item in page.locator('[data-total="stops"]').all()
        if item.is_visible()
    ]
    assert counters, "Missing selected-stop counter"
    for counter in counters:
        expect(counter).to_have_text(str(expected))


def assert_no_usable_old_result(page):
    expect(page.locator("#review-panel")).to_be_hidden()
    expect(page.locator("#success-panel")).to_be_hidden()
    for button in page.locator('[data-action="program"]').all():
        assert not button.is_visible() or not button.is_enabled(), (
            "A stale result can still be programmed"
        )


def assert_no_horizontal_overflow(page):
    dimensions = page.evaluate("""() => ({
        viewport: document.documentElement.clientWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
    })""")
    assert dimensions["document"] <= dimensions["viewport"] + 1, dimensions
    assert dimensions["body"] <= dimensions["viewport"] + 1, dimensions


def screenshot(page, output, prefix, stage):
    path = output / f"{prefix}-{stage}.png"
    page.screenshot(path=str(path), full_page=True, animations="disabled")
    return path.name


def run_case(browser, origin, variant, width, height, output):
    started = perf_counter()
    prefix = f"pianificazione-{variant}-{width}"
    result = {
        "variant": variant, "viewport": {"width": width, "height": height},
        "status": "failed", "console_errors": [], "page_errors": [],
        "unexpected_requests": [], "external_stylesheets_stubbed": 0,
        "screenshots": [],
    }
    context = browser.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=1,
        is_mobile=width == 390, has_touch=width <= 768,
        service_workers="block", accept_downloads=False,
    )
    context.set_default_timeout(5000)
    port = urlsplit(origin).port

    def intercept(route):
        request = route.request
        parts = urlsplit(request.url)
        local = parts.scheme == "http" and parts.hostname == "127.0.0.1" and parts.port == port
        if local and allowed_path(parts.path) and request.method == "GET":
            route.continue_()
            return
        if parts.hostname == "fonts.googleapis.com" and request.resource_type == "stylesheet":
            result["external_stylesheets_stubbed"] += 1
            route.fulfill(status=200, content_type="text/css", body="/* Fonts stubbed for isolated tests. */")
            return
        result["unexpected_requests"].append({
            "method": request.method, "type": request.resource_type,
            "url": safe_url(request.url),
        })
        route.abort("blockedbyclient")

    context.route("**/*", intercept)

    def block_socket(socket):
        result["unexpected_requests"].append({"type": "websocket", "url": safe_url(socket.url)})
        socket.close(code=1008, reason="Static previews forbid API traffic")

    context.route_web_socket("**/*", block_socket)
    page = context.new_page()
    page.set_default_navigation_timeout(15000)
    page.on("console", lambda msg: result["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))

    try:
        response = page.goto(f"{origin}/anteprime/pianificazione-{variant}.html", wait_until="networkidle")
        assert response and response.status == 200
        expect(page.locator("body")).to_have_attribute("data-preview-layout", variant)
        assert page.locator("[style], style").count() == 0, "Prototypes must reuse shared CSS"
        ids = page.locator("[id]").evaluate_all("nodes => nodes.map(node => node.id)")
        assert len(ids) == len(set(ids)), "Duplicate HTML IDs"
        message = page.locator("#preview-message")
        assert message.count() == 1
        expect(message).to_have_attribute("role", "status")
        assert_no_usable_old_result(page)
        organize(page, variant)
        if variant == "c":
            page.locator("#tab-config").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#tab-stops")).to_have_attribute("aria-selected", "true")
            page.keyboard.press("ArrowLeft")
            expect(page.locator("#tab-config")).to_have_attribute("aria-selected", "true")
        assert_stop_count(page, 6)
        assert_no_horizontal_overflow(page)
        result["screenshots"].append(screenshot(page, output, prefix, "initial"))

        page.locator("#trip-date").fill("2026-10-20")
        page.locator("#trip-time").fill("08:15")
        page.locator("#trip-mode").select_option("single")
        page.locator("#trip-vehicle").select_option("van03")
        page.locator("#trip-driver").select_option("sara")
        configured = field_snapshot(page)
        advanced = page.locator("#advanced-options")
        expect(advanced).to_be_visible()
        assert advanced.evaluate("node => node.tagName") == "DETAILS"
        advanced.locator("summary").click()
        assert advanced.evaluate("node => node.open")
        advanced.locator("summary").click()
        assert not advanced.evaluate("node => node.open")

        weight = quantity_field(page, variant)
        weight.fill("37")
        weight.press("Tab")
        action(page, "edit-selection")
        choice = page.locator('[data-stop-choice="6"]')
        expect(choice).to_be_visible()
        expect(choice).to_be_checked()
        action(page, "continue")
        organize(page, variant)
        assert_fields_preserved(page, configured)
        expect(quantity_field(page, variant)).to_have_value("37")

        organize(page, variant)
        action(page, "calculate")
        expect(page.locator("#review-panel")).to_be_visible()
        expect(page.locator("#success-panel")).to_be_hidden()
        expect(visible_locator(page, '[data-action="program"]')).to_be_enabled()
        assert_stop_count(page, 6)
        assert_no_horizontal_overflow(page)
        result["screenshots"].append(screenshot(page, output, prefix, "review"))

        action(page, "edit-selection")
        expect(choice).to_be_visible()
        choice.uncheck()
        assert_stop_count(page, 5)
        action(page, "continue")
        organize(page, variant)
        assert_no_usable_old_result(page)
        assert_fields_preserved(page, configured)
        expect(quantity_field(page, variant)).to_have_value("37")
        organize(page, variant)
        action(page, "calculate")
        expect(page.locator("#review-panel")).to_be_visible()
        assert_stop_count(page, 5)
        action(page, "program")
        expect(page.locator("#success-panel")).to_be_visible()
        expect(message).not_to_be_empty()
        assert_no_horizontal_overflow(page)
        result["screenshots"].append(screenshot(page, output, prefix, "programmed"))

        # Invalid prices cannot produce negative costs, even in demonstration.
        action(page, "edit-config")
        advanced.locator("summary").click()
        page.locator("#trip-energy-mode").select_option("custom")
        page.locator("#trip-energy-price").fill("-1")
        action(page, "calculate")
        assert_no_usable_old_result(page)
        expect(message).to_contain_text("prezzo")
        page.locator("#trip-energy-price").fill("1.75")
        advanced.locator("summary").click()

        # Negative inputs cannot produce a usable result.
        action(page, "edit-config")
        bad_weight = quantity_field(page, variant)
        bad_weight.fill("-1")
        organize(page, variant)
        action(page, "calculate")
        assert_no_usable_old_result(page)
        expect(message).to_contain_text("colli e peso")
        quantity_field(page, variant).fill("37")
        organize(page, variant)
        page.locator("#trip-mode").select_option("fleet")
        expect(page.locator("#fleet-fields")).to_be_visible()
        action(page, "calculate")
        expect(page.locator("#review-panel")).to_be_visible()
        expect(page.locator("[data-review-resources]")).to_contain_text("Van 04")

        # Client-based selection is also available, without clearing field edits.
        action(page, "edit-selection")
        page.locator("#trip-source").select_option("customers")
        action(page, "continue")
        organize(page, variant)
        expect(quantity_field(page, variant)).to_have_value("37")
        assert_no_usable_old_result(page)

        if width <= 768:
            toggle = page.locator(".gf-header__menu")
            if toggle.count():
                toggle.click()
                expect(toggle).to_have_attribute("aria-expanded", "true")
                page.keyboard.press("Escape")
                expect(toggle).to_have_attribute("aria-expanded", "false")

        assert not result["unexpected_requests"], result["unexpected_requests"]
        assert not result["page_errors"], result["page_errors"]
        assert not result["console_errors"], result["console_errors"]
        result["status"] = "passed"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        try:
            result["screenshots"].append(screenshot(page, output, prefix, "failure"))
        except Exception:
            pass
    finally:
        context.close()
        result["seconds"] = round(perf_counter() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "test-results" / "planning-previews")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for path in PAGES | PREVIEW_ASSETS:
        assert (ROOT / path.lstrip("/")).is_file(), path
    cases = []
    with preview_server() as origin, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for variant in VARIANTS:
                for width, height in VIEWPORTS:
                    case = run_case(browser, origin, variant, width, height, output)
                    cases.append(case)
                    print(f"{case['status'].upper():6} pianificazione-{variant} {width}px ({case['seconds']}s)", flush=True)
                    if case["status"] != "passed":
                        print("       " + case.get("error", "Unknown error"), flush=True)
        finally:
            browser.close()
    failures = [case for case in cases if case["status"] != "passed"]
    report = {"passed": len(cases) - len(failures), "failed": len(failures), "cases": cases}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{report['passed']}/{len(cases)} scenarios passed; report: {report_path}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
