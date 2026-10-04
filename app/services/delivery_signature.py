"""Signature compatibility helpers; all new evidence uses the POD storage service."""
from .delivery_pod import normalize_image


def legacy_signature_image(signature_data):
    return normalize_image(signature_data, 'signature')
