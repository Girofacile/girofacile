"""Read and preflight imports before changing any customer record."""
import io
import pandas as pd
from fastapi import HTTPException
from ..models import Customer
from .plans import check_customer_limit


async def read_customer_import(file):
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Il file supera il limite di 10 MB")
    name = (file.filename or "").lower()
    try:
        if name.endswith('.csv'):
            return pd.read_csv(io.BytesIO(content))
        if name.endswith('.xlsx'):
            return pd.read_excel(io.BytesIO(content))
    except Exception:
        raise HTTPException(400, "File non leggibile: verifica formato e intestazioni")
    raise HTTPException(400, "Usa un file CSV o XLSX")


def preflight_customer_import(df, db, user, agent_id=None):
    # Serialize company customer creation, including concurrent imports.
    check_customer_limit(user, db, additional=0)
    existing = {c.codice_cliente: c for c in db.query(Customer).filter(
        Customer.user_id == user.id, Customer.deleted_at.is_(None),
        Customer.codice_cliente.isnot(None)).all()}
    seen = set(existing)
    additional = 0
    for _, row in df.iterrows():
        def value(key):
            raw = row.get(key)
            return '' if pd.isna(raw) else str(raw or '').strip()
        if not value('nome') or not value('indirizzo'):
            continue
        code = value('codice_cliente')
        if agent_id is not None and code in existing and existing[code].agent_id != agent_id:
            raise HTTPException(400, "Un codice cliente appartiene già a un altro cliente aziendale")
        if not code or code not in seen:
            additional += 1
        if code:
            seen.add(code)
    check_customer_limit(user, db, additional=additional)
