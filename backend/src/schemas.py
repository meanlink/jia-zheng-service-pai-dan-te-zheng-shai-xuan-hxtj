from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .models import Service, Slot


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


Code = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r'^[A-Z0-9][A-Z0-9-]{2,31}$')]
Minutes = Annotated[int, Field(ge=15, le=720)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=500)]


class Login(Input):
    username: str = Field(min_length=1, max_length=48)
    password: str = Field(min_length=1, max_length=128)


class NewOrder(Input):
    code: Code
    customer: str = Field(min_length=2, max_length=60)
    neighborhood: str = Field(min_length=2, max_length=80)
    service: Service
    service_date: date
    slot: Slot
    area_m2: int = Field(ge=10, le=500)
    dirt_level: int = Field(ge=1, le=5)
    obstacles: int = Field(ge=0, le=15)
    supplies: bool
    baseline_minutes: Minutes


class Renewal(Input):
    certificate: str = Field(min_length=4, max_length=48)
    valid_through: date


class AnalysisRequest(Input):
    technician_id: int = Field(ge=1)


class Review(Input):
    note: Note


class Followup(Review):
    actual_minutes: Minutes


class TimeOff(Review):
    technician_id: int = Field(ge=1)
    off_date: date
    slot: Slot


class VisitContact(Review):
    outcome: Literal['confirmed', 'reschedule', 'moved']
    service_date: date | None = None
    slot: Slot | None = None
