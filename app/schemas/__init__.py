from .driver_schedule import DriverSchedule
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from typing import Annotated, Optional, List, Literal
from datetime import date, datetime

from ..core.utils import parse_time_value


RequiredName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

TIME_WINDOW_FIELDS = ("scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a")
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Latitude = Annotated[Optional[float], Field(default=None, ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[Optional[float], Field(default=None, ge=-180, le=180, allow_inf_nan=False)]
UnloadMinutes = Annotated[int, Field(ge=0, le=1440)]


def strict_time_text(value, label: str = "Orario"):
    """Vuoto -> None; orario valido -> "HH:MM"; altrimenti errore esplicito.

    Evita che un orario scritto male diventi silenziosamente "nessun vincolo".
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    parsed = parse_time_value(value)
    if parsed is None:
        raise ValueError(f"{label} non valido: usa il formato HH:MM")
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def strict_date_text(value, label: str = "Data"):
    """Vuoto -> None; data ISO valida -> "YYYY-MM-DD"; altrimenti errore."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        raise ValueError(f"{label} non valida: usa il formato AAAA-MM-GG") from None


def check_time_windows(item):
    """Una fascia con inizio e fine deve avere l'inizio prima della fine."""
    for start, end, label in (
        (item.scarico_mattina_da, item.scarico_mattina_a, "mattina"),
        (item.scarico_pomeriggio_da, item.scarico_pomeriggio_a, "pomeriggio"),
    ):
        if start and end and start >= end:
            raise ValueError(f"Fascia di scarico {label}: l'orario di inizio deve precedere quello di fine")
    return item


class TimeWindowsMixin:
    @field_validator(*TIME_WINDOW_FIELDS, mode="before", check_fields=False)
    @classmethod
    def _valid_window_time(cls, value):
        return strict_time_text(value, "Orario di scarico")

    @model_validator(mode="after")
    def _valid_windows(self):
        return check_time_windows(self)


class SignupIn(BaseModel):
    username: str
    email: Optional[str] = None
    company_name: Optional[str] = None
    password: str
    plan: Optional[str] = None

    # v46 — registrazione azienda professionale
    company_phone: Optional[str] = None
    company_vat: Optional[str] = None
    company_fiscal_code: Optional[str] = None
    company_pec: Optional[str] = None
    company_sdi: Optional[str] = None
    company_address: Optional[str] = None
    company_city: Optional[str] = None
    company_zip: Optional[str] = None
    company_country: Optional[str] = "Italia"
    company_legal_address: Optional[str] = None
    company_billing_address: Optional[str] = None
    company_sector: Optional[str] = None
    company_activity_type: Optional[str] = None
    company_size: Optional[str] = None
    daily_deliveries: Optional[str] = None
    has_time_windows: bool = True
    needs_signature: bool = False
    needs_photo_proof: bool = False
    has_refrigerated_goods: bool = False
    has_ztl: bool = False
    needs_tail_lift: bool = False

class DepositIn(BaseModel):
    nome: RequiredName = Field(max_length=200)
    indirizzo: str
    predefinito: bool = False
    note: Optional[str] = None

class AgentIn(BaseModel):
    codice_agente: Optional[str] = None
    nome: RequiredName = Field(max_length=150)
    cognome: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    zona: Optional[str] = None
    attivo: bool = True
    note: Optional[str] = None
    photo_url: Optional[str] = None

class CustomerIn(TimeWindowsMixin, BaseModel):
    agent_id: Optional[int] = None
    codice_cliente: Optional[str] = None
    nome: RequiredName = Field(max_length=250)
    indirizzo: str
    comune: Optional[str] = None
    provincia: Optional[str] = None
    telefono: Optional[str] = None
    referente: Optional[str] = None
    email: Optional[str] = None
    scarico_mattina_da: Optional[str] = None
    scarico_mattina_a: Optional[str] = None
    scarico_pomeriggio_da: Optional[str] = None
    scarico_pomeriggio_a: Optional[str] = None
    tempo_scarico_min: UnloadMinutes = 10
    ztl: bool = False
    pedestrian_area: bool = False
    sponda: bool = False
    transpallet: bool = False
    note: Optional[str] = None
    lat: Latitude = None
    lon: Longitude = None
    indirizzo_geocodificato: Optional[str] = None
    stato_geocodifica: Optional[str] = None
    affidabilita_geocodifica: Optional[float] = None
    fonte_geocodifica: Optional[str] = None
    google_place_id: Optional[str] = None

class VehicleIn(BaseModel):
    @field_validator("alimentazione", mode="before")
    @classmethod
    def normalize_alimentazione(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    nome: RequiredName = Field(max_length=150)
    targa: Optional[str] = None
    marca: Optional[str] = Field(default=None, max_length=100)
    modello: Optional[str] = Field(default=None, max_length=160)
    anno_immatricolazione: Optional[int] = Field(default=None, ge=1900, le=2100)
    cilindrata_cc: Optional[int] = Field(default=None, ge=0)
    potenza_kw: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    classe_euro: Optional[str] = Field(default=None, max_length=60)
    carrozzeria: Optional[str] = Field(default=None, max_length=100)
    lookup_provider: Optional[str] = Field(default=None, max_length=60)
    lookup_at: Optional[datetime] = None
    lookup_token: Optional[str] = Field(default=None, max_length=64)
    toll_class: Literal["A", "B", "3", "4", "5"] = "B"
    consumo_l_100km: NonNegativeFloat = 8.5
    alimentazione: str = "gasolio"
    consumo_primario_100km: NonNegativeFloat = 8.5
    consumo_kwh_100km: NonNegativeFloat = 0
    capacita_kg: NonNegativeFloat = 1000
    capacita_colli: int = Field(default=100, ge=0)
    ha_sponda: bool = False
    accesso_ztl: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None

class DriverIn(BaseModel):
    work_schedule: DriverSchedule = Field(default_factory=DriverSchedule)
    nome: RequiredName = Field(max_length=150)
    cognome: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    patente: Optional[str] = None
    scadenza_patente: Optional[str] = None
    cqc: bool = False
    scadenza_cqc: Optional[str] = None

    @field_validator("scadenza_patente", "scadenza_cqc", mode="before")
    @classmethod
    def _valid_expiry(cls, value):
        return strict_date_text(value, "Data di scadenza")
    adr: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None

class StopAddressIn(BaseModel):
    indirizzo: str = Field(min_length=4, max_length=500)


class OrderReference(BaseModel):
    id: int = Field(gt=0)
    version: int = Field(ge=1)


class DeliveryIn(TimeWindowsMixin, BaseModel):
    order_refs: list[OrderReference] = Field(default_factory=list, max_length=1000)
    order_stop_key: str | None = Field(default=None, max_length=36)
    customer_id: Optional[int] = None
    geocoding_token: Optional[str] = Field(default=None, max_length=128)
    cliente_nome: str
    indirizzo: str
    peso_kg: NonNegativeFloat = 0
    colli: int = Field(default=0, ge=0)
    scarico_mattina_da: Optional[str] = None
    scarico_mattina_a: Optional[str] = None
    scarico_pomeriggio_da: Optional[str] = None
    scarico_pomeriggio_a: Optional[str] = None
    tempo_scarico_min: UnloadMinutes = 10
    ztl: bool = False
    pedestrian_area: bool = False
    sponda: bool = False
    note: Optional[str] = None
    lat: Latitude = None
    lon: Longitude = None
    stato_geocodifica: Optional[str] = None
    indirizzo_geocodificato: Optional[str] = None

class RoutePlanIn(BaseModel):
    driver_schedule: DriverSchedule | None = None
    nome: str | None = None
    data_giro: str
    orario_partenza: str = "08:00"
    deposit_id: int
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None
    rientro_deposito: bool = True
    prezzo_carburante_litro: NonNegativeFloat = 1.75
    energy_price_mode: str = "manual"
    energy_price_primary: NonNegativeFloat = 0
    energy_price_electric: NonNegativeFloat = 0
    consegne: List[DeliveryIn]

    @field_validator("data_giro", mode="before")
    @classmethod
    def _valid_route_date(cls, value):
        parsed = strict_date_text(value, "Data del giro")
        if parsed is None:
            raise ValueError("Data del giro obbligatoria")
        return parsed

    @field_validator("orario_partenza", mode="before")
    @classmethod
    def _valid_departure(cls, value):
        return strict_time_text(value, "Orario di partenza") or "08:00"

class ManualRoutePlanIn(RoutePlanIn):
    route_id: Optional[int] = None
