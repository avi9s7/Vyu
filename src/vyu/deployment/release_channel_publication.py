from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_acceptance import DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL_PUBLICATION_CHANNEL = "local-release-channel-publication"
DEFAULT_RELEASE_CHANNEL_PUBLICATION_STEPS = (
    "Keep the accepted release-channel preparation, handoff inventory, and handoff archive together.",
    "Verify recorded SHA-256 values before any future transfer or publication work starts.",
    "Treat this manifest as a local checklist only; do not sign, upload, transfer, scan, or deploy artifacts until those module boundaries are selected explicitly.",
)
DEFAULT_RELEASE_CHANNEL_PUBLICATION_LIMITS = (
    "no_shell_execution",
    "no_artifact_transfer",
    "no_ci_upload",
    "no_signing_or_kms",
    "no_sbom_generation",
    "no_vulnerability_scanning",
    "no_cloud_deployment",
    "no_production_persistence",
)


class DeploymentReleaseChannelPublicationError(RuntimeError):
    """Raised when release-channel publication metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelPublicationCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelAcceptanceInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    decided_at: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "decided_at": self.decided_at,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelPublicationManifest:
    created_at: str
    publication_channel: str
    acceptance_path: Path
    acceptance: DeploymentReleaseChannelAcceptanceInput
    package: dict[str, object]
    preparation: dict[str, object]
    preparation_artifact_hashes: dict[str, object]
    preparation_archive: dict[str, object]
    preparation_inventory_sha256: str | None
    operator: dict[str, object]
    decision: dict[str, object]
    publication_steps: tuple[str, ...] = DEFAULT_RELEASE_CHANNEL_PUBLICATION_STEPS
    local_only_limits: tuple[str, ...] = DEFAULT_RELEASE_CHANNEL_PUBLICATION_LIMITS
    checks: tuple[DeploymentReleaseChannelPublicationCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "publication_channel": self.publication_channel,
            "acceptance_path": str(self.acceptance_path),
            "acceptance": self.acceptance.to_json(),
            "package": dict(self.package),
            "preparation": dict(self.preparation),
            "preparation_artifact_hashes": dict(self.preparation_artifact_hashes),
            "preparation_archive": dict(self.preparation_archive),
            "preparation_inventory_sha256": self.preparation_inventory_sha256,
            "operator": dict(self.operator),
            "decision": dict(self.decision),
            "publication_steps": list(self.publication_steps),
            "local_only_limits": list(self.local_only_limits),
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_publication_manifest(
    *,
    acceptance_path: Path,
    root: Path = Path("."),
    publication_channel: str = DEFAULT_RELEASE_CHANNEL_PUBLICATION_CHANNEL,
    created_at: str | None = None,
    publication_steps: Sequence[str] = DEFAULT_RELEASE_CHANNEL_PUBLICATION_STEPS,
    local_only_limits: Sequence[str] = DEFAULT_RELEASE_CHANNEL_PUBLICATION_LIMITS,
) -> DeploymentReleaseChannelPublicationManifest:
    """Build a local no-op publication manifest from an accepted release-channel decision."""

    root = Path(root)
    acceptance_path = Path(acceptance_path)
    publication_channel = _normalize_required_text(publication_channel, "publication_channel")
    created_at = _normalize_created_at(created_at)
    normalized_steps = _normalize_text_sequence(publication_steps, "publication_steps")
    normalized_limits = _normalize_text_sequence(local_only_limits, "local_only_limits")

    payload, acceptance = _read_acceptance(acceptance_path, root=root)
    checks = _build_checks(
        acceptance_payload=payload,
        acceptance=acceptance,
        publication_steps=normalized_steps,
        local_only_limits=normalized_limits,
    )

    return DeploymentReleaseChannelPublicationManifest(
        created_at=created_at,
        publication_channel=publication_channel,
        acceptance_path=acceptance_path,
        acceptance=acceptance,
        package=dict(_mapping_value(payload, "package") or {}),
        preparation=dict(_mapping_value(payload, "preparation") or {}),
        preparation_artifact_hashes=dict(_mapping_value(payload, "preparation_artifact_hashes") or {}),
        preparation_archive=dict(_mapping_value(payload, "preparation_archive") or {}),
        preparation_inventory_sha256=_str_or_none(payload.get("preparation_inventory_sha256") if payload else None),
        operator=dict(_mapping_value(payload, "operator") or {}),
        decision=dict(_mapping_value(payload, "decision") or {}),
        publication_steps=normalized_steps,
        local_only_limits=normalized_limits,
        checks=checks,
    )


def write_deployment_release_channel_publication_manifest(
    manifest: DeploymentReleaseChannelPublicationManifest,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    acceptance_payload: Mapping[str, object] | None,
    acceptance: DeploymentReleaseChannelAcceptanceInput,
    publication_steps: tuple[str, ...],
    local_only_limits: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelPublicationCheck, ...]:
    decision = _mapping_value(acceptance_payload, "decision")
    operator = _mapping_value(acceptance_payload, "operator")
    preparation = _mapping_value(acceptance_payload, "preparation")
    archive = _mapping_value(acceptance_payload, "preparation_archive")
    blocking_reasons = _list_value(acceptance_payload, "blocking_reasons")
    return (
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_file_readable",
            acceptance.readable,
            str(acceptance.path),
        ),
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_json_valid",
            acceptance.json_valid,
            "valid" if acceptance.json_valid else "invalid",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_schema_supported",
            acceptance.schema_version == DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA,
            f"schema_version={acceptance.schema_version}",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_status_accepted",
            acceptance.status == "accepted",
            str(acceptance.status),
        ),
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_decision_approves",
            _str_or_none(decision.get("value") if decision else None) == "approve",
            str(decision.get("value") if decision else None),
        ),
        DeploymentReleaseChannelPublicationCheck(
            "acceptance_blocking_reasons_absent",
            len(blocking_reasons) == 0,
            f"count={len(blocking_reasons)}",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "preparation_hash_present",
            bool(_str_or_none(preparation.get("sha256") if preparation else None)),
            "preparation.sha256",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "preparation_status_ready",
            _str_or_none(preparation.get("status") if preparation else None) == "ready",
            str(preparation.get("status") if preparation else None),
        ),
        DeploymentReleaseChannelPublicationCheck(
            "preparation_inventory_sha256_present",
            bool(_str_or_none(acceptance_payload.get("preparation_inventory_sha256") if acceptance_payload else None)),
            "preparation_inventory_sha256",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "preparation_archive_hash_bound",
            _archive_not_requested_or_hash_bound(archive),
            _archive_hash_detail(archive),
        ),
        DeploymentReleaseChannelPublicationCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(acceptance_payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "operator_metadata_present",
            _operator_metadata_present(operator),
            "operator.id,operator.role",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "publication_steps_recorded",
            len(publication_steps) > 0,
            f"count={len(publication_steps)}",
        ),
        DeploymentReleaseChannelPublicationCheck(
            "local_only_limits_recorded",
            len(local_only_limits) > 0,
            f"count={len(local_only_limits)}",
        ),
    )


def _read_acceptance(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelAcceptanceInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelAcceptanceInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelAcceptanceInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelAcceptanceInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            decided_at=None,
        )
    return payload, DeploymentReleaseChannelAcceptanceInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        decided_at=_str_or_none(payload.get("decided_at")),
    )


def _archive_not_requested_or_hash_bound(archive: Mapping[str, object] | None) -> bool:
    if archive is None:
        return False
    if archive.get("requested") is False:
        return True
    return bool(
        _str_or_none(archive.get("sha256"))
        and _str_or_none(archive.get("expected_sha256"))
        and archive.get("hash_matches_expected") is True
    )


def _archive_hash_detail(archive: Mapping[str, object] | None) -> str:
    if archive is None:
        return "archive=missing"
    return "requested={requested},sha256={sha256},expected_sha256={expected},hash_matches_expected={matches}".format(
        requested=archive.get("requested"),
        sha256=archive.get("sha256"),
        expected=archive.get("expected_sha256"),
        matches=archive.get("hash_matches_expected"),
    )


def _package_metadata_present(package: Mapping[str, object] | None) -> bool:
    if package is None:
        return False
    return all(bool(_str_or_none(package.get(key))) for key in ("package_name", "runtime", "handler"))


def _operator_metadata_present(operator: Mapping[str, object] | None) -> bool:
    if operator is None:
        return False
    return bool(_str_or_none(operator.get("id")) and _str_or_none(operator.get("role")))


def _mapping_value(payload: Mapping[str, object] | None, key: str) -> Mapping[str, object] | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, Mapping) else None


def _list_value(payload: Mapping[str, object] | None, key: str) -> list[object]:
    if payload is None:
        return []
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelPublicationError(f"{field_name} cannot be empty.")
    return value


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelPublicationError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelPublicationError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
