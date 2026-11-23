"""Consenso cookie e pixel di Meta: il pixel parte solo dopo «Accetta».

Pagine servite dai file del progetto (nessun server): la landing mostra il banner, «Rifiuta» non
carica nulla da Meta, «Accetta» carica il pixel e registra la visita; l'area riservata non mostra
il banner e invia solo l'evento di registrazione a chi ha accettato.
"""
import mimetypes
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "http://girofacile.test"
OUTPUT = ROOT / "test-results" / "cookie-consent"


def serve(route):
    url = route.request.url
    if "facebook" in url:
        return route.fulfill(status=200, content_type="application/javascript", body="")
    path = url.removeprefix(BASE).split("?")[0].split("#")[0]
    if path in ("", "/"):
        path = "/static/landing/index.html"
    file = ROOT / path.lstrip("/")
    if file.is_file():
        return route.fulfill(status=200, body=file.read_bytes(), content_type=mimetypes.guess_type(file.name)[0] or "application/octet-stream")
    return route.fulfill(status=200, content_type="application/javascript", body="window.GF_PLANS={};") if path.startswith("/api/") else route.fulfill(status=404, body="")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (390, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900})
            context.route("**/*", serve)
            meta = []
            context.on("request", lambda r: meta.append(r.url) if "facebook" in r.url else None)
            page = context.new_page()
            page.goto(BASE + "/")
            banner = page.locator("#gfConsentBanner")
            banner.wait_for(state="visible")
            assert not meta and page.evaluate("typeof window.fbq") == "undefined", "pixel prima del consenso"
            page.screenshot(path=str(OUTPUT / f"banner-{width}.png"))
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
            # Rifiuta: niente pixel, nemmeno ricaricando.
            banner.get_by_role("button", name="Rifiuta").click()
            assert not banner.count()
            page.reload()
            page.wait_for_timeout(300)
            assert not page.locator("#gfConsentBanner").count() and not meta
            # Preferenze cookie dal piè di pagina, poi Accetta: pixel caricato e visita registrata.
            page.get_by_role("button", name="Preferenze cookie").click()
            page.locator("#gfConsentBanner").get_by_role("button", name="Accetta").click()
            page.wait_for_timeout(300)
            assert any("fbevents.js" in url for url in meta)
            assert page.evaluate("typeof window.fbq") == "function"
            # Area riservata: nessun banner né visita; l'evento di registrazione parte (consenso già dato).
            meta.clear()
            page.goto(BASE + "/static/dashboard/index.html")
            page.wait_for_timeout(500)
            assert not page.locator("#gfConsentBanner").count()
            assert not meta, meta
            assert page.evaluate("GFMarketing.track('CompleteRegistration')") is True
            assert any("fbevents.js" in url for url in meta)
            context.close()
        browser.close()
    print("PASS: consenso cookie a 390/1440 — banner, Rifiuta senza pixel, Accetta con pixel, area riservata senza banner")


if __name__ == "__main__":
    main()
