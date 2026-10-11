"""Bounded source configuration and acquisition contracts."""
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field
from .orders import OrderCreate

MAX_ROWS=1000
MAX_BYTES=2*1024*1024

class ExternalOrder(OrderCreate):
    external_id: str = Field(min_length=1,max_length=160)
    external_customer_id: str | None = Field(default=None,max_length=160)

class SourceCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str = Field(min_length=1,max_length=160)
    kind: Literal['file','api']
    software: str = Field(default='',max_length=160)

class SourceFields(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    excluded_fields: list[str] = Field(max_length=30)

class SourceUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    mapping: dict[str,str] = Field(max_length=30)

class SourceAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version: int = Field(ge=1)
    action: Literal['activate','pause','resume','remove','revoke','rotate']
    run_id: int | None = None

class RunConfirm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm: Literal[True]

class Acquisition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    batch_id: str = Field(min_length=1,max_length=140,pattern=r'^[A-Za-z0-9_.:-]+$')
    orders: list[dict[str,Any]] = Field(min_length=1,max_length=MAX_ROWS)
    dry_run: bool = False
