from pydantic import BaseModel
from typing import Optional, List


class SignupIn(BaseModel):
    username: str
    email: Optional[str] = None
    company_name: Optional[str] = None
    password: str
    plan: Optional[str] = "starter"

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
    nome: str | None = None
    indirizzo: str
    predefinito: bool = False
    note: Optional[str] = None

class AgentIn(BaseModel):
    codice_agente: Optional[str] = None
    nome: str | None = None
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
    nome: str | None = None
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
    nome: str | None = None
    targa: Optional[str] = None
    consumo_l_100km: float = 8.5
    capacita_kg: float = 1000
    capacita_colli: int = 100
    ha_sponda: bool = False
    accesso_ztl: bool = False
    note: Optional[str] = None
    photo_url: Optional[str] = None

class DriverIn(BaseModel):
    nome: str
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

class DeliveryIn(BaseModel):
    customer_id: Optional[int] = None
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
    consegne: List[DeliveryIn]

class ManualRoutePlanIn(RoutePlanIn):
    route_id: Optional[int] = None
