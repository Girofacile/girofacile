"""Validated operational input, distinct from immutable received data."""
from datetime import date, time
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Text160 = Annotated[str, Field(min_length=1, max_length=160)]
Nonnegative = Annotated[float, Field(ge=0, le=100000000, allow_inf_nan=False)]


class OrderLineIn(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    description: str = Field(min_length=1, max_length=500)
    sku: str | None = Field(default=None, max_length=160)
    quantity: Nonnegative


class OrderData(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    number: Text160
    recipient_name: str | None = Field(default=None, max_length=200)
    delivery_address: str | None = Field(default=None, max_length=500)
    requested_date: date | None = None
    time_from: time | None = None
    time_to: time | None = None
    weight_kg: Nonnegative | None = None
    packages: int | None = Field(default=None, ge=0, le=1000000)
    pallets: Nonnegative | None = None
    volume_m3: Nonnegative | None = None
    tail_lift: bool | None = None
    pallet_truck: bool | None = None
    ztl: bool | None = None
    requirements: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode='after')
    def window(self):
        if bool(self.time_from) != bool(self.time_to):
            raise ValueError('Indica entrambi gli orari della fascia richiesta')
        if self.time_from and self.time_from >= self.time_to:
            raise ValueError('La fine della fascia deve seguire l’inizio')
        return self


class OrderCreate(OrderData):
    items: list[OrderLineIn] = Field(default_factory=list, max_length=500)


class OrderUpdate(OrderData):
    version: int = Field(ge=1)


class OrderAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    status: Literal['nuovo', 'da_verificare', 'pronto', 'annullato']


class OrderVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=1)


class CustomerResolution(OrderVersion):
    action: Literal['recognize', 'link', 'separate', 'create']
    customer_id: int | None = Field(default=None, gt=0)
