from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorField(BaseModel):
    path: str
    code: str


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    fields: list[ErrorField] = Field(default_factory=list)


class ErrorEnvelope(BaseModel):
    request_id: str
    trace_id: str
    status: str = "error"
    error: ErrorBody


def build_error_response(
    *,
    request_id: str,
    trace_id: str,
    code: str,
    message: str,
    retryable: bool = False,
    fields: list[ErrorField] | None = None,
) -> dict[str, Any]:
    envelope = ErrorEnvelope(
        request_id=request_id,
        trace_id=trace_id,
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            fields=fields or [],
        ),
    )
    return envelope.model_dump()
