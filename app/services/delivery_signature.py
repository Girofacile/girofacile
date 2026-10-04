"""Shared signature policy for driver and token-based operator portals."""
from fastapi import HTTPException
from ..core.utils import local_now
import base64
import binascii
import io
from PIL import Image, UnidentifiedImageError


def apply_delivery_signature(status, payload, owner, *, required=False):
    if not owner or not owner.delivery_signature_enabled:
        return
    signature = str(payload.get("signature_data") or "").strip()
    name = str(payload.get("signed_by_name") or "").strip()
    if signature:
        if len(signature) > 2_000_000:
            raise HTTPException(400, "Firma troppo grande")
        if not signature.startswith("data:image/png;base64,"):
            raise HTTPException(400, "Formato firma non valido: usa il riquadro firma")
        try:
            raw = base64.b64decode(signature.split(',', 1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or image.width * image.height > 4_000_000:
                    raise ValueError()
                image.verify()
        except (ValueError, binascii.Error, OSError, UnidentifiedImageError, Image.DecompressionBombError):
            raise HTTPException(400, 'Immagine firma non valida')
        if not name:
            raise HTTPException(400, "Nome firmatario mancante")
        status.signature_data = signature
        status.signed_by_name = name[:200]
        status.signature_note = str(payload.get("signature_note") or "").strip() or None
        status.signed_at = local_now().replace(tzinfo=None)
    if required and (not status.signature_data or not status.signed_by_name):
        raise HTTPException(400, "Firma cliente e nome firmatario richiesti prima di confermare la consegna")
