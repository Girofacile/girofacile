import re
from datetime import datetime, timezone
from typing import Any

import requests

from ..core.config import (
    MYCARPLATE_API_KEY,
    MYCARPLATE_BASE_URL,
    OPENAPI_AUTOMOTIVE_BASE_URL,
    OPENAPI_AUTOMOTIVE_TOKEN,
    VEHICLE_LOOKUP_PROVIDER,
)


class VehicleLookupError(RuntimeError):
    pass


def normalize_plate(value: str) -> str:
    plate = re.sub(r"[^A-Za-z0-9]", "", (value or "").upper())
    if not 5 <= len(plate) <= 10:
        raise VehicleLookupError("Inserisci una targa valida.")
    return plate


def _pick(data: Any, *paths: str):
    """Return the first non-empty value found in dotted paths, case-insensitively."""
    for path in paths:
        cur = data
        ok = True
        for part in path.split("."):
            if not isinstance(cur, dict):
                ok = False
                break
            if part in cur:
                cur = cur[part]
                continue
            match = next((k for k in cur.keys() if str(k).lower() == part.lower()), None)
            if match is None:
                ok = False
                break
            cur = cur[match]
        if ok and cur not in (None, "", [], {}):
            if isinstance(cur, dict):
                for key in ("CurrentTextValue", "currentTextValue", "value", "Value", "name", "Name"):
                    if cur.get(key) not in (None, ""):
                        return cur[key]
            return cur
    return None


def _fuel_to_internal(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value).strip().lower()
    mapping = [
        (("diesel", "gasolio"), "gasolio"),
        (("petrol", "benzina", "gasoline"), "benzina"),
        (("lpg", "gpl"), "gpl"),
        (("methane", "metano", "cng"), "metano"),
        (("electric", "elettrico", "bev"), "elettrico"),
        (("plug-in hybrid petrol", "plug in hybrid petrol", "phev petrol"), "ibrido_plugin_benzina"),
        (("plug-in hybrid diesel", "plug in hybrid diesel", "phev diesel"), "ibrido_plugin_diesel"),
        (("hybrid petrol", "ibrido benzina"), "ibrido_benzina"),
        (("hybrid diesel", "ibrido diesel"), "ibrido_diesel"),
    ]
    for aliases, result in mapping:
        if any(alias in raw for alias in aliases):
            return result
    if "hybrid" in raw or "ibrid" in raw:
        return "ibrido_benzina"
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        match = re.search(r"\d+(?:[.,]\d+)?", str(value))
        return int(float(match.group(0).replace(",", "."))) if match else None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        match = re.search(r"\d+(?:[.,]\d+)?", str(value))
        return float(match.group(0).replace(",", ".")) if match else None


def _lookup_openapi(plate: str) -> dict:
    if not OPENAPI_AUTOMOTIVE_TOKEN:
        raise VehicleLookupError(
            "Lookup targa non configurato. Inserisci OPENAPI_AUTOMOTIVE_TOKEN nel file .env."
        )
    url = f"{OPENAPI_AUTOMOTIVE_BASE_URL.rstrip('/')}/IT-car/{plate}"
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {OPENAPI_AUTOMOTIVE_TOKEN}", "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise VehicleLookupError("Servizio targa temporaneamente non raggiungibile.") from exc

    if response.status_code == 404:
        raise VehicleLookupError("Targa non trovata dal servizio dati veicolo.")
    if response.status_code in (401, 403):
        raise VehicleLookupError("Token del servizio targa non valido o non autorizzato.")
    if response.status_code >= 400:
        raise VehicleLookupError(f"Servizio targa non disponibile (HTTP {response.status_code}).")

    try:
        payload = response.json()
    except ValueError as exc:
        raise VehicleLookupError("Risposta non valida dal servizio targa.") from exc

    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    brand = _pick(data, "CarMake", "Make", "Brand", "vehicle.brand")
    model = _pick(data, "CarModel", "Model", "vehicle.model")
    description = _pick(data, "Description", "VehicleDescription", "description")
    fuel_raw = _pick(data, "FuelType", "Fuel", "engine.FuelType", "vehicle.engine.energySources")
    if isinstance(fuel_raw, list):
        fuel_raw = " ".join(str(x) for x in fuel_raw)

    result = {
        "targa": plate,
        "marca": str(brand).strip() if brand else None,
        "modello": str(model).strip() if model else None,
        "descrizione": str(description).strip() if description else None,
        "anno_immatricolazione": _to_int(_pick(data, "RegistrationYear", "Year", "registrationYear")),
        "alimentazione": _fuel_to_internal(fuel_raw),
        "alimentazione_raw": str(fuel_raw).strip() if fuel_raw else None,
        "cilindrata_cc": _to_int(_pick(data, "EngineSize", "EngineCapacity", "engine.size", "engine.capacity")),
        "potenza_kw": _to_float(_pick(data, "PowerKW", "PowerKw", "KW", "engine.powerKw")),
        "classe_euro": _pick(data, "EuroStatus", "EuroClass", "EmissionClass", "emissions.euroClass"),
        "carrozzeria": _pick(data, "BodyStyle", "BodyType", "bodyStyle"),
        "provider": "openapi",
        "lookup_at": datetime.now(timezone.utc).isoformat(),
    }
    if not result["marca"] and result["descrizione"]:
        # Keep a useful name even when the provider omits separate make/model fields.
        result["modello"] = result["modello"] or result["descrizione"]
    return result



