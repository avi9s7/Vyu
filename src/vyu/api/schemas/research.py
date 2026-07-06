from __future__ import annotations

from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from src.vyu.contracts.evidence import StudyDesign

RESEARCH_ROUTE = "POST /v1/research/searches"
DEFAULT_INTENDED_USE = "literature_search"


class CreateResearchSearchRequest(BaseModel):
    question: Annotated[str, Field(min_length=10, max_length=2000)]
    source_ids: Annotated[list[str], Field(min_length=1, max_length=10)]
    intended_use: str = DEFAULT_INTENDED_USE
    date_from: date | None = None
    date_to: date | None = None
    evidence_types: list[StudyDesign] = Field(default_factory=list)
    population: Annotated[str | None, Field(max_length=500)] = None
    intervention: Annotated[str | None, Field(max_length=500)] = None
    comparator: Annotated[str | None, Field(max_length=500)] = None
    only_approved_sources: bool = True

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 10:
            raise ValueError("question must be at least 10 characters after trimming")
        return trimmed

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("source_ids must contain at least one source ID")
        if len(set(normalized)) != len(normalized):
            raise ValueError("source_ids must be unique")
        return normalized

    @field_validator("evidence_types")
    @classmethod
    def unique_evidence_types(cls, value: list[StudyDesign]) -> list[StudyDesign]:
        if len(set(value)) != len(value):
            raise ValueError("evidence_types must be unique")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class ResearchSearchLinks(BaseModel):
    self: str
    events: str
    job: str


class ResearchSearchCreatedResponse(BaseModel):
    search_id: str
    job_id: str
    status: str
    links: ResearchSearchLinks


class ResearchSearchSummary(BaseModel):
    search_id: str
    status: str
    question: str
    cancel_requested: bool
    created_at: str
    job_id: str | None = None


class ResearchSearchListResponse(BaseModel):
    items: list[ResearchSearchSummary]
    next_cursor: str | None = None


class ResearchSearchDetail(ResearchSearchSummary):
    intended_use: str
    requested_sources: list[str]
    current_step: str | None = None
    policy_version: str
    started_at: str | None = None
    completed_at: str | None = None
    links: ResearchSearchLinks


class ResearchEventItem(BaseModel):
    sequence: int
    event_type: str
    safe_message: str
    created_at: str
    details: dict[str, object] = Field(default_factory=dict)


class ResearchEventListResponse(BaseModel):
    items: list[ResearchEventItem]
    next_cursor: str | None = None


class ResearchCancelResponse(BaseModel):
    search_id: str
    status: str
    cancel_requested: bool
