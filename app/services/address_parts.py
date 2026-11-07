"""Indirizzo a campi separati: via, civico, CAP, comune (e provincia facoltativa).

L'indirizzo su una riga che arriva a Google si compone sempre allo stesso modo
(«Via Roma 10, 80026 Casoria NA»), così la verifica severa ritrova esattamente i campi scritti.
"""
from __future__ import annotations

import re

CAP_RE = re.compile(r"^\d{5}$")


def clean(value) -> str:
    return " ".join(str(value or "").split()).strip()


def street_line(street, number) -> str:
    """«Via Roma» + «10» → «Via Roma 10» (senza civico resta la via)."""
    return clean(f"{clean(street)} {clean(number)}")


def compose(street, number, cap, city, province=None) -> str:
    place = clean(" ".join(x for x in (clean(cap), clean(city), clean(province).upper()) if x))
    return ", ".join(x for x in (street_line(street, number), place) if x)


def split_street(line) -> tuple[str, str]:
    """«Via Roma 10» → («Via Roma», «10»); il civico è l'ultimo numero (anche 12/B, 7A)."""
    text = clean(line)
    match = re.match(r"^(.*?\D)[\s,]+(\d+\s*[a-zA-Z]?(?:\s*/\s*\w+)?)$", text)
    return (match.group(1).strip(" ,"), match.group(2)) if match else (text, "")


def split(text) -> dict:
    """Campi da un indirizzo su una riga (ordini già salvati, import con una colonna sola)."""
    from .geocoding import parse_address
    parsed = parse_address(text)
    province = ""
    tail = clean(str(text or "").split(",")[-1]) if text else ""
    found = re.search(r"\b([A-Z]{2})$", tail)
    if found and found.group(1) not in ("IT",):
        province = found.group(1)
    return {"street": parsed["street"], "street_number": parsed["number"] or "",
            "postal_code": parsed["cap"] or "", "city": parsed["town"], "province": province}
