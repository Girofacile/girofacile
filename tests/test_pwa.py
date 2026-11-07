"""App autista e portale mobile installabili: manifest, service worker e collegamenti nelle pagine."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_manifests_describe_two_installable_apps():
    driver = json.loads(Path("static/driver.webmanifest").read_text(encoding="utf-8"))
    portal = json.loads(Path("static/portal.webmanifest").read_text(encoding="utf-8"))
    # Ambito su tutto il sito: il login comune resta dentro l'app installata, senza barra del browser.
    assert (driver["name"], driver["start_url"], driver["scope"]) == ("GiroFacile Autista", "/driver", "/")
    assert (portal["start_url"], portal["display"]) == ("/mobile", "standalone")
    for manifest in (driver, portal):
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        assert {"192x192", "512x512"} <= sizes and manifest["display"] == "standalone"
        for icon in manifest["icons"]:
            assert Path(icon["src"].lstrip("/")).exists(), icon["src"]


def test_pages_link_manifest_and_register_the_service_worker():
    for page, manifest in (("static/driver/index.html", "driver"), ("static/driver/setup.html", "driver"),
                           ("static/mobile/index.html", "portal")):
        html = Path(page).read_text(encoding="utf-8")
        assert f'<link rel="manifest" href="/static/{manifest}.webmanifest">' in html, page
        assert '<script src="/static/pwa.js" defer></script>' in html, page
    worker = Path("static/sw.js").read_text(encoding="utf-8")
    # Solo l'apertura delle pagine passa dal service worker; nessuna API in cache.
    assert "event.request.mode !== 'navigate'" in worker and "/api/" not in worker


def test_service_worker_is_served_from_the_site_root():
    env = dict(os.environ, DATABASE_URL="sqlite+pysqlite:///:memory:", ALLOW_SQLITE_LEGACY="true", APP_ENV="development")
    code = ("from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app); "
            "r=c.get('/sw.js'); assert r.status_code==200 and 'javascript' in r.headers['content-type'], r.text; "
            "assert r.headers['service-worker-allowed']=='/' and r.headers['cache-control']=='no-cache'; "
            "m=c.get('/static/driver.webmanifest'); assert m.headers['content-type'].startswith('application/manifest+json'), m.headers")
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_install_guide_opens_once_after_login_in_both_apps():
    guide = Path("static/install-guide.js").read_text(encoding="utf-8")
    assert "Aggiungi GiroFacile alla tua Home" in guide and "Metti GiroFacile sulla Home" not in guide
    # iPhone: tre passaggi; Android: pulsante del browser; mai se già installata o rimandata.
    for text in ("Tocca Condividi", "Aggiungi alla schermata Home", "beforeinstallprompt", "display-mode: standalone", "Più tardi"):
        assert text in guide, text
    for page in ("static/driver/index.html", "static/mobile/index.html"):
        assert '<script src="/static/install-guide.js" defer></script>' in Path(page).read_text(encoding="utf-8"), page
    assert "GFInstallGuide?.maybeShow('GiroFacile Autista')" in Path("static/driver/index.html").read_text(encoding="utf-8")
    assert "GFInstallGuide?.maybeShow('GiroFacile')" in Path("static/mobile/mobile.js").read_text(encoding="utf-8")
