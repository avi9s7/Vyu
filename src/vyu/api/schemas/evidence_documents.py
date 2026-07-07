from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

REPROCESS_ROUTE = "POST /v1/evidence-documents/{document_id}/reprocess"


class DocumentSummary(BaseModel):
    document_id: str
    source_id: str
    external_id: str | None
    title: str | None
    status: str
    media_type: str | None
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    next_cursor: str | None = None


class DocumentVersionSummary(BaseModel):
    version_id: str
    version: int
    sha256: str | None
    size_bytes: int
    media_type: str | None
    filename: str | None
    parser_name: str | None
    parser_version: str | None
    page_count: int | None
    malware_status: str | None
    phi_status: str | None
    created_at: str


class DocumentDetailResponse(BaseModel):
    document_id: str
    source_id: str
    external_id: str | None
    title: str | None
    status: str
    current_version_id: str | None
    created_at: str
    updated_at: str
    current_version: DocumentVersionSummary | None
    block_summary: dict[str, str] | None = None


class DocumentVersionListResponse(BaseModel):
    items: list[DocumentVersionSummary]


class DocumentChunkItem(BaseModel):
    ordinal: int
    citation_id: str
    text: str
    token_count: int
    page_from: int | None
    page_to: int | None
    section: str | None


class DocumentVersionDetail(BaseModel):
    version_id: str
    version: int
    sha256: str | None
    size_bytes: int
    media_type: str | None
    filename: str | None
    parser_name: str | None
    parser_version: str | None
    page_count: int | None
    malware_status: str | None
    phi_status: str | None
    created_at: str
    metadata: dict[str, object] = Field(default_factory=dict)
    chunks: list[DocumentChunkItem] = Field(default_factory=list)


class DocumentEventItem(BaseModel):
    sequence: int
    status: str
    code: str | None
    safe_message: str | None
    created_at: str
    details: dict[str, object] = Field(default_factory=dict)


class DocumentEventListResponse(BaseModel):
    items: list[DocumentEventItem]
    next_cursor: str | None = None


class IngestionJobEventItem(BaseModel):
    sequence: int
    status: str
    code: str | None
    safe_message: str | None
    created_at: str


class IngestionJobDetailResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    attempt: int
    payload: dict[str, object]
    result: dict[str, object] | None
    error_code: str | None
    created_at: str
    updated_at: str
    events: list[IngestionJobEventItem]


class ReprocessDocumentRequest(BaseModel):
    version_id: UUID | None = None
    target_parser_version: str = Field(min_length=1, max_length=64)
    target_chunker_version: str = Field(min_length=1, max_length=64)


class ReprocessDocumentResponse(BaseModel):
    document_id: str
    version_id: str
    job_id: str
    status: str
    idempotent: bool


class RetentionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RetentionRequestResponse(BaseModel):
    document_id: str
    status: str
