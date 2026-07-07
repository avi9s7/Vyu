#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from src.vyu.ingestion.staging_fixtures import (
    BLOCKED_STAGING_FIXTURES,
    CLEAN_STAGING_FIXTURES,
    StagingUploadFixture,
)

SUPPORTED_ENVIRONMENTS = ("dev", "staging", "prod")
DEFAULT_SOURCE_ID = "internal_documents"
POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 30.0


class IngestionStagingValidationError(Exception):
    """Raised when staging validation configuration or API calls fail."""


@dataclass(frozen=True)
class StagingCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class StagingValidationResult:
    status: str
    environment: str
    base_url: str
    checks: tuple[StagingCheck, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "environment": self.environment,
            "base_url": self.base_url,
            "checks": [asdict(check) for check in self.checks],
        }


CLEAN_FIXTURES = CLEAN_STAGING_FIXTURES
BLOCKED_FIXTURES = BLOCKED_STAGING_FIXTURES
UploadFixture = StagingUploadFixture


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run governed evidence ingestion staging validation against a VYU API.",
    )
    parser.add_argument("--environment", required=True, choices=SUPPORTED_ENVIRONMENTS)
    parser.add_argument("--base-url", required=True, help="Public HTTPS API origin.")
    parser.add_argument(
        "--bearer-token-env",
        default="VYU_INGESTION_STAGING_BEARER_TOKEN",
        help="Environment variable holding an upload-capable bearer token.",
    )
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=180.0,
        help="Maximum time to wait for each ingestion job to finish.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--skip-uploads",
        action="store_true",
        help="Run read-only checks only (cross-tenant and metadata probes).",
    )
    parser.add_argument(
        "--output",
        type=argparse.FileType("w", encoding="utf-8"),
        help="Optional path to write JSON evidence.",
    )
    return parser.parse_args(argv)


def _assert_https_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise IngestionStagingValidationError("base-url must be an absolute https:// origin.")
    return base_url.rstrip("/")


