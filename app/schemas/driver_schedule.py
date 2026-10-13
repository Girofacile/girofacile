"""Operator-defined daily working hours and fixed breaks (local time)."""
from datetime import time
from pydantic import BaseModel, ConfigDict, Field, model_validator

class DriverBreak(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: str
    end: str
    @model_validator(mode='after')
    def validate_hours(self):
        for value in (self.start,self.end):
            if len(value)!=5 or time.fromisoformat(value).tzinfo: raise ValueError('Usa orari HH:MM')
        if self.start>=self.end: raise ValueError('La pausa deve terminare dopo il suo inizio, nella stessa giornata')
        return self

class DriverSchedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: str | None = None
    end: str | None = None
    breaks: list[DriverBreak] = Field(default_factory=list,max_length=8)
    @model_validator(mode='after')
    def validate_schedule(self):
        if bool(self.start)!=bool(self.end): raise ValueError('Indica sia inizio sia fine turno')
        if self.start: DriverBreak(start=self.start,end=self.end)
        self.breaks=sorted(self.breaks,key=lambda b:b.start)
        for index,pause in enumerate(self.breaks):
            if self.start and (pause.start<self.start or pause.end>self.end): raise ValueError('Le pause devono essere comprese nel turno')
            if index and self.breaks[index-1].end>pause.start: raise ValueError('Gli orari delle pause non possono sovrapporsi')
        return self
