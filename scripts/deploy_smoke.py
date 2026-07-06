#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_RESEARCH_PAYLOAD: dict[str, object] = {
    "question": "What is the efficacy of VX-101 for episodic migraine prevention?",
    "source_ids": ["pubmed"],
    "only_approved_sources": True,
}

SENSITIVE_RESPONSE_MARKERS = (
    "bearer ",
    "password",
    "secret",
    "api_key",
    "authorization:",
)

REQUIRED_SECURITY_HEADERS = (
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
)


class DeploySmokeError(Exception):
    """Raised when smoke configuration is invalid."""


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DeploySmokeResult:
    status: str
    base_url: str
    checks: tuple[SmokeCheck, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "base_url": self.base_url,
            "checks": [asdict(check) for check in self.checks],
        }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run HTTPS post-deploy smoke checks against a VYU environment.",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Public HTTPS origin, for example https://staging.example.com",
    )
    parser.add_argument(
        "--bearer-token-env",
        default="VYU_DEPLOY_SMOKE_BEARER_TOKEN",
        help="Environment variable that holds the operator bearer token.",
    )
    parser.add_argument(
        "--idempotency-key",
        default="",
        help="Optional idempotency key for the research submission probe.",
    )
    parser.add_argument(
        "--research-payload-json",
        type=argparse.FileType("r", encoding="utf-8"),
        help="Optional JSON file overriding the default research submission body.",
    )
    parser.add_argument(
        "--expected-git-sha",
        default="",
        help="Optional deployed git SHA to verify from /v1/version.",
    )
    parser.add_argument(
        "--expected-schema-revision",
        default="",
        help="Optional Alembic revision to verify from /v1/version.",
    )
    parser.add_argument(
        "--expected-image-digest",
        default="",
        help="Optional image digest to verify from /v1/version.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="Per-request timeout.",
    )
    return parser.parse_args(argv)


def _load_bearer_token(env_name: str) -> str:
    token = os.environ.get(env_name, "").strip()
    if not token:
        raise DeploySmokeError(
            f"Bearer token environment variable {env_name} is missing or empty."
        )
    return token


def _assert_https_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise DeploySmokeError("base-url must be an absolute https:// origin.")
    return base_url.rstrip("/")


def _response_is_safe(body_text: str) -> bool:
    lowered = body_text.lower()
    return not any(marker in lowered for marker in SENSITIVE_RESPONSE_MARKERS)


