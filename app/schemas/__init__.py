from pydantic import BaseModel, Field, StringConstraints, field_validator
from typing import Annotated, Optional, List, Literal


RequiredName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


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

class CustomerIn(BaseModel):
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
    tempo_scarico_min: int = 10
    ztl: bool = False
    sponda: bool = False
    transpallet: bool = False
    note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
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
    anno_immatricolazione: Optional[int] = None
    cilindrata_cc: Optional[int] = Field(default=None, ge=0)
    potenza_kw: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    classe_euro: Optional[str] = Field(default=None, max_length=60)
    carrozzeria: Optional[str] = Field(default=None, max_length=100)
    lookup_provider: Optional[str] = Field(default=None, max_length=60)
    toll_class: Literal["A", "B", "3", "4", "5"] = "B"
    consumo_l_100km: float = 8.5
    alimentazione: str = "gasolio"
    consumo_primario_100km: float = 8.5
    consumo_kwh_100km: float = 0
    capacita_kg: float = 1000
    capacita_colli: int = 100
    ha_sponda: bool = False
    accesso_ztl: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None

class DriverIn(BaseModel):
    nome: RequiredName = Field(max_length=150)
    cognome: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    patente: Optional[str] = None
    scadenza_patente: Optional[str] = None
    cqc: bool = False
    scadenza_cqc: Optional[str] = None
    adr: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None

class StopAddressIn(BaseModel):
    indirizzo: str = Field(min_length=4, max_length=500)


class DeliveryIn(BaseModel):
    customer_id: Optional[int] = None
    geocoding_token: Optional[str] = Field(default=None, max_length=128)
    cliente_nome: str
    indirizzo: str
    peso_kg: float = 0
    colli: int = 0
    scarico_mattina_da: Optional[str] = None
    scarico_mattina_a: Optional[str] = None
    scarico_pomeriggio_da: Optional[str] = None
    scarico_pomeriggio_a: Optional[str] = None
    tempo_scarico_min: int = 10
    ztl: bool = False
    sponda: bool = False
    note: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    stato_geocodifica: Optional[str] = None
    indirizzo_geocodificato: Optional[str] = None

class RoutePlanIn(BaseModel):
    nome: str | None = None
    data_giro: str
    orario_partenza: str = "08:00"
    deposit_id: int
    vehicle_id: Optional[int] = None
    driver_id: Optional[int] = None
    rientro_deposito: bool = True
    prezzo_carburante_litro: float = 1.75
    energy_price_mode: str = "manual"
    energy_price_primary: float = 0
    energy_price_electric: float = 0
    consegne: List[DeliveryIn]

class ManualRoutePlanIn(RoutePlanIn):
    route_id: Optional[int] = None
