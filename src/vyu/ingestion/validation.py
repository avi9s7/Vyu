from __future__ import annotations

import re
from dataclasses import dataclass

from src.vyu.ingestion.settings import MAX_UPLOAD_BYTES

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
_DOUBLE_EXTENSION_PATTERN = re.compile(r"\.[^.]+\.[^.]+$")

_ALLOWED_MEDIA_TYPES: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
    ".txt": frozenset({"text/plain"}),
    ".html": frozenset({"text/html"}),
}


class UploadValidationError(ValueError):
    """Raised when an upload request fails local validation."""


@dataclass(frozen=True)
class ValidatedUploadRequest:
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    extension: str


def validate_upload_request(
    *,
    filename: str,
    media_type: str,
    size_bytes: int,
    sha256: str,
    contains_phi: bool,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
) -> ValidatedUploadRequest:
    if contains_phi:
        raise UploadValidationError("contains_phi attestation must be false")
    if not sha256 or len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
        raise UploadValidationError("sha256 must be a 64-character lowercase hex digest")
    if size_bytes < 1 or size_bytes > max_upload_bytes:
        raise UploadValidationError("size_bytes exceeds the 50 MiB upload limit")
    cleaned = filename.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise UploadValidationError("filename is required")
    if _CONTROL_CHAR_PATTERN.search(cleaned):
        raise UploadValidationError("filename contains control characters")
    if _DOUBLE_EXTENSION_PATTERN.search(cleaned):
        raise UploadValidationError("filename has a disallowed double extension")
    extension = _extension_for(cleaned)
    allowed_media_types = _ALLOWED_MEDIA_TYPES.get(extension)
    if allowed_media_types is None:
        raise UploadValidationError("unsupported file extension")
    if media_type not in allowed_media_types:
        raise UploadValidationError("media_type does not match file extension")
    return ValidatedUploadRequest(
        filename=sanitize_filename(cleaned),
        media_type=media_type,
        size_bytes=size_bytes,
        sha256=sha256,
        extension=extension,
    )


def sanitize_filename(filename: str) -> str:
    basename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return basename.replace("\x00", "").strip()


def _extension_for(filename: str) -> str:
    dot_index = filename.rfind(".")
    if dot_index <= 0:
        raise UploadValidationError("unsupported file extension")
    return filename[dot_index:].lower()