def _load_bearer_token(env_name: str) -> str:
    token = os.environ.get(env_name, "").strip()
    if not token:
        raise IngestionStagingValidationError(
            f"Bearer token environment variable {env_name} is missing or empty."
        )
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _sha256_hex(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _upload_presigned_post(
    *,
    upload_url: str,
    fields: dict[str, str],
    body: bytes,
    content_type: str,
    timeout_seconds: float,
) -> httpx.Response:
    multipart_fields = [(key, value) for key, value in fields.items()]
    files = {"file": (fields.get("key", "upload.bin").split("/")[-1], body, content_type)}
    return httpx.post(
        upload_url,
        data=multipart_fields,
        files=files,
        timeout=timeout_seconds,
        follow_redirects=True,
    )


def presign_upload(
    client: httpx.Client,
    *,
    origin: str,
    headers: dict[str, str],
    fixture: UploadFixture,
    source_id: str,
) -> dict[str, Any]:
    payload = {
        "filename": fixture.filename,
        "media_type": fixture.media_type,
        "size_bytes": len(fixture.body),
        "sha256": _sha256_hex(fixture.body),
        "source_id": source_id,
        "contains_phi": False,
    }
    response = client.post(f"{origin}/v1/uploads/presign", headers=headers, json=payload)
    if response.status_code != 201:
        raise IngestionStagingValidationError(
            f"Presign failed for {fixture.name} with status {response.status_code}."
        )
    return response.json()


def finalize_upload(
    client: httpx.Client,
    *,
    origin: str,
    headers: dict[str, str],
    document_id: str,
    version_id: str,
) -> dict[str, Any]:
    response = client.post(
        f"{origin}/v1/uploads/finalize",
        headers=headers,
        json={"document_id": document_id, "version_id": version_id},
    )
    if response.status_code != 200:
        raise IngestionStagingValidationError(
            f"Finalize failed for {document_id} with status {response.status_code}."
        )
    return response.json()


def poll_ingestion_job(
    client: httpx.Client,
    *,
    origin: str,
    headers: dict[str, str],
    job_id: str,
    poll_timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + poll_timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"{origin}/v1/ingestion-jobs/{job_id}", headers=headers)
        if response.status_code != 200:
            raise IngestionStagingValidationError(
                f"Job lookup failed for {job_id} with status {response.status_code}."
            )
        payload = response.json()
        terminal_codes = {
            "ready",
            "duplicate_exact",
            "malware_infected",
            "phi_suspected_phi",
            "phi_unknown",
            "checksum_mismatch",
            "parser_unsupported_format",
            "parser_malformed_document",
            "object_missing",
        }
        event_codes = {event.get("code") for event in payload.get("events", [])}
        if payload.get("status") in {"completed", "failed", "blocked"}:
            return payload
        if terminal_codes & event_codes:
            return payload
        time.sleep(POLL_INTERVAL_SECONDS)
    raise IngestionStagingValidationError(f"Timed out waiting for job {job_id}.")


def get_document_detail(
    client: httpx.Client,
    *,
    origin: str,
    headers: dict[str, str],
    document_id: str,
) -> httpx.Response:
    return client.get(f"{origin}/v1/evidence-documents/{document_id}", headers=headers)


def run_fixture_upload(
    client: httpx.Client,
    *,
    origin: str,
    headers: dict[str, str],
    fixture: UploadFixture,
    source_id: str,
    poll_timeout_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    presign = presign_upload(
        client,
        origin=origin,
        headers=headers,
        fixture=fixture,
        source_id=source_id,
    )
    upload_response = _upload_presigned_post(
        upload_url=presign["upload_url"],
        fields=presign["upload_fields"],
        body=fixture.body,
        content_type=fixture.media_type,
        timeout_seconds=timeout_seconds,
    )
    if upload_response.status_code not in {200, 201, 204}:
        raise IngestionStagingValidationError(
            f"S3 upload failed for {fixture.name} with status {upload_response.status_code}."
        )
    finalize_upload(
        client,
        origin=origin,
        headers=headers,
        document_id=presign["document_id"],
        version_id=presign["version_id"],
    )
    job = poll_ingestion_job(
        client,
        origin=origin,
        headers=headers,
        job_id=presign["job_id"],
        poll_timeout_seconds=poll_timeout_seconds,
    )
    detail_response = get_document_detail(
        client,
        origin=origin,
        headers=headers,
        document_id=presign["document_id"],
    )
    return {
        "fixture": fixture.name,
        "presign": presign,
        "job": job,
        "detail": detail_response.json() if detail_response.status_code == 200 else None,
        "detail_status": detail_response.status_code,
    }


def _check(checks: list[StagingCheck], *, name: str, passed: bool, detail: str) -> None:
    checks.append(StagingCheck(name=name, passed=passed, detail=detail))


def run_ingestion_staging_validation(
    *,
    environment: str,
    base_url: str,
    bearer_token: str,
    source_id: str = DEFAULT_SOURCE_ID,
    poll_timeout_seconds: float = 180.0,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    skip_uploads: bool = False,
    client: httpx.Client | None = None,
) -> StagingValidationResult:
    origin = _assert_https_base_url(base_url)
    checks: list[StagingCheck] = []
    headers = _auth_headers(bearer_token)

    def _run(http_client: httpx.Client) -> None:
        me = http_client.get(f"{origin}/v1/me", headers=headers)
        _check(
            checks,
            name="authenticated_me",
            passed=me.status_code == 200,
            detail=f"status={me.status_code}",
        )

        if skip_uploads:
            return

        ready_documents: list[dict[str, Any]] = []
        blocked_documents: list[dict[str, Any]] = []

        for fixture in CLEAN_FIXTURES:
            outcome = run_fixture_upload(
                http_client,
                origin=origin,
                headers=headers,
                fixture=fixture,
                source_id=source_id,
                poll_timeout_seconds=poll_timeout_seconds,
                timeout_seconds=timeout_seconds,
            )
            detail = outcome["detail"] or {}
            status = detail.get("status")
            version_id = detail.get("current_version_id")
            passed = status == "ready" and version_id is not None
            _check(
                checks,
                name=f"{fixture.name}_ready",
                passed=passed,
                detail=f"status={status}",
            )
            if passed:
                version_response = http_client.get(
                    f"{origin}/v1/evidence-documents/{detail['document_id']}/versions/{version_id}",
                    headers=headers,
                )
                version = version_response.json() if version_response.status_code == 200 else {}
                chunk_count = len(version.get("chunks", []))
                _check(
                    checks,
                    name=f"{fixture.name}_chunks",
                    passed=chunk_count >= 1,
                    detail=f"chunks={chunk_count}",
                )
                ready_documents.append(outcome)

        for fixture in BLOCKED_FIXTURES:
            outcome = run_fixture_upload(
                http_client,
                origin=origin,
                headers=headers,
                fixture=fixture,
                source_id=source_id,
                poll_timeout_seconds=poll_timeout_seconds,
                timeout_seconds=timeout_seconds,
            )
            detail = outcome["detail"] or {}
            block_code = (detail.get("block_summary") or {}).get("code")
            status = detail.get("status")
            _check(
                checks,
                name=f"{fixture.name}_blocked",
                passed=status == "blocked" and block_code == fixture.expect_code,
                detail=f"status={status} code={block_code}",
            )
            version_id = detail.get("current_version_id") or outcome["presign"]["version_id"]
            version_response = http_client.get(
                f"{origin}/v1/evidence-documents/{detail['document_id']}/versions/{version_id}",
                headers=headers,
            )
            chunks = []
            if version_response.status_code == 200:
                chunks = version_response.json().get("chunks", [])
            _check(
                checks,
                name=f"{fixture.name}_not_retrievable",
                passed=len(chunks) == 0,
                detail=f"chunks={len(chunks)}",
            )
            blocked_documents.append(outcome)

        if len(ready_documents) >= 2:
            duplicate_fixture = UploadFixture(
                name="duplicate_txt",
                filename="report.txt",
                media_type="text/plain",
                body=CLEAN_FIXTURES[0].body,
                expect_ready=True,
            )
            duplicate = run_fixture_upload(
                http_client,
                origin=origin,
                headers=headers,
                fixture=duplicate_fixture,
                source_id=source_id,
                poll_timeout_seconds=poll_timeout_seconds,
                timeout_seconds=timeout_seconds,
            )
            detail = duplicate["detail"] or {}
            _check(
                checks,
                name="duplicate_exact_reuse",
                passed=detail.get("status") == "ready",
                detail=f"status={detail.get('status')}",
            )
            finalize_upload(
                http_client,
                origin=origin,
                headers=headers,
                document_id=duplicate["presign"]["document_id"],
                version_id=duplicate["presign"]["version_id"],
            )
            _check(
                checks,
                name="duplicate_finalize_idempotent",
                passed=True,
                detail="second finalize accepted",
            )

        if ready_documents:
            owner_document_id = ready_documents[0]["detail"]["document_id"]
            foreign_headers = {
                "Authorization": f"Bearer {bearer_token}-foreign-{uuid.uuid4().hex[:8]}",
                "Accept": "application/json",
            }
            foreign = http_client.get(
                f"{origin}/v1/evidence-documents/{owner_document_id}",
                headers=foreign_headers,
            )
            _check(
                checks,
                name="cross_tenant_or_auth_rejected",
                passed=foreign.status_code in {401, 403, 404},
                detail=f"status={foreign.status_code}",
            )

        first_presign = presign_upload(
            http_client,
            origin=origin,
            headers=headers,
            fixture=CLEAN_FIXTURES[0],
            source_id=source_id,
        )
        expires_at = first_presign.get("expires_at", "")
        upload_fields = first_presign.get("upload_fields", {})
        _check(
            checks,
            name="presign_expiry_present",
            passed=bool(expires_at),
            detail=f"expires_at={expires_at}",
        )
        _check(
            checks,
            name="presign_kms_required",
            passed=upload_fields.get("x-amz-server-side-encryption") == "aws:kms",
            detail=f"encryption={upload_fields.get('x-amz-server-side-encryption')}",
        )
        _check(
            checks,
            name="presign_checksum_metadata",
            passed=upload_fields.get("x-amz-meta-sha256") == _sha256_hex(CLEAN_FIXTURES[0].body),
            detail="sha256 metadata bound",
        )

    if client is None:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as owned_client:
            _run(owned_client)
    else:
        _run(client)

    status = "pass" if checks and all(check.passed for check in checks) else "fail"
    return StagingValidationResult(
        status=status,
        environment=environment,
        base_url=origin,
        checks=tuple(checks),
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        bearer_token = _load_bearer_token(args.bearer_token_env)
        result = run_ingestion_staging_validation(
            environment=args.environment,
            base_url=args.base_url,
            bearer_token=bearer_token,
            source_id=args.source_id,
            poll_timeout_seconds=args.poll_timeout_seconds,
            timeout_seconds=args.timeout_seconds,
            skip_uploads=args.skip_uploads,
        )
    except (IngestionStagingValidationError, httpx.HTTPError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    if args.output is not None:
        json.dump(payload, args.output, indent=2, sort_keys=True)
        args.output.write("\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
