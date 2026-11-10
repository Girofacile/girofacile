"""Controlli di formato dei dati fiscali italiani (collaudo 10/11: P.IVA «123», PEC «non-una-pec» accettate).

Campi vuoti ammessi: sono facoltativi. Si controlla solo che quanto scritto sia plausibile.
"""
import re
from fastapi import HTTPException


def _vat_checksum_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(digits[:10]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(digits[10])


def vat_error(value):
    v = re.sub(r'[\s.-]', '', str(value or '')).upper()
    if not v:
        return None
    if v.startswith('IT'):
        v = v[2:]
    elif re.fullmatch(r'[A-Z]{2}[A-Z0-9]{2,13}', v):
        return None  # partita IVA di un altro paese UE: si accetta il formato
    if not re.fullmatch(r'\d{11}', v):
        return 'La partita IVA italiana ha 11 cifre.'
    if not _vat_checksum_ok(v):
        return 'Partita IVA non valida: controlla le cifre.'
    return None


def fiscal_code_error(value):
    v = re.sub(r'\s', '', str(value or '')).upper()
    if not v:
        return None
    if re.fullmatch(r'\d{11}', v) or re.fullmatch(r'[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]', v):
        return None
    return 'Il codice fiscale ha 16 caratteri (persona) oppure 11 cifre (azienda).'


def pec_error(value):
    v = str(value or '').strip()
    if not v:
        return None
    if re.fullmatch(r'[^@\s]+@[^@\s]+\.[A-Za-z]{2,}', v):
        return None
    return 'Indirizzo PEC non valido.'


def sdi_error(value):
    v = str(value or '').strip().upper()
    if not v:
        return None
    if re.fullmatch(r'[A-Z0-9]{7}', v) or re.fullmatch(r'[A-Z0-9]{6}', v):
        return None
    return 'Il codice SDI ha 7 caratteri (6 per la Pubblica Amministrazione).'


CHECKS = {'company_vat': vat_error, 'company_fiscal_code': fiscal_code_error, 'company_pec': pec_error, 'company_sdi': sdi_error}


def validate_fiscal(values: dict):
    """422 con il primo campo non valido; i campi assenti o vuoti non si controllano."""
    for key, check in CHECKS.items():
        if key in values:
            message = check(values.get(key))
            if message:
                raise HTTPException(422, message)
