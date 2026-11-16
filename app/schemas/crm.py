from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CRMInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    version: int | None = Field(default=None, ge=1)

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if isinstance(value, bool):
            raise ValueError('Versione non valida')
        return value


class CompanyIn(CRMInput):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(default='', max_length=220)
    phone: str = Field(default='', max_length=80)
    vat: str | None = Field(default=None, max_length=80)
    country: str = Field(default='IT', pattern=r'^[A-Za-z]{2}$')
    sector: str = Field(default='', max_length=120)
    city: str = Field(default='', max_length=150)
    source: str = Field(default='', max_length=120)
    interest: Literal['unknown', 'interested', 'later', 'not_interested'] = 'unknown'
    owner_id: int | None = Field(default=None, gt=0)
    notes: str = Field(default='', max_length=10000)
    archived: bool = False

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        if value and ('@' not in value or any(c.isspace() for c in value) or not all(value.split('@')) or value.count('@') != 1):
            raise ValueError('Email non valida')
        return value.lower()

    @field_validator('country')
    @classmethod
    def country_code(cls, value):
        return value.upper()

    @field_validator('vat')
    @classmethod
    def normalize_vat(cls, value):
        return ''.join((value or '').upper().split()) or None


class ContactIn(CRMInput):
    company_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=200)
    role: str = Field(default='', max_length=120)
    email: str = Field(default='', max_length=220)
    phone: str = Field(default='', max_length=80)
    do_not_contact: bool = False
    notes: str = Field(default='', max_length=10000)
    _email = field_validator('email')(CompanyIn.email_address.__func__)


def utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError('La data deve includere il fuso orario')
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class OpportunityIn(CRMInput):
    company_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    stage: Literal['new', 'contacted', 'qualified', 'demo', 'proposal', 'negotiation', 'won', 'lost'] = 'new'
    amount: Decimal = Field(default=Decimal('0'), ge=0, max_digits=14, decimal_places=2)
    probability: int = Field(default=0, ge=0, le=100)
    expected_close: datetime | None = None
    lost_reason: str = Field(default='', max_length=500)
    notes: str = Field(default='', max_length=10000)
    _date = field_validator('expected_close')(utc)

    @model_validator(mode='after')
    def loss_reason(self):
        if self.stage == 'lost' and not self.lost_reason:
            raise ValueError('Indica il motivo della perdita')
        return self


class FollowupIn(CRMInput):
    company_id: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=200)
    due_at: datetime
    status: Literal['open', 'completed', 'cancelled'] = 'open'
    priority: Literal['normal', 'high'] = 'normal'
    notes: str = Field(default='', max_length=10000)
    _date = field_validator('due_at')(utc)


class ActivityIn(CRMInput):
    company_id: int = Field(gt=0)
    kind: Literal['note', 'call', 'email', 'meeting'] = 'note'
    notes: str = Field(min_length=1, max_length=10000)
    occurred_at: datetime
    _date = field_validator('occurred_at')(utc)
