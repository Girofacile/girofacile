from .driver_schedule import DriverSchedule
"""Typed, bounded planning snapshots; limits are technical, not subscription quotas."""
from datetime import date, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import DeliveryIn
from .fleet_planning import FleetResource

MAX_SELECTION = 1000


class SelectionFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    q: str = Field(default='', max_length=200)
    status: str | None = None
    source_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None


class SelectionChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    action: Literal['add', 'remove', 'all_filtered', 'clear']
    order_ids: list[int] = Field(default_factory=list, max_length=MAX_SELECTION)
    filters: SelectionFilters = Field(default_factory=SelectionFilters)


class PlanningConfiguration(BaseModel):
    driver_schedule: DriverSchedule | None = None
    model_config = ConfigDict(extra='forbid')
    group_orders: bool = False
    planning_mode: Literal['single','fleet'] = 'single'
    fleet_strategy: Literal['efficient','balanced'] = 'efficient'
    fleet_resources: list[FleetResource] = Field(default_factory=list,max_length=10)
    nome: str = Field(default='', max_length=200)
    data_giro: str = Field(default='', max_length=10)
    orario_partenza: str = Field(default='', max_length=8)
    deposit_id: int | None = None
    vehicle_id: int | None = None
    driver_id: int | None = None
    rientro_deposito: bool = True
    energy_price_mode: Literal['manual', 'automatic'] = 'manual'
    energy_price_primary: float = Field(default=0, ge=0, le=100000, allow_inf_nan=False)
    energy_price_electric: float = Field(default=0, ge=0, le=100000, allow_inf_nan=False)

    @field_validator('data_giro')
    @classmethod
    def valid_date(cls, value):
        if value:
            date.fromisoformat(value)
        return value

    @field_validator('orario_partenza')
    @classmethod
    def valid_time(cls, value):
        if value:
            time.fromisoformat(value)
        return value


class SelectionSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    configuration: PlanningConfiguration
    stops: list[DeliveryIn] | None = Field(default=None, max_length=MAX_SELECTION)


class SelectionVerify(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    order_ids: list[int] = Field(min_length=1,max_length=3)
    retry: bool = False


class SelectionAddressResolution(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    version: int = Field(ge=1)
    order_id: int = Field(gt=0)
    order_version: int = Field(ge=1)
    action: Literal['correct','manual','exclude']
    address: str = Field(default='',max_length=500)
    recipient_name: str = Field(default='',max_length=200)
    lat: float | None = Field(default=None,ge=-90,le=90,allow_inf_nan=False)
    lon: float | None = Field(default=None,ge=-180,le=180,allow_inf_nan=False)
