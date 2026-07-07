#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

SUPPORTED_ENVIRONMENTS = ("dev", "staging", "prod")
SUPPORTED_MODES = ("dry-run", "apply")


class ReprocessDocumentError(Exception):
    """Raised when reprocess configuration or API calls fail."""


@dataclass(frozen=True)
class ReprocessPlan:
    environment: str
    tenant_id: str
    workspace_id: str
    document_id: str
    version_id: str | None
    reason: str
    actor: str
    target_parser_version: str
    target_chunker_version: str
    mode: str
    idempotency_key: str


@dataclass(frozen=True)
class ReprocessResult:
    status: str
    mode: str
    document_id: str
    version_id: str | None
    job_id: str | None
    idempotent: bool | None
    detail: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Request governed evidence document reprocessing through the VYU API. "
            "Production use must go through API credentials, not direct database writes."
        ),
    )
    parser.add_argument("--environment", required=True, choices=SUPPORTED_ENVIRONMENTS)
    parser.add_argument("--base-url", required=True, help="Public HTTPS API origin.")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--version-id", default="", help="Optional source version UUID.")
    parser.add_argument("--reason", required=True, help="Operator reason recorded in the ticket.")
    parser.add_argument("--actor", required=True, help="Operator identity for audit evidence.")
    parser.add_argument("--target-parser-version", required=True)
    parser.add_argument("--target-chunker-version", required=True)
    parser.add_argument("--mode", required=True, choices=SUPPORTED_MODES)
    parser.add_argument(
        "--bearer-token-env",
        default="VYU_REPROCESS_BEARER_TOKEN",
        help="Environment variable holding a workspace-admin bearer token.",
    )
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="Optional Idempotency-Key override. A deterministic key is generated when omitted.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args(argv)


def _assert_https_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ReprocessDocumentError("base-url must be an absolute https:// origin.")
    return base_url.rstrip("/")


def _load_bearer_token(env_name: str) -> str:
    token = os.environ.get(env_name, "").strip()
    if not token:
        raise ReprocessDocumentError(
            f"Bearer token environment variable {env_name} is missing or empty."
        )
    return token


def _build_idempotency_key(
    *,
    document_id: str,
    version_id: str | None,
    target_parser_version: str,
    target_chunker_version: str,
    override: str,
) -> str:
    if override.strip():
        return override.strip()
    digest = hashlib.sha256(
        "|".join(
            [
                document_id,
                version_id or "",
                target_parser_version,
                target_chunker_version,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return f"reprocess-{digest[:32]}"


def build_reprocess_plan(args: argparse.Namespace) -> ReprocessPlan:
    version_id = args.version_id.strip() or None
    return ReprocessPlan(
        environment=args.environment,
        tenant_id=args.tenant_id.strip(),
        workspace_id=args.workspace_id.strip(),
        document_id=args.document_id.strip(),
        version_id=version_id,
        reason=args.reason.strip(),
        actor=args.actor.strip(),
        target_parser_version=args.target_parser_version.strip(),
        target_chunker_version=args.target_chunker_version.strip(),
        mode=args.mode,
        idempotency_key=_build_idempotency_key(
            document_id=args.document_id.strip(),
            version_id=version_id,
            target_parser_version=args.target_parser_version.strip(),
            target_chunker_version=args.target_chunker_version.strip(),
            override=args.idempotency_key,
        ),
    )


def run_reprocess_document(
    *,
    base_url: str,
    bearer_token: str,
    plan: ReprocessPlan,
    timeout_seconds: float = 30.0,
    client: httpx.Client | None = None,
) -> ReprocessResult:
    origin = _assert_https_base_url(base_url)
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "application/json",
    }
    detail_url = f"{origin}/v1/evidence-documents/{plan.document_id}"

    def _run(http_client: httpx.Client) -> ReprocessResult:
        detail_response = http_client.get(detail_url, headers=headers)
        if detail_response.status_code == 404:
            raise ReprocessDocumentError("Document was not found for the authenticated tenant.")
        if detail_response.status_code != 200:
            raise ReprocessDocumentError(
                f"Document lookup failed with status {detail_response.status_code}."
            )
        detail = detail_response.json()
        if detail.get("status") == "deleted":
            raise ReprocessDocumentError("Deleted documents cannot be reprocessed.")

        source_version_id = plan.version_id or detail.get("current_version_id")
        if not source_version_id:
            raise ReprocessDocumentError("No source version is available to reprocess.")

        if plan.mode == "dry-run":
            return ReprocessResult(
                status="planned",
                mode=plan.mode,
                document_id=plan.document_id,
                version_id=str(source_version_id),
                job_id=None,
                idempotent=None,
                detail=(
                    f"Would reprocess document {plan.document_id} "
                    f"from version {source_version_id} in {plan.environment} "
                    f"for actor {plan.actor}: {plan.reason}"
                ),
            )

        body = {
            "version_id": source_version_id,
            "target_parser_version": plan.target_parser_version,
            "target_chunker_version": plan.target_chunker_version,
        }
        request_headers = {
            **headers,
            "Idempotency-Key": plan.idempotency_key,
        }
        response = http_client.post(
            f"{origin}/v1/evidence-documents/{plan.document_id}/reprocess",
            headers=request_headers,
            json=body,
        )
        if response.status_code not in {200, 202}:
            raise ReprocessDocumentError(
                f"Reprocess request failed with status {response.status_code}."
            )
        payload = response.json()
        return ReprocessResult(
            status="accepted",
            mode=plan.mode,
            document_id=payload.get("document_id", plan.document_id),
            version_id=payload.get("version_id"),
            job_id=payload.get("job_id"),
            idempotent=bool(payload.get("idempotent")),
            detail=plan.reason,
        )

    if client is None:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as owned_client:
            return _run(owned_client)
    return _run(client)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        plan = build_reprocess_plan(args)
        bearer_token = _load_bearer_token(args.bearer_token_env)
        result = run_reprocess_document(
            base_url=args.base_url,
            bearer_token=bearer_token,
            plan=plan,
            timeout_seconds=args.timeout_seconds,
        )
    except (ReprocessDocumentError, httpx.HTTPError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    payload["environment"] = plan.environment
    payload["tenant_id"] = plan.tenant_id
    payload["workspace_id"] = plan.workspace_id
    payload["actor"] = plan.actor
    payload["idempotency_key"] = plan.idempotency_key
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.status in {"planned", "accepted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
