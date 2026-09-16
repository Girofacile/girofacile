from __future__ import annotations

import html as html_lib
import re
from datetime import date, datetime

import requests
from sqlalchemy.orm import Session

from ..models import FuelPriceSnapshot

MIMIT_URL = "https://www.mimit.gov.it/index.php/it/prezzo-medio-carburanti/autostrade"
SOURCE = "MIMIT - media nazionale rete autostradale"
MAP = {"Gasolio": ("gasolio", "€/L"), "Benzina": ("benzina", "€/L"), "GPL": ("gpl", "€/L"), "Metano": ("metano", "€/kg")}

def _plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()

def fetch_mimit_prices() -> tuple[date, dict[str, dict]]:
    response = requests.get(MIMIT_URL, timeout=12, headers={"User-Agent": "GiroFacile/1.0"})
    response.raise_for_status()
    body = response.text
    m = re.search(r"Aggiornamento\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})", _plain(body), re.I)
    ref = date.today() if not m else date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    prices = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.I | re.S):
        cells = [_plain(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)]
        if len(cells) < 3 or cells[0] not in MAP:
            continue
        try:
            price = float(cells[2].replace(",", "."))
        except ValueError:
            continue
        key, unit = MAP[cells[0]]
        prices[key] = {"price": price, "unit": unit, "label": cells[0]}
    if not prices:
        raise RuntimeError("Prezzi MIMIT non disponibili")
    return ref, prices

def get_daily_prices(db: Session) -> dict:
    today = date.today()
    rows = db.query(FuelPriceSnapshot).filter(FuelPriceSnapshot.reference_date == today).all()
    if rows:
        return {r.fuel_type: {"price": r.price, "unit": r.unit, "source": r.source, "reference_date": r.reference_date.isoformat()} for r in rows}
    try:
        ref, fetched = fetch_mimit_prices()
        for fuel, info in fetched.items():
            exists = db.query(FuelPriceSnapshot).filter(FuelPriceSnapshot.reference_date == ref, FuelPriceSnapshot.fuel_type == fuel).first()
            if not exists:
                db.add(FuelPriceSnapshot(reference_date=ref, fuel_type=fuel, price=info["price"], unit=info["unit"], source=SOURCE))
        db.commit()
        return {fuel: {**info, "source": SOURCE, "reference_date": ref.isoformat()} for fuel, info in fetched.items()}
    except Exception:
        latest = db.query(FuelPriceSnapshot).order_by(FuelPriceSnapshot.reference_date.desc(), FuelPriceSnapshot.id.desc()).all()
        out = {}
        for r in latest:
            if r.fuel_type not in out:
                out[r.fuel_type] = {"price": r.price, "unit": r.unit, "source": r.source, "reference_date": r.reference_date.isoformat(), "stale": True}
        return out
