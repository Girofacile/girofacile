"""Controllo indirizzi dei clienti selezionati (variante A): tabella a confronto, Conferma, Modifica con mappa.

Usa il pop-up vero (HTML di index.html) e il suo script, con il server simulato: nessun dato reale.
"""
import json
import mimetypes
import pathlib
import re

from playwright.sync_api import sync_playwright, expect

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "http://girofacile.test"
OUTPUT = ROOT / "test-results" / "customer-addresses"
ISSUES = [
    {"id": 1, "recipient_name": "Eurospin – Atripalda", "address": "Contrada Novesoldi", "comune": "Atripalda", "provincia": "AV",
     "message": "Google ha trovato una posizione da confermare sulla mappa.", "kind": "address",
     "candidate": {"lat": 40.9196, "lon": 14.8277, "formatted": "Contrada Novesoldi, 83042 Atripalda AV"}},
    {"id": 2, "recipient_name": "Eurospin – Mercogliano", "address": "Via Nicola Santangelo", "comune": "Mercogliano", "provincia": "AV",
     "message": "Google ha trovato una posizione da confermare sulla mappa.", "kind": "address",
     "candidate": {"lat": 40.9213, "lon": 14.7432, "formatted": "Via Nicola Santangelo, 83013 Mercogliano AV"}},
    {"id": 3, "recipient_name": "Famila Superstore – Caserta", "address": "Viale Carlo III", "comune": "Caserta", "provincia": "CE",
     "message": "Indirizzo non trovato. Correggilo o scegli la posizione sulla mappa.", "kind": "address", "candidate": None},
]


def page_html():
    index = (ROOT / "static/dashboard/index.html").read_text(encoding="utf-8")
    dialog = re.search(r'<dialog id="selectedCustomerAddressesDialog".*?</dialog>', index, re.S).group(0)
    css = "".join(f'<link rel="stylesheet" href="/static/design-system/{n}.css">' for n in ("theme", "components", "layout"))
    return f"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{css}
<script>
window.customerDirectory={{selected:new Set([1,2,3,4])}};
window.cxEsc=v=>String(v??'').replace(/[&<>"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
window.gfCount=(n,one,many)=>n+' '+(n===1?one:many);
window.calls=[];window.planning=0;
window.api=async(path,options)=>{{const body=JSON.parse(options.body);calls.push([path,body]);
  if(path.endsWith('verify-selected'))return {{issues:{json.dumps(ISSUES)}.filter(r=>body.customer_ids.includes(r.id)),aborted:false}};
  return {{customer:{{}}}};}};
window.refreshCustomerDirectory=async()=>{{}};window.renderCustomerDirectory=()=>{{}};window.goCustomerPlanning=()=>{{planning++;}};
window.loadRoadMapLibrary=async()=>{{window.L={{map:()=>({{setView(){{return this;}},on(){{}},remove(){{}},invalidateSize(){{}}}}),
  tileLayer:()=>({{addTo(){{}}}}),marker:()=>({{addTo(){{return this;}},on(){{}},setLatLng(){{}},remove(){{}}}})}};}};
</script></head><body data-gf-surface="workspace">{dialog}
<script src="/static/dashboard/js/selected-customer-addresses.js"></script></body></html>"""


def serve(route):
    path = route.request.url.removeprefix(BASE).split("?")[0]
    if path in ("", "/"):
        return route.fulfill(status=200, content_type="text/html", body=page_html())
    file = ROOT / path.lstrip("/")
    if file.is_file():
        return route.fulfill(status=200, body=file.read_bytes(), content_type=mimetypes.guess_type(file.name)[0] or "text/plain")
    return route.fulfill(status=404, body="")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (390, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900})
            context.route("**/*", serve)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE + "/")
            assert page.evaluate("GFCustomerAddresses.verify()") is False
            dialog = page.locator("#selectedCustomerAddressesDialog")
            expect(dialog).to_be_visible()
            rows = dialog.locator("[data-customer-address-row]")
            expect(rows).to_have_count(3)
            expect(dialog).to_contain_text("Contrada Novesoldi, 83042 Atripalda AV")
            # Senza proposta di Google non c'è «Conferma», solo Modifica ed Escludi.
            expect(rows.nth(2).get_by_role("button", name="Conferma")).to_have_count(0)
            expect(dialog.get_by_role("button", name="Conferma tutte le proposte")).to_be_visible()
            expect(dialog.get_by_role("button", name="Vai alla pianificazione")).to_be_disabled()
            assert page.evaluate("document.querySelector('#selectedCustomerAddressesDialog .gf-modal__body').scrollHeight <= document.querySelector('#selectedCustomerAddressesDialog .gf-modal__body').clientHeight + 2") or width < 500
            page.screenshot(path=str(OUTPUT / f"elenco-{width}.png"))
            # Conferma rapida della prima riga.
            rows.nth(0).get_by_role("button", name="Conferma").click()
            expect(rows).to_have_count(2)
            assert page.evaluate("calls.at(-1)[1].action") == "accept"
            # Modifica: la tabella lascia il posto alla mappa, «Torna all'elenco» la riporta.
            rows.nth(1).get_by_role("button", name="Modifica").click()
            expect(page.locator("#selectedCustomerAddressesList")).to_be_hidden()
            expect(page.locator("#selectedCustomerAddressMap")).to_be_visible()
            expect(page.locator("#selectedCustomerAddressCity")).to_have_value("Caserta")
            page.screenshot(path=str(OUTPUT / f"modifica-{width}.png"))
            dialog.get_by_role("button", name="← Torna all'elenco").click()
            expect(page.locator("#selectedCustomerAddressesList")).to_be_visible()
            # Conferma tutte (resta solo quella con proposta) ed Escludi l'ultima: si può pianificare.
            dialog.get_by_role("button", name="Escludi").last.click()
            expect(rows).to_have_count(1)
            rows.nth(0).get_by_role("button", name="Conferma").click()
            expect(dialog).to_contain_text("Tutti gli indirizzi sono a posto")
            dialog.get_by_role("button", name="Vai alla pianificazione").click()
            assert page.evaluate("planning") == 1
            assert not errors, errors
            context.close()
        browser.close()
    print("PASS: controllo indirizzi clienti a 390/1440 — tabella a confronto, Conferma, Modifica con mappa, Escludi, pianificazione")


if __name__ == "__main__":
    main()
