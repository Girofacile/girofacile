"""Read and preflight imports before changing any customer record."""
import io
import pandas as pd
from fastapi import HTTPException
from ..core.utils import parse_time_value
from ..models import Customer
from .plans import check_customer_limit

IMPORT_TIME_FIELDS = ("scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a")
MAX_REPORTED_ERRORS = 5


def _blank(raw):
    return raw is None or (not isinstance(raw, str) and pd.isna(raw)) or str(raw).strip() == ''


def unload_minutes(raw, default=10):
    """Tempo di scarico dall'import: vuoto -> default, "15.0" -> 15."""
    if _blank(raw):
        return default
    value = float(str(raw).strip().replace(',', '.'))
    if not value.is_integer() or not 0 <= value <= 1440:
        raise ValueError('tempo_scarico_min deve essere un numero intero di minuti tra 0 e 1440')
    return int(value)


def import_row_errors(row):
    """Errori di formato di una riga di import; lista vuota se valida."""
    errors = []
    times = {}
    for field in IMPORT_TIME_FIELDS:
        raw = row.get(field)
        parsed = None if _blank(raw) else parse_time_value(raw)
        if not _blank(raw) and parsed is None:
            errors.append(f'{field} "{raw}" non è un orario valido (HH:MM)')
        times[field] = parsed
    for start, end, label in (("scarico_mattina_da", "scarico_mattina_a", "mattina"),
                              ("scarico_pomeriggio_da", "scarico_pomeriggio_a", "pomeriggio")):
        if times[start] and times[end] and times[start] >= times[end]:
            errors.append(f'fascia {label}: l\'inizio deve precedere la fine')
    try:
        unload_minutes(row.get('tempo_scarico_min'))
    except ValueError as exc:
        errors.append(str(exc) if 'tempo_scarico_min' in str(exc) else 'tempo_scarico_min non è un numero valido')
    return errors


def customer_address_key(customer):
    return tuple(str(getattr(customer, field, None) or '').strip().casefold()
                 for field in ('indirizzo', 'cap', 'comune', 'provincia'))


def invalidate_imported_address(db, customer, previous_address):
    """Keep an import atomic; changed addresses require a new verification."""
    if previous_address == customer_address_key(customer):
        return
    for field in ('lat', 'lon', 'indirizzo_geocodificato', 'affidabilita_geocodifica',
                  'fonte_geocodifica', 'google_place_id', 'geocodificato_il'):
        setattr(customer, field, None)
    customer.stato_geocodifica = 'da_verificare'
    if customer.id is not None:
        from . import distance_cache as dc
        dc.invalidate_key(db, dc.customer_key(customer.id, user_id=customer.user_id),
                          user_id=customer.user_id, commit=False)


# Intestazioni riconosciute senza badare a maiuscole, spazi, punti e accenti, con i sinonimi più comuni.
COLUMN_ALIASES = {
    'nome': ('nome', 'ragione sociale', 'ragsoc', 'cliente', 'nominativo', 'destinatario', 'denominazione', 'insegna'),
    'codice_cliente': ('codice cliente', 'codice', 'cod cliente', 'codcli', 'cod'),
    'indirizzo': ('indirizzo', 'indirizzo completo', 'indirizzo consegna'),
    'via': ('via', 'strada'),
    'civico': ('civico', 'numero civico', 'n civico', 'nr civico'),
    'cap': ('cap', 'codice postale'),
    'comune': ('comune', 'citta', 'localita', 'paese'),
    'provincia': ('provincia', 'prov', 'pr'),
    'telefono': ('telefono', 'tel', 'cellulare', 'cell', 'recapito'),
    'email': ('email', 'e mail', 'mail', 'posta elettronica'),
    'note': ('note', 'annotazioni'),
    'ztl': ('ztl',),
    'sponda': ('sponda', 'sponda idraulica'),
    'transpallet': ('transpallet',),
    'tempo_scarico_min': ('tempo scarico min', 'tempo scarico', 'tempo di scarico', 'minuti scarico'),
    'scarico_mattina_da': ('scarico mattina da', 'mattina dalle', 'mattina da', 'dalle'),
    'scarico_mattina_a': ('scarico mattina a', 'mattina alle', 'mattina a', 'alle'),
    'scarico_pomeriggio_da': ('scarico pomeriggio da', 'pomeriggio dalle', 'pomeriggio da'),
    'scarico_pomeriggio_a': ('scarico pomeriggio a', 'pomeriggio alle', 'pomeriggio a'),
    'codice_agente': ('codice agente', 'cod agente'),
    'agente': ('agente',),
}


