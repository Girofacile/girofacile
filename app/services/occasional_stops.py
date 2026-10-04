"""Durable, tenant-bound Google verification for a delivery without a Customer.

The signature covers the exact saved address and coordinates, so edits require
verification again. It survives route reopening without another Google request.
It is an address attestation, never an authentication or route-access token.
"""
import hashlib
import hmac
import json

from fastapi import HTTPException

from ..core.config import APP_SECRET
from .customer_planning import has_verified_coordinates
from .geocoding import geocode_address

STOP_VERIFICATION_FIELDS = ("geocoding_token", "stato_geocodifica", "indirizzo_geocodificato")
VERIFICATION_ERROR = "Verifica l'indirizzo della fermata occasionale prima di inserirla nel giro."


def sign_stop_address(user_id, address, lat, lon):
    value = json.dumps(["occasional-stop-v1", int(user_id), address, float(lat), float(lon)],
                       ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hmac.new(APP_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify_stop_address(db, user_id, address):
    result = geocode_address(address, db=db, user_id=user_id)
    if not has_verified_coordinates(result.get("status"), result.get("lat"), result.get("lon")):
        raise HTTPException(400, "Indirizzo non verificato. Completa via, numero civico e comune e riprova.")
    address = result.get("formatted") or address.strip()
    lat, lon = float(result["lat"]), float(result["lon"])
    return {"indirizzo": address, "indirizzo_geocodificato": address,
            "lat": lat, "lon": lon, "stato_geocodifica": "verificato",
            "geocoding_token": sign_stop_address(user_id, address, lat, lon)}


def validate_occasional_stops(user_id, deliveries):
    for delivery in deliveries:
        if delivery.get("customer_id") is not None:
            continue  # Registry customers always follow the registry validation.
        valid = has_verified_coordinates(delivery.get("stato_geocodifica"),
                                         delivery.get("lat"), delivery.get("lon"))
        token = delivery.get("geocoding_token")
        if not valid or not isinstance(token, str) or not token.isascii():
            raise HTTPException(400, VERIFICATION_ERROR)
        expected = sign_stop_address(user_id, delivery.get("indirizzo"), delivery["lat"], delivery["lon"])
        if not hmac.compare_digest(token, expected):
            raise HTTPException(400, VERIFICATION_ERROR)
        if not str(delivery.get("cliente_nome") or "").strip():
            raise HTTPException(400, "Inserisci il nome della fermata occasionale.")
        delivery["indirizzo_geocodificato"] = delivery["indirizzo"]
