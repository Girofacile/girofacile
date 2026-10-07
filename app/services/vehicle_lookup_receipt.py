"""Bind the saved verification date to a successful lookup, not to a save."""
import hashlib
import hmac
import json
from datetime import datetime

from fastapi import HTTPException

from ..core.config import APP_SECRET


def lookup_signature(user_id, plate, provider, when):
    value = json.dumps(['vehicle-lookup-v1', user_id, plate, provider, when.isoformat()])
    return hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def lookup_receipt(user_id, plate, provider, when=None):
    when = when or datetime.utcnow()
    return {'lookup_at': when.isoformat(),
            'lookup_token': lookup_signature(user_id, plate, provider, when)}


def apply_lookup_receipt(payload, user_id, existing=None):
    when = payload.pop('lookup_at', None)
    token = payload.pop('lookup_token', None)
    if token:
        provider = payload.get('lookup_provider')
        if (not when or not provider or not token.isascii() or
                not hmac.compare_digest(token, lookup_signature(user_id, payload['targa'], provider, when))):
            raise HTTPException(400, 'Verifica targa non valida: ripeti la ricerca.')
        # Replaying a saved result cannot move the verification date backwards.
        if existing and existing.targa == payload['targa'] and existing.lookup_at and when < existing.lookup_at:
            payload['lookup_provider'] = existing.lookup_provider
        else:
            payload['lookup_at'] = when
    elif existing:
        if existing.targa == payload['targa']:
            payload['lookup_provider'] = existing.lookup_provider
        else:
            payload['lookup_provider'] = None
            payload['lookup_at'] = None