def _header_key(value):
    import unicodedata
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().casefold()
    return ' '.join(''.join(ch if ch.isalnum() else ' ' for ch in text).split())


def normalize_columns(df):
    """Rinomina le intestazioni nei nomi interni (es. «Ragione Sociale» -> nome, «Città» -> comune)."""
    lookup = {_header_key(alias): field for field, aliases in COLUMN_ALIASES.items() for alias in (field, *aliases)}
    renamed, used = {}, set()
    for column in df.columns:
        field = lookup.get(_header_key(column))
        if field and field not in used:
            renamed[column] = field
            used.add(field)
    original = [str(c) for c in df.columns]
    df = df.rename(columns=renamed)
    if 'nome' not in df.columns or not ({'indirizzo', 'via'} & set(df.columns)):
        found = ', '.join(original[:12]) or 'nessuna'
        raise HTTPException(400, 'Nel file mancano le colonne indispensabili: servono «Nome» (o Ragione sociale) '
                                 f'e «Indirizzo» (oppure «Via»). Colonne trovate: {found}.')
    return df


async def read_customer_import(file):
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Il file supera il limite di 10 MB")
    name = (file.filename or "").lower()
    try:
        # Tutto come testo: «NA» (Napoli) non diventa «dato mancante», civico e telefono
        # restano come scritti («12», «0811111111») invece di diventare 12.0 / 811111111.0.
        if name.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False, sep=None, engine='python')
        elif name.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(content), dtype=str, keep_default_na=False)
        else:
            df = None
    except Exception:
        raise HTTPException(400, "File non leggibile: verifica formato e intestazioni")
    if df is None:
        if name.endswith('.xls'):
            raise HTTPException(400, "Il formato .xls (Excel vecchio) non è supportato: in Excel usa «Salva con nome» → «Cartella di lavoro di Excel (.xlsx)» e riprova.")
        raise HTTPException(400, "Usa un file CSV o XLSX")
    return normalize_columns(df)


def preflight_customer_import(df, db, user, agent_id=None):
    # Serialize company customer creation, including concurrent imports.
    check_customer_limit(user, db, additional=0)
    existing = {c.codice_cliente: c for c in db.query(Customer).filter(
        Customer.user_id == user.id, Customer.deleted_at.is_(None),
        Customer.codice_cliente.isnot(None)).all()}
    seen = set(existing)
    additional = 0
    row_errors = []
    for position, (_, row) in enumerate(df.iterrows()):
        def value(key):
            raw = row.get(key)
            return '' if pd.isna(raw) else str(raw or '').strip()
        if not value('nome') or not (value('indirizzo') or value('via')):
            continue
        for message in import_row_errors(row):
            row_errors.append(f'Riga {position + 2}: {message}')
        code = value('codice_cliente')
        if agent_id is not None and code in existing and existing[code].agent_id != agent_id:
            raise HTTPException(400, "Un codice cliente appartiene già a un altro cliente aziendale")
        if not code or code not in seen:
            additional += 1
        if code:
            seen.add(code)
    if row_errors:
        shown = row_errors[:MAX_REPORTED_ERRORS]
        more = len(row_errors) - len(shown)
        suffix = f' (e altri {more} errori)' if more > 0 else ''
        raise HTTPException(400, 'Import non eseguito, correggi il file: ' + '; '.join(shown) + suffix)
    check_customer_limit(user, db, additional=additional)
