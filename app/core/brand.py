"""Colore del brand dell'azienda, usato nella pagina di tracking dei clienti."""
import re

DEFAULT_BRAND_COLOR = "#1F5BFF"
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _luminance(color):
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def normalize_brand_color(value):
    """#RRGGBB in maiuscolo, oppure None se vuoto. ValueError se non valido o troppo chiaro.

    Il colore fa da sfondo a pulsanti con testo bianco: serve un contrasto di almeno 3:1.
    """
    value = (value or "").strip()
    if not value:
        return None
    if not _HEX.match(value):
        raise ValueError("Colore non valido: usa il formato #RRGGBB.")
    if 1.05 / (_luminance(value) + 0.05) < 3:
        raise ValueError("Colore troppo chiaro: il testo bianco dei pulsanti non si leggerebbe. Scegli una tonalità più scura.")
    return value.upper()
