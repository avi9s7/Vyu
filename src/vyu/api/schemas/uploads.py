from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PresignUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)
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
