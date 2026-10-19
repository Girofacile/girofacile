"""Finder launcher: keep the local server in the user's Terminal session."""
import json
import threading
from urllib.request import urlopen
import webbrowser

from server import Handler, ThreadingHTTPServer, brand_profile

URL = "http://127.0.0.1:8765"


def main():
    brand_profile()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    except OSError as exc:
        # A second double-click should reuse a running Studio, never kill it.
        try:
            with urlopen(URL + "/api/brand", timeout=3) as response:
                profile = json.load(response)
            if profile.get("name") != "GiroFacile" or "funnels" not in profile or "token" not in profile:
                raise ValueError("Il servizio sulla porta 8765 non è Carousel Studio.")
        except Exception:
            raise RuntimeError("Impossibile avviare Carousel Studio sulla porta 8765. La porta potrebbe essere occupata da un altro programma.") from exc
        print("Carousel Studio è già attivo. Apro il browser.", flush=True)
        webbrowser.open(URL)
        return

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    print(f"GiroFacile Carousel Studio è attivo: {URL}", flush=True)
    print("Lascia aperta questa finestra di Terminale mentre usi il generatore.", flush=True)
    print("Per fermarlo premi Ctrl+C. Per riaprirlo fai doppio clic su Apri Carousel Studio.command.", flush=True)
    try:
        if not webbrowser.open(URL):
            print(f"Apri manualmente {URL} nel browser.", flush=True)
        worker.join()
    except KeyboardInterrupt:
        print("\nChiusura di Carousel Studio.", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


if __name__ == "__main__":
    main()
