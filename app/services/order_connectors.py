"""Native inbound adapters. No network calls and no mailbox-wide access."""
import base64
import hashlib
import hmac
import os
import re
from fastapi import HTTPException
from .order_files import read_file, suggestions, FIELDS

CONNECTORS = ('shopify', 'woocommerce', 'email')


def cipher():
    try:
        from cryptography.fernet import Fernet
        return Fernet(os.environ['ORDER_CONNECTOR_KEY'].encode())
    except (KeyError, ValueError, ImportError):
        raise HTTPException(503, 'Collegamenti automatici da abilitare sul server GiroFacile.')


def seal(secret):
    return cipher().encrypt(secret.encode()).decode()


def unseal(secret):
    from cryptography.fernet import InvalidToken
    try:
        return cipher().decrypt(secret.encode()).decode()
    except InvalidToken:
        raise HTTPException(503, 'Configurazione collegamento non leggibile: contatta assistenza.')


def email_base():
    address = os.getenv('ORDER_INBOUND_ADDRESS', '').strip().lower()
    if not re.fullmatch(r'[a-z0-9-]+@inbound\.postmarkapp\.com', address) or len(address.split('@')[0]) > 38 or len(os.getenv('ORDER_INBOUND_PASSWORD', '')) < 32:
        raise HTTPException(503, 'Ricezione email da abilitare sul server GiroFacile.')
    return address


def connector_public(src):
    kind = src.configuration.get('connector')
    if kind not in CONNECTORS:
        return {}
    from ..core.config import APP_BASE_URL
    info = {'provider': kind, 'store': src.configuration.get('store', ''),
            'received': bool(src.configuration.get('connector_received'))}
    if kind == 'email':
        info['address'] = src.configuration.get('inbound_address', '')
    else:
        info['webhook_url'] = APP_BASE_URL.rstrip('/') + '/api/order-connectors/hooks/' + src.key
    return {'connector': info}


def verify_signature(raw, signature, secret):
    expected = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
    if not hmac.compare_digest(expected.encode(), (signature or '').encode()):
        raise HTTPException(401, 'Firma collegamento non valida.')


def shop_order(body, provider, excluded=()):
    """Only order-created events; never infer parcel counts from item quantities."""
    address = body.get('shipping_address' if provider == 'shopify' else 'shipping') or {}
    if not isinstance(address, dict):
        raise ValueError('Indirizzo non valido')
    name = address.get('name') or ' '.join(str(address.get(k) or '') for k in ('first_name', 'last_name')).strip() or address.get('company')
    keys = ('address1','address2','zip','city','province','country') if provider == 'shopify' else ('address_1','address_2','postcode','city','state','country')
    destination = ', '.join(str(address[k]).strip() for k in keys if address.get(k))
    if not body.get('id') or not str(address.get(keys[0]) or '').strip() or not str(address.get('city') or '').strip():
        raise ValueError('Identificativo o indirizzo di spedizione incompleto')
    if body.get('cancelled_at') or body.get('status') in ('cancelled','refunded','failed','trash'):
        raise ValueError('Ordine annullato o non consegnabile')
    lines = [] if 'items' in excluded else body.get('line_items') or []
    if not isinstance(lines,list) or len(lines)>500:
        raise ValueError('Troppi articoli')
    return {'external_id': str(body['id']), 'number': str(body.get('name' if provider=='shopify' else 'number') or body['id']),
            'recipient_name': name, 'delivery_address': destination,
            'notes': body.get('note' if provider=='shopify' else 'customer_note'),
            'items': [{'description': line.get('title') or line.get('name') or '', 'sku': line.get('sku') or None,
                       'quantity': line.get('quantity')} for line in lines]}


def email_orders(body):
    attachments = body.get('Attachments') or []
    if not isinstance(attachments,list) or len(attachments)>10:
        raise ValueError('Troppi allegati')
    orders=[]
    for attachment in attachments:
        name = str(attachment.get('Name',''))
        if not name.lower().endswith(('.csv','.xlsx')):
            continue
        content = base64.b64decode(attachment.get('Content',''), validate=True)
        headers, rows = read_file(content,name)
        mapping = suggestions(headers)
        # Validation and exclusions happen centrally, after this field association.
        orders.extend({k: row.get(v) for k,v in mapping.items()} for row in rows)
    if orders:
        return orders
    # Deterministic labelled messages only: free text/PDF requires human review.
    text = body.get('TextBody') or ''
    if not isinstance(text,str) or len(text)>20000:
        raise ValueError('Testo email troppo lungo')
    row={}
    for line in text.splitlines():
        if ':' not in line:
            continue
        label,value=line.split(':',1)
        mapping=suggestions([label.strip()])
        for field in mapping:
            if field in row:
                raise ValueError('Campi ripetuti: verifica il messaggio')
            row[field]=value.strip()
    if not row.get('number') or not row.get('recipient_name') or not row.get('delivery_address'):
        raise ValueError('Email non strutturata: verifica il messaggio originale e inserisci manualmente ordine. Sono supportati CSV/Excel e testo con Numero ordine, Destinatario, Indirizzo.')
    row.setdefault('external_id',row['number'])
    return [row]
