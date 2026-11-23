from typing import Annotated, Literal

from pydantic import Field

from .schemas import Input, Note, Review

Area = Annotated[int, Field(ge=10, le=500)]
Dirt = Annotated[int, Field(ge=1, le=5)]
Obstacles = Annotated[int, Field(ge=0, le=15)]
EntryMethod = Literal['customer', 'concierge', 'keyholder']


class ScopeProposal(Input):
    area_m2: Area
    dirt_level: Dirt
    obstacles: Obstacles
    supplies: bool
    note: Note


class ScopeDecision(Review):
    decision: Literal['approved', 'rejected']


class AccessClearance(Review):
    status: Literal['ready', 'blocked']
    entry_method: EntryMethod


class EntryCorrection(Input):
    entry_method: EntryMethod
    entry_instructions: Note


class HandoverIssue(Review):
    correction: EntryCorrection | None = None


class SensitivityScenario(ScopeProposal):
    analysis_event_id: int = Field(ge=1)


class ArrivalReport(Review):
    status: Literal['arrived', 'access_failed']
