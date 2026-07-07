from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


INDEX_BUILD_ROUTE = "POST /v1/admin/retrieval/indexes/build"


class CreateIndexBuildRequest(BaseModel):
    policy_version: str = Field(min_length=1, max_length=128)
    source_ids: list[str] | None = None
    use_case: str | None = Field(default=None, max_length=64)
    reason: str = Field(min_length=1, max_length=255)


class IndexBuildCreatedResponse(BaseModel):
    retrieval_index_id: UUID
    job_id: UUID
    status: str
    links: dict[str, str]


class IndexRecordSummary(BaseModel):
    retrieval_index_id: UUID
    status: str
    use_case: str
    manifest_checksum: str
    document_count: int
    chunk_count: int
    created_at: str


class IndexRecordListResponse(BaseModel):
    items: list[IndexRecordSummary]


class ResearchEvidenceItem(BaseModel):
    citation_id: str
    document_id: str
    rank: int
    score_source: str
    score_value: float
    retrieval_index_id: UUID
    retrieval_run_id: UUID


class ResearchEvidenceExclusionSummary(BaseModel):
    total: int
    kinds: dict[str, int]


class ResearchEvidenceListResponse(BaseModel):
    items: list[ResearchEvidenceItem]
    exclusions: ResearchEvidenceExclusionSummary
    abstention_reason: str | None = None