def _lookup_mycarplate(plate: str) -> dict:
    if not MYCARPLATE_API_KEY:
        raise VehicleLookupError(
            "Lookup targa gratuito non configurato. Inserisci MYCARPLATE_API_KEY nel file .env."
        )

    url = f"{MYCARPLATE_BASE_URL.rstrip('/')}/vehicle"
    try:
        response = requests.get(
            url,
            params={"plate": plate, "country": "IT"},
            headers={"X-API-Key": MYCARPLATE_API_KEY, "Accept": "application/json"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise VehicleLookupError("Servizio targa temporaneamente non raggiungibile.") from exc

    # MyCarPlate restituisce spesso un messaggio JSON utile anche sugli errori.
    # Lo leggiamo prima di gestire lo status, così GiroFacile può mostrare la
    # causa reale (chiave, quota, targa, parametri...) invece di un generico 400.
    error_payload = None
    try:
        error_payload = response.json()
    except ValueError:
        error_payload = None

    def provider_error_message(default: str) -> str:
        if isinstance(error_payload, dict):
            for key in ("message", "error", "detail", "reason"):
                value = error_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, dict):
                    nested = value.get("message") or value.get("detail")
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
        text = (response.text or "").strip()
        if text and len(text) <= 300 and "<html" not in text.lower():
            return text
        return default

    if response.status_code == 404:
        raise VehicleLookupError(provider_error_message("Targa non trovata dal servizio dati veicolo."))
    if response.status_code in (401, 403):
        raise VehicleLookupError(provider_error_message("Chiave MyCarPlate non valida o non autorizzata."))
    if response.status_code == 429:
        raise VehicleLookupError(provider_error_message("Limite giornaliero gratuito MyCarPlate raggiunto."))
    if response.status_code >= 400:
        message = provider_error_message(f"MyCarPlate ha rifiutato la richiesta (HTTP {response.status_code}).")
        # Diagnostica sicura in locale: non stampa mai la API key, ma rende
        # visibile nel terminale il motivo reale restituito dal provider.
        print(f"[MYCARPLATE] HTTP {response.status_code} plate={plate} country=IT: {message}")
        raise VehicleLookupError(message)

    payload = error_payload
    if payload is None:
        raise VehicleLookupError("Risposta non valida dal servizio targa.")
    try:
        # Manteniamo questo blocco per compatibilità con la validazione esistente.
        if not isinstance(payload, (dict, list)):
            raise ValueError
    except ValueError as exc:
        raise VehicleLookupError("Risposta non valida dal servizio targa.") from exc

    if not isinstance(payload, dict) or payload.get("success") is False:
        message = payload.get("message") if isinstance(payload, dict) else None
        raise VehicleLookupError(message or "Impossibile recuperare i dati del veicolo.")

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise VehicleLookupError("Nessun dato veicolo disponibile per questa targa.")

    fuel_raw = _pick(data, "fuelType", "fuel", "engine.fuelType")
    version = _pick(data, "version", "trim", "variant")
    model = _pick(data, "model")

    result = {
        "targa": plate,
        "marca": _pick(data, "make", "brand", "manufacturer"),
        "modello": model,
        "descrizione": version or model,
        "anno_immatricolazione": _to_int(_pick(data, "year", "registrationYear")),
        "alimentazione": _fuel_to_internal(fuel_raw),
        "alimentazione_raw": str(fuel_raw).strip() if fuel_raw else None,
        "cilindrata_cc": _to_int(_pick(data, "engineSize", "engineCapacity", "engine.capacity")),
        "potenza_kw": _to_float(_pick(data, "powerKw", "kw", "engine.powerKw")),
        "classe_euro": _pick(data, "emissionClass", "euroClass"),
        "carrozzeria": _pick(data, "bodyClass", "bodyType", "bodyStyle"),
        "provider": "mycarplate",
        "lookup_at": datetime.now(timezone.utc).isoformat(),
    }
    return result

def lookup_vehicle_by_plate(value: str) -> dict:
    plate = normalize_plate(value)
    provider = (VEHICLE_LOOKUP_PROVIDER or "free").strip().lower()
    if provider in {"free", "local", "manual"}:
        return {
            "targa": plate,
            "provider": "free",
            "manual_required": True,
            "message": "Targa validata. Nessun archivio esterno a pagamento è attivo: completa i dati del mezzo manualmente.",
            "lookup_at": datetime.now(timezone.utc).isoformat(),
        }
    if provider == "mycarplate":
        return _lookup_mycarplate(plate)
    if provider == "openapi":
        return _lookup_openapi(plate)
    raise VehicleLookupError(f"Provider targa non supportato: {provider}")
