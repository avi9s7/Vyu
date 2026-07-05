from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.vyu.deployment.release_evidence import DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA
from src.vyu.deployment.release_review import DEPLOYMENT_RELEASE_REVIEW_SCHEMA

DEPLOYMENT_RELEASE_HANDOFF_SCHEMA = 1


class DeploymentReleaseHandoffError(RuntimeError):
    """Raised when deployment release handoff metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseHandoffCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseHandoffInput:
    name: str
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True)
class DeploymentReleaseHandoffBundle:
    created_at: str
    summary_path: Path
    review_path: Path
    inputs: dict[str, DeploymentReleaseHandoffInput]
    package: dict[str, object]
    artifact_hashes: dict[str, object]
    command_summary: dict[str, object]
    reviewer: dict[str, object]
    decision: dict[str, object]
    checks: tuple[DeploymentReleaseHandoffCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_HANDOFF_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "summary_path": str(self.summary_path),
            "review_path": str(self.review_path),
            "inputs": {name: item.to_json() for name, item in self.inputs.items()},
            "package": dict(self.package),
            "artifact_hashes": dict(self.artifact_hashes),
            "command_summary": dict(self.command_summary),
            "reviewer": dict(self.reviewer),
            "decision": dict(self.decision),
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_handoff_bundle(
    *,
    summary_path: Path,
    review_path: Path,
    created_at: str | None = None,
) -> DeploymentReleaseHandoffBundle:
    """Build a local deployment release handoff manifest from summary and review records."""

    created_at = _normalize_created_at(created_at)
    summary_path = Path(summary_path)
    review_path = Path(review_path)

    summary_payload, summary_input = _read_input("release_evidence_summary", summary_path)
    review_payload, review_input = _read_input("release_review_decision", review_path)
    inputs = {summary_input.name: summary_input, review_input.name: review_input}

    checks = _build_checks(
        summary_payload=summary_payload,
        review_payload=review_payload,
        summary_input=summary_input,
        review_input=review_input,
        summary_path=summary_path,
    )

    return DeploymentReleaseHandoffBundle(
        created_at=created_at,
        summary_path=summary_path,
        review_path=review_path,
        inputs=inputs,
        package=_handoff_package(summary_payload, review_payload),
        artifact_hashes=_handoff_artifact_hashes(
            summary_payload=summary_payload,
            review_payload=review_payload,
            summary_sha256=summary_input.sha256,
            review_sha256=review_input.sha256,
        ),
        command_summary=dict(_mapping_value(summary_payload, "command_summary") or {}),
        reviewer=dict(_mapping_value(review_payload, "reviewer") or {}),
        decision=dict(_mapping_value(review_payload, "decision") or {}),
        checks=checks,
    )


def write_deployment_release_handoff_bundle(
    bundle: DeploymentReleaseHandoffBundle,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(bundle.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    summary_payload: Mapping[str, object] | None,
    review_payload: Mapping[str, object] | None,
    summary_input: DeploymentReleaseHandoffInput,
    review_input: DeploymentReleaseHandoffInput,
    summary_path: Path,
) -> tuple[DeploymentReleaseHandoffCheck, ...]:
    return (
        DeploymentReleaseHandoffCheck(
            "input_files_readable",
            summary_input.readable and review_input.readable,
            _missing_input_detail(summary_input, review_input),
        ),
        DeploymentReleaseHandoffCheck(
            "input_json_valid",
            summary_input.json_valid and review_input.json_valid,
            _invalid_json_detail(summary_input, review_input),
        ),
        DeploymentReleaseHandoffCheck(
            "summary_schema_supported",
            summary_input.schema_version == DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
            f"schema_version={summary_input.schema_version}",
        ),
        DeploymentReleaseHandoffCheck(
            "review_schema_supported",
            review_input.schema_version == DEPLOYMENT_RELEASE_REVIEW_SCHEMA,
            f"schema_version={review_input.schema_version}",
        ),
        DeploymentReleaseHandoffCheck(
            "summary_status_ready",
            summary_input.status == "ready",
            str(summary_input.status),
        ),
        DeploymentReleaseHandoffCheck(
            "review_status_approved",
            review_input.status == "approved",
            str(review_input.status),
        ),
        DeploymentReleaseHandoffCheck(
            "review_summary_hash_matches_input",
            _review_summary_hash_matches(review_payload, summary_input.sha256),
            str(summary_input.sha256),
        ),
        DeploymentReleaseHandoffCheck(
            "review_summary_path_matches_input",
            _review_summary_path_matches(review_payload, summary_path),
            str(summary_path),
        ),
        DeploymentReleaseHandoffCheck(
            "package_metadata_matches_review",
            _package_metadata_matches(summary_payload, review_payload),
            "package",
        ),
        DeploymentReleaseHandoffCheck(
            "artifact_hashes_match_review",
            _artifact_hashes_match(summary_payload, review_payload),
            "summary_artifact_hashes",
        ),
        DeploymentReleaseHandoffCheck(
            "review_decision_approves",
            _review_decision_value(review_payload) == "approve",
            str(_review_decision_value(review_payload)),
        ),
        DeploymentReleaseHandoffCheck(
            "review_blocking_reasons_absent",
            _review_blocking_reasons_absent(review_payload),
            "blocking_reasons",
        ),
        DeploymentReleaseHandoffCheck(
            "reviewer_metadata_present",
            _reviewer_metadata_present(review_payload),
            "reviewer.id,reviewer.role",
        ),
    )


def _read_input(name: str, path: Path) -> tuple[Mapping[str, object] | None, DeploymentReleaseHandoffInput]:
    path = Path(path)
    sha256 = _sha256(path) if path.is_file() else None
    if not path.is_file():
        return None, DeploymentReleaseHandoffInput(
            name=name,
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
        )
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseHandoffInput(
            name=name,
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseHandoffInput(
            name=name,
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
        )
    return payload, DeploymentReleaseHandoffInput(
        name=name,
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=payload.get("status") if isinstance(payload.get("status"), str) else None,
    )


def _handoff_package(
    summary_payload: Mapping[str, object] | None,
    review_payload: Mapping[str, object] | None,
) -> dict[str, object]:
    summary_package = _mapping_value(summary_payload, "package")
    if summary_package is not None:
        return dict(summary_package)
    return dict(_mapping_value(review_payload, "package") or {})


def _handoff_artifact_hashes(
    *,
    summary_payload: Mapping[str, object] | None,
    review_payload: Mapping[str, object] | None,
    summary_sha256: str | None,
    review_sha256: str | None,
) -> dict[str, object]:
    hashes: dict[str, object] = {
        "release_evidence_summary_sha256": summary_sha256,
        "release_review_decision_sha256": review_sha256,
    }
    hashes.update(dict(_mapping_value(summary_payload, "artifact_hashes") or {}))
    review_hashes = _mapping_value(review_payload, "summary_artifact_hashes") or {}
    if review_hashes:
        hashes["review_summary_artifact_hashes"] = dict(review_hashes)
    return hashes


def _review_summary_hash_matches(
    review_payload: Mapping[str, object] | None,
    summary_sha256: str | None,
) -> bool:
    summary = _mapping_value(review_payload, "summary")
    if summary is None or summary_sha256 is None:
        return False
    return _str_or_none(summary.get("sha256")) == summary_sha256


def _review_summary_path_matches(
    review_payload: Mapping[str, object] | None,
    summary_path: Path,
) -> bool:
    summary = _mapping_value(review_payload, "summary")
    paths = {
        _str_or_none(review_payload.get("summary_path")) if review_payload else None,
        _str_or_none(summary.get("path")) if summary else None,
    }
    return str(summary_path) in paths


def _package_metadata_matches(
    summary_payload: Mapping[str, object] | None,
    review_payload: Mapping[str, object] | None,
) -> bool:
    summary_package = _mapping_value(summary_payload, "package")
    review_package = _mapping_value(review_payload, "package")
    return summary_package is not None and summary_package == review_package


def _artifact_hashes_match(
    summary_payload: Mapping[str, object] | None,
    review_payload: Mapping[str, object] | None,
) -> bool:
    summary_hashes = _mapping_value(summary_payload, "artifact_hashes")
    review_hashes = _mapping_value(review_payload, "summary_artifact_hashes")
    return summary_hashes is not None and summary_hashes == review_hashes


def _review_decision_value(review_payload: Mapping[str, object] | None) -> str | None:
    decision = _mapping_value(review_payload, "decision")
    return _str_or_none(decision.get("value")) if decision is not None else None


def _review_blocking_reasons_absent(review_payload: Mapping[str, object] | None) -> bool:
    if review_payload is None:
        return False
    reasons = review_payload.get("blocking_reasons")
    return isinstance(reasons, list) and len(reasons) == 0


def _reviewer_metadata_present(review_payload: Mapping[str, object] | None) -> bool:
    reviewer = _mapping_value(review_payload, "reviewer")
    if reviewer is None:
        return False
    reviewer_id = _str_or_none(reviewer.get("id"))
    reviewer_role = _str_or_none(reviewer.get("role"))
    return bool(reviewer_id and reviewer_id.strip() and reviewer_role and reviewer_role.strip())


def _missing_input_detail(*inputs: DeploymentReleaseHandoffInput) -> str:
    missing = [item.name for item in inputs if not item.readable]
    return "missing=" + ",".join(missing) if missing else "complete"


def _invalid_json_detail(*inputs: DeploymentReleaseHandoffInput) -> str:
    invalid = [item.name for item in inputs if item.readable and not item.json_valid]
    return "invalid=" + ",".join(invalid) if invalid else "complete"


def _mapping_value(payload: Mapping[str, object] | None, key: str) -> Mapping[str, object] | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, Mapping) else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseHandoffError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