def _check(
    checks: list[SmokeCheck],
    *,
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append(SmokeCheck(name=name, passed=passed, detail=detail))


def run_deploy_smoke(
    *,
    base_url: str,
    bearer_token: str,
    research_payload: dict[str, object],
    idempotency_key: str,
    expected_git_sha: str = "",
    expected_schema_revision: str = "",
    expected_image_digest: str = "",
    timeout_seconds: float = 30.0,
    client: httpx.Client | None = None,
) -> DeploySmokeResult:
    origin = _assert_https_base_url(base_url)
    checks: list[SmokeCheck] = []
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "application/json",
    }

    def _run(client: httpx.Client) -> None:
        live = client.get(f"{origin}/v1/health/live")
        _check(
            checks,
            name="health_live",
            passed=live.status_code == 200 and live.json().get("status") == "ok",
            detail=f"status={live.status_code}",
        )
        _check(
            checks,
            name="health_live_request_id",
            passed=bool(live.headers.get("x-request-id")),
            detail="x-request-id present",
        )

        ready = client.get(f"{origin}/v1/health/ready")
        _check(
            checks,
            name="health_ready",
            passed=ready.status_code == 200 and ready.json().get("status") == "ready",
            detail=f"status={ready.status_code}",
        )

        version = client.get(f"{origin}/v1/version")
        version_payload = version.json() if version.headers.get("content-type", "").startswith(
            "application/json"
        ) else {}
        version_ok = version.status_code == 200 and _response_is_safe(version.text)
        if expected_git_sha:
            version_ok = version_ok and version_payload.get("git_sha") == expected_git_sha
        if expected_schema_revision:
            version_ok = version_ok and version_payload.get("schema_revision") == (
                expected_schema_revision
            )
        if expected_image_digest:
            version_ok = version_ok and version_payload.get("image_digest") == (
                expected_image_digest
            )
        _check(
            checks,
            name="version",
            passed=version_ok,
            detail=f"status={version.status_code}",
        )

        unauthenticated = client.get(f"{origin}/v1/research/searches")
        _check(
            checks,
            name="unauthenticated_rejection",
            passed=unauthenticated.status_code == 401,
            detail=f"status={unauthenticated.status_code}",
        )

        me = client.get(f"{origin}/v1/me", headers=headers)
        me_payload = me.json() if me.headers.get("content-type", "").startswith(
            "application/json"
        ) else {}
        _check(
            checks,
            name="authenticated_me",
            passed=(
                me.status_code == 200
                and bool(me_payload.get("user_id"))
                and bool(me_payload.get("tenant_id"))
                and _response_is_safe(me.text)
            ),
            detail=f"status={me.status_code}",
        )

        research_headers = {
            **headers,
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        }
        first_submit = client.post(
            f"{origin}/v1/research/searches",
            headers=research_headers,
            json=research_payload,
        )
        second_submit = client.post(
            f"{origin}/v1/research/searches",
            headers=research_headers,
            json=research_payload,
        )
        first_payload = first_submit.json()
        second_payload = second_submit.json()
        idempotent_ok = (
            first_submit.status_code == 202
            and second_submit.status_code == 202
            and first_payload.get("search_id") == second_payload.get("search_id")
            and first_payload.get("job_id") == second_payload.get("job_id")
        )
        _check(
            checks,
            name="research_idempotent_submission",
            passed=idempotent_ok,
            detail=(
                f"first={first_submit.status_code} "
                f"second={second_submit.status_code}"
            ),
        )

        search_id = str(first_payload.get("search_id", ""))
        job_id = str(first_payload.get("job_id", ""))
        detail = client.get(
            urljoin(f"{origin}/v1/research/searches/", search_id),
            headers=headers,
        )
        detail_payload = detail.json() if detail.status_code == 200 else {}
        _check(
            checks,
            name="research_job_visibility",
            passed=(
                detail.status_code == 200
                and detail_payload.get("search_id") == search_id
                and detail_payload.get("job_id") == job_id
            ),
            detail=f"status={detail.status_code}",
        )

        events = client.get(
            f"{origin}/v1/research/searches/{search_id}/events",
            headers=headers,
        )
        events_payload = events.json() if events.status_code == 200 else {}
        event_items = events_payload.get("items", [])
        _check(
            checks,
            name="research_queue_events",
            passed=events.status_code == 200 and isinstance(event_items, list) and bool(event_items),
            detail=f"status={events.status_code} items={len(event_items) if isinstance(event_items, list) else 0}",
        )

        security_probe = client.get(f"{origin}/v1/health/live")
        missing_headers = [
            header
            for header in REQUIRED_SECURITY_HEADERS
            if header not in {key.lower() for key in security_probe.headers.keys()}
        ]
        _check(
            checks,
            name="security_headers",
            passed=not missing_headers,
            detail=(
                "missing=" + ", ".join(missing_headers)
                if missing_headers
                else "required edge headers present"
            ),
        )

    if client is None:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as owned_client:
            _run(owned_client)
    else:
        _run(client)

    status = "pass" if all(check.passed for check in checks) else "fail"
    return DeploySmokeResult(status=status, base_url=origin, checks=tuple(checks))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        bearer_token = _load_bearer_token(args.bearer_token_env)
        research_payload = DEFAULT_RESEARCH_PAYLOAD.copy()
        if args.research_payload_json is not None:
            research_payload.update(json.load(args.research_payload_json))
        idempotency_key = args.idempotency_key.strip() or f"deploy-smoke-{uuid.uuid4()}"
        result = run_deploy_smoke(
            base_url=args.base_url,
            bearer_token=bearer_token,
            research_payload=research_payload,
            idempotency_key=idempotency_key,
            expected_git_sha=args.expected_git_sha.strip(),
            expected_schema_revision=args.expected_schema_revision.strip(),
            expected_image_digest=args.expected_image_digest.strip(),
            timeout_seconds=args.timeout_seconds,
        )
    except (DeploySmokeError, httpx.HTTPError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
