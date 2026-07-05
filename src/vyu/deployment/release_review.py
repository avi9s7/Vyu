from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.vyu.deployment.release_evidence import DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA

DEPLOYMENT_RELEASE_REVIEW_SCHEMA = 1
DEPLOYMENT_RELEASE_REVIEW_DECISIONS = ("approve", "block")


class DeploymentReleaseReviewError(RuntimeError):
    """Raised when deployment release review metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseReviewCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseReviewSummaryInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DeploymentReleaseReviewDecision:
    decided_at: str
    summary_path: Path
    summary: DeploymentReleaseReviewSummaryInput
    reviewer_id: str
    reviewer_role: str
    decision: str
    comment: str
    package: dict[str, object]
    summary_artifact_hashes: dict[str, object]
    command_summary: dict[str, object]
    checks: tuple[DeploymentReleaseReviewCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.decision == "approve" and all(check.passed for check in self.checks):
            return "approved"
        return "blocked"

    @property
    def decision_id(self) -> str:
        hash_prefix = (self.summary.sha256 or "missing-summary")[:12]
        return "deployment-release-review-{hash}-{reviewer}-{role}".format(
            hash=hash_prefix,
            reviewer=_safe_token(self.reviewer_id),
            role=_safe_token(self.reviewer_role),
        )

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.decision == "block":
            reasons.append("operator_decision_block")
        for check in self.checks:
            if not check.passed:
                reasons.append(check.name)
        return tuple(sorted(set(reasons)))

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
            "status": self.status,
            "decision_id": self.decision_id,
            "decided_at": self.decided_at,
            "summary_path": str(self.summary_path),
            "summary": self.summary.to_json(),
            "package": dict(self.package),
            "summary_artifact_hashes": dict(self.summary_artifact_hashes),
            "command_summary": dict(self.command_summary),
            "reviewer": {
                "id": self.reviewer_id,
                "role": self.reviewer_role,
            },
            "decision": {
                "value": self.decision,
                "comment": self.comment,
            },
            "blocking_reasons": list(self.blocking_reasons),
            "review_summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_review_decision(
    *,
    summary_path: Path,
    decision: str,
    reviewer_id: str,
    reviewer_role: str,
    comment: str,
    decided_at: str | None = None,
) -> DeploymentReleaseReviewDecision:
    """Build a local deployment release review decision bound to a summary SHA-256."""

    decision = _normalize_required_value("decision", decision)
    if decision not in DEPLOYMENT_RELEASE_REVIEW_DECISIONS:
        raise DeploymentReleaseReviewError(
            f"Unsupported deployment release review decision: {decision}."
        )
    reviewer_id = _normalize_required_value("reviewer_id", reviewer_id)
    reviewer_role = _normalize_required_value("reviewer_role", reviewer_role)
    comment = _normalize_required_value("comment", comment)
    decided_at = _normalize_decided_at(decided_at)

    summary_path = Path(summary_path)
    payload, summary = _read_summary(summary_path)
    checks = _build_checks(
        summary=summary,
        decision=decision,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        comment=comment,
    )

    return DeploymentReleaseReviewDecision(
        decided_at=decided_at,
        summary_path=summary_path,
        summary=summary,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        decision=decision,
        comment=comment,
        package=dict(_mapping_value(payload, "package") or {}),
        summary_artifact_hashes=dict(_mapping_value(payload, "artifact_hashes") or {}),
        command_summary=dict(_mapping_value(payload, "command_summary") or {}),
        checks=checks,
    )


def write_deployment_release_review_decision(
    review: DeploymentReleaseReviewDecision,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(review.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    summary: DeploymentReleaseReviewSummaryInput,
    decision: str,
    reviewer_id: str,
    reviewer_role: str,
    comment: str,
) -> tuple[DeploymentReleaseReviewCheck, ...]:
    return (
        DeploymentReleaseReviewCheck(
            "summary_file_readable",
            summary.readable,
            str(summary.path),
        ),
        DeploymentReleaseReviewCheck(
            "summary_json_valid",
            summary.json_valid,
            "valid" if summary.json_valid else "invalid",
        ),
        DeploymentReleaseReviewCheck(
            "summary_schema_supported",
            summary.schema_version == DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
            f"schema_version={summary.schema_version}",
        ),
        DeploymentReleaseReviewCheck(
            "summary_status_ready",
            summary.status == "ready",
            str(summary.status),
        ),
        DeploymentReleaseReviewCheck(
            "decision_supported",
            decision in DEPLOYMENT_RELEASE_REVIEW_DECISIONS,
            decision,
        ),
        DeploymentReleaseReviewCheck(
            "reviewer_metadata_present",
            bool(reviewer_id and reviewer_role and comment),
            "reviewer_id,reviewer_role,comment",
        ),
        DeploymentReleaseReviewCheck(
            "approve_requires_ready_summary",
            decision != "approve" or summary.status == "ready",
            f"decision={decision},summary_status={summary.status}",
        ),
    )


def _read_summary(path: Path) -> tuple[Mapping[str, object] | None, DeploymentReleaseReviewSummaryInput]:
    path = Path(path)
    sha256 = _sha256(path) if path.is_file() else None
    if not path.is_file():
        return None, DeploymentReleaseReviewSummaryInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
        )
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseReviewSummaryInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseReviewSummaryInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
        )
    return payload, DeploymentReleaseReviewSummaryInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=payload.get("status") if isinstance(payload.get("status"), str) else None,
        created_at=payload.get("created_at") if isinstance(payload.get("created_at"), str) else None,
    )


def _normalize_decided_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseReviewError("decided_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_required_value(name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseReviewError(f"{name} cannot be empty.")
    return value


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip())
    return token.strip("-") or "unknown"


def _mapping_value(payload: Mapping[str, object] | None, key: str) -> Mapping[str, object] | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, Mapping) else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
