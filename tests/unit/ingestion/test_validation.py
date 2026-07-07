from __future__ import annotations

import pytest

from src.vyu.ingestion.object_store import build_quarantine_key
from src.vyu.ingestion.validation import UploadValidationError, validate_upload_request


def test_validate_upload_request_accepts_supported_pdf() -> None:
    validated = validate_upload_request(
        filename="report.pdf",
        media_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        contains_phi=False,
    )
    assert validated.filename == "report.pdf"
    assert validated.extension == ".pdf"


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("report.pdf.exe", "double extension"),
        ("bad\x01name.pdf", "control characters"),
        ("huge.bin", "unsupported"),
    ],
)
def test_validate_upload_request_rejects_invalid_filenames(filename: str, message: str) -> None:
    media_type = "application/pdf" if filename.endswith(".pdf") else "application/octet-stream"
    with pytest.raises(UploadValidationError, match=message):
        validate_upload_request(
            filename=filename,
            media_type=media_type,
            size_bytes=1024,
            sha256="b" * 64,
            contains_phi=False,
        )


def test_validate_upload_request_rejects_phi_attestation() -> None:
    with pytest.raises(UploadValidationError, match="contains_phi"):
        validate_upload_request(
            filename="report.pdf",
            media_type="application/pdf",
            size_bytes=1024,
            sha256="c" * 64,
            contains_phi=True,
        )


def test_build_quarantine_key_uses_server_owned_prefix() -> None:
    from uuid import UUID

    tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    workspace_id = UUID("00000000-0000-0000-0000-000000000002")
    document_id = UUID("00000000-0000-0000-0000-000000000003")
    version_id = UUID("00000000-0000-0000-0000-000000000004")
    key = build_quarantine_key(
        env="test",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        document_id=document_id,
        version_id=version_id,
        filename="report.pdf",
    )
    assert key.endswith("/report.pdf")
    assert "/quarantine/" in key
    assert str(tenant_id) in key
    assert str(workspace_id) in key
