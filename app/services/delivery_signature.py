"""Shared signature policy for driver and token-based operator portals."""
from fastapi import HTTPException
from ..core.utils import local_now


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
        if not name:
            raise HTTPException(400, "Nome firmatario mancante")
        status.signature_data = signature
        status.signed_by_name = name[:200]
        status.signature_note = str(payload.get("signature_note") or "").strip() or None
        status.signed_at = local_now().replace(tzinfo=None)
    if required and (not status.signature_data or not status.signed_by_name):
        raise HTTPException(400, "Firma cliente e nome firmatario richiesti prima di confermare la consegna")
