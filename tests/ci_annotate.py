"""Scrive le ultime righe di un registro come avviso di errore di GitHub Actions.

Gli avvisi compaiono nella pagina del controllo e sono leggibili tramite l'API pubblica,
anche senza scaricare i registri completi. Uso: python tests/ci_annotate.py "<titolo>" <file>
"""
import sys
from pathlib import Path

MAX_LINES = 60
MAX_CHARS = 6000


def escape(text: str) -> str:
    # Formato dei comandi di GitHub Actions: % e a capo vanno codificati.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotation(title: str, log_text: str) -> str:
    tail = "\n".join(log_text.splitlines()[-MAX_LINES:])[-MAX_CHARS:]
    safe_title = title.replace("%", "%25").replace("\n", " ").replace("::", ": ").replace(",", ";")
    return f"::error title={safe_title}::{escape(tail or '(nessuna uscita)')}"


def main(argv):
    title, path = argv[1], Path(argv[2])
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    print(annotation(title, text))


if __name__ == "__main__":
    main(sys.argv)
