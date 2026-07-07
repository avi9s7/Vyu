from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
    external_id: str | None = Field(default=None, max_length=255)
    contains_phi: bool

    @field_validator("contains_phi")
    @classmethod
    def phi_must_be_false(cls, value: bool) -> bool:
        if value:
            raise ValueError("contains_phi must be false")
        return value


class PresignUploadResponse(BaseModel):
    document_id: str
    version_id: str
    job_id: str
    upload_url: str
    upload_fields: dict[str, str]
    expires_at: str
    object_key: str


class FinalizeUploadRequest(BaseModel):
    document_id: UUID
    version_id: UUID


class FinalizeUploadResponse(BaseModel):
    document_id: str
    version_id: str
    status: str
    idempotent: bool
