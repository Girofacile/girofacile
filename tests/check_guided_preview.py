"""Browser checks for the standalone guided prototype. No app or database needed."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-executable', help='Optional installed Chromium/Chrome executable')
    args = parser.parse_args()
    output = ROOT / 'test-results' / 'guided-preview'
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**({'executable_path': args.browser_executable} if args.browser_executable else {}))
        try:
            for width, height in ((390, 844), (768, 1024), (1440, 1000), (1920, 1080)):
                context = browser.new_context(viewport={'width': width, 'height': height}, offline=True)
                page = context.new_page()
                errors, requests = [], []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: requests.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
                page.goto((ROOT / 'anteprime/html-autonomi/pianificazione-guidata.html').as_uri())
                expect(page.locator('[data-gf-shell]')).to_have_count(1)

                def shot(name):
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}px, {name}'
                    page.screenshot(path=str(output / f'{width}-{name}.png'), full_page=True)

                shot('consegne')
                expect(page.locator('[data-step="2"]')).to_be_disabled()
                page.locator('#search').fill('centrale')
                expect(page.locator('.stop-row:visible')).to_have_count(1)
                page.locator('#search').fill('nessun-risultato')
                expect(page.locator('#empty-search')).to_be_visible()
                page.locator('#search').fill('')
                page.locator('#select-all').uncheck()
                expect(page.locator('#next')).to_be_disabled()
                page.locator('#select-all').check()
                page.locator('[data-detail="1"]').click()
                packages = page.locator('[data-edit="packages"][data-id="1"]')
                packages.fill('-1')
                page.locator('#next').click()
                expect(page.locator('[data-panel="0"]')).to_be_visible()
                packages.fill('10')
                expect(page.locator('[data-packages]').first).to_have_text('34')
                page.locator('#next').click()
                shot('organizza')
                page.locator('#date').fill('')
                page.locator('#next').click()
                expect(page.locator('[data-panel="1"]')).to_be_visible()
                page.locator('#date').fill('2026-10-20')
                page.locator('input[value="fleet"]').check()
                expect(page.locator('#fleet-fields')).to_be_visible()
                shot('flotta')
                page.locator('input[value="single"]').check()
                page.locator('#back').click()
                expect(packages).to_have_value('10')
                packages.fill('-1')
                page.locator('[data-step="1"]').click()
                expect(page.locator('[data-panel="0"]')).to_be_visible()
                packages.fill('10')
                weight = page.locator('[data-edit="weight"][data-id="1"]')
                weight.fill('2000')
                page.locator('#next').click()
                page.locator('#next').click()
                expect(page.locator('#message')).to_contain_text('supera la portata')
                page.locator('#back').click()
                weight.fill('180')
                page.locator('#next').click()
                page.locator('#next').click()
                expect(page.locator('[data-panel="2"]')).to_be_visible()
                expect(page.locator('#review-date')).to_contain_text('20 ottobre 2026')
                expect(page.locator('#next')).to_be_disabled()
                shot('verifica')
                page.locator('#confirm-review').check()
                page.locator('#next').click()
                expect(page.locator('[data-panel="3"]')).to_be_visible()
                expect(page.locator('#finish-date')).to_contain_text('20 ottobre 2026')
                shot('pianificato')
                page.locator('#edit-again').click()
                expect(page.locator('[data-panel="1"]')).to_be_visible()
                expect(page.locator('[data-step="2"]')).to_be_disabled()
                expect(page.locator('[data-step="3"]')).to_be_disabled()
                page.locator('#next').click()
                expect(page.locator('#confirm-review')).not_to_be_checked()
                assert not errors, errors
                assert not requests, requests
                cases.append({'width': width, 'status': 'passed', 'page_errors': errors, 'network_requests': requests})
                print(f'PASS {width}px: full journey, validation, backtracking, no network', flush=True)
                context.close()
        finally:
            browser.close()
    (output / 'report.json').write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
