"""Bounded common-depot, same-day fleet planning."""
from datetime import date,time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from . import RoutePlanIn, DeliveryIn

class FleetResource(BaseModel):
    model_config=ConfigDict(extra='forbid')
    vehicle_id: int=Field(gt=0)
    driver_id: int=Field(gt=0)
    max_minutes: int=Field(default=480,ge=1,le=1440)
    energy_price_primary: float=Field(default=1.75,ge=0,le=10000,allow_inf_nan=False)
    energy_price_electric: float=Field(default=0.30,ge=0,le=10000,allow_inf_nan=False)

class FleetStop(DeliveryIn):
    peso_kg: float=Field(default=0,ge=0,le=100000000,allow_inf_nan=False)
    colli: int=Field(default=0,ge=0,le=1000000)
    tempo_scarico_min: int=Field(default=10,ge=0,le=1440)
    @field_validator('scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a')
    @classmethod
    def valid_time(cls,value):
        if value and (len(value)!=5 or time.fromisoformat(value).second): raise ValueError('Usa il formato HH:MM')
        return value
    @model_validator(mode='after')
    def windows(self):
        for start,end in ((self.scarico_mattina_da,self.scarico_mattina_a),(self.scarico_pomeriggio_da,self.scarico_pomeriggio_a)):
            if bool(start)!=bool(end) or (start and start>=end):
                raise ValueError('Indica inizio e fine della fascia oraria nella stessa giornata')
        return self

class FleetInput(RoutePlanIn):
    model_config=ConfigDict(extra='forbid')
    nome: str=Field(default='Piano consegne',max_length=180)
    strategy: Literal['efficient','balanced']='efficient'
    resources: list[FleetResource]=Field(min_length=2,max_length=10)
    consegne: list[FleetStop]=Field(min_length=1,max_length=100)
    @model_validator(mode='after')
    def valid(self):
        date.fromisoformat(self.data_giro)
        clock=time.fromisoformat(self.orario_partenza)
        if len(self.orario_partenza)!=5 or clock.tzinfo or clock.second or clock.microsecond: raise ValueError('Usa ore e minuti per la partenza')
        for key in ('driver_id','vehicle_id'):
            if len({getattr(r,key) for r in self.resources})!=len(self.resources):
                raise ValueError('Seleziona ogni mezzo e autista una sola volta')
        if any(clock.hour*60+clock.minute+r.max_minutes>1440 for r in self.resources):
            raise ValueError('Il termine del lavoro deve essere entro la giornata')
        return self

class FleetRevision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int=Field(ge=1)
    assignments: list[int | None]=Field(min_length=1,max_length=100)

class FleetConfirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int=Field(ge=1)
    accept_unassigned: bool=False
