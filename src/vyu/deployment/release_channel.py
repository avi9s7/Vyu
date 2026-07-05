from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_handoff_archive import DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL = "local-release-channel"
DEFAULT_RELEASE_CHANNEL_NEXT_ACTIONS = (
    "Keep the handoff inventory and archive together when transferring release evidence.",
    "Verify recorded SHA-256 values after any transfer before review or deployment work continues.",
    "Do not add signing, CI upload, cloud deployment, SBOM, vulnerability scanning, or production persistence until those module boundaries are selected explicitly.",
)


class DeploymentReleaseChannelPreparationError(RuntimeError):
    """Raised when deployment release-channel preparation metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelPreparationCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelArchiveSummary:
    requested: bool
    path: Path | None
    sha256: str | None
    expected_sha256: str | None

    @property
    def hash_matches_expected(self) -> bool:
        return self.expected_sha256 is None or self.sha256 == self.expected_sha256

    def to_json(self) -> dict[str, object]:
        return {
            "requested": self.requested,
            "path": str(self.path) if self.path is not None else None,
            "sha256": self.sha256,
            "expected_sha256": self.expected_sha256,
            "hash_matches_expected": self.hash_matches_expected,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelPreparation:
    created_at: str
    channel: str
    inventory_path: Path
    inventory_sha256: str | None
    archive: DeploymentReleaseChannelArchiveSummary
    package: dict[str, object]
    inventory_summary: dict[str, object]
    artifact_hashes: dict[str, object]
    next_actions: tuple[str, ...] = DEFAULT_RELEASE_CHANNEL_NEXT_ACTIONS
    checks: tuple[DeploymentReleaseChannelPreparationCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "channel": self.channel,
            "inventory_path": str(self.inventory_path),
            "inventory_sha256": self.inventory_sha256,
            "archive": self.archive.to_json(),
            "package": dict(self.package),
            "inventory_summary": dict(self.inventory_summary),
            "artifact_hashes": dict(self.artifact_hashes),
            "next_actions": list(self.next_actions),
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_preparation(
    *,
    inventory_path: Path,
    archive_path: Path | None = None,
    root: Path = Path("."),
    channel: str = DEFAULT_RELEASE_CHANNEL,
    created_at: str | None = None,
    next_actions: Sequence[str] = DEFAULT_RELEASE_CHANNEL_NEXT_ACTIONS,
) -> DeploymentReleaseChannelPreparation:
    """Build a local release-channel preparation manifest from a handoff archive inventory."""

    root = Path(root)
    inventory_path = Path(inventory_path)
    created_at = _normalize_created_at(created_at)
    channel = _normalize_required_text(channel, "channel")
    normalized_next_actions = _normalize_next_actions(next_actions)

    inventory_payload, inventory_readable, inventory_json_valid = _read_json_mapping(inventory_path, root=root)
    inventory_sha256 = _sha256(_absolute_path(inventory_path, root=root)) if inventory_readable else None

    archive_info = _mapping_value(inventory_payload, "archive")
    inventory_archive_requested = _bool_value(archive_info.get("requested")) if archive_info else False
    inventory_archive_path = _str_or_none(archive_info.get("path")) if archive_info else None
    expected_archive_sha256 = _str_or_none(archive_info.get("sha256")) if archive_info else None

    resolved_archive_path = Path(archive_path) if archive_path is not None else (Path(inventory_archive_path) if inventory_archive_path else None)
    archive_requested = inventory_archive_requested or resolved_archive_path is not None
    archive_sha256 = _sha256(_absolute_path(resolved_archive_path, root=root)) if resolved_archive_path is not None and _absolute_path(resolved_archive_path, root=root).is_file() else None
    archive = DeploymentReleaseChannelArchiveSummary(
        requested=archive_requested,
        path=resolved_archive_path,
        sha256=archive_sha256,
        expected_sha256=expected_archive_sha256,
    )

    artifact_hashes = _release_artifact_hashes(
        inventory_payload,
        inventory_sha256=inventory_sha256,
        archive_sha256=archive_sha256,
    )
    checks = _build_checks(
        inventory_payload=inventory_payload,
        inventory_readable=inventory_readable,
        inventory_json_valid=inventory_json_valid,
        archive=archive,
        inventory_archive_requested=inventory_archive_requested,
        package=_mapping_value(inventory_payload, "package"),
        next_actions=normalized_next_actions,
    )

    return DeploymentReleaseChannelPreparation(
        created_at=created_at,
        channel=channel,
        inventory_path=inventory_path,
        inventory_sha256=inventory_sha256,
        archive=archive,
        package=dict(_mapping_value(inventory_payload, "package") or {}),
        inventory_summary=dict(_mapping_value(inventory_payload, "summary") or {}),
        artifact_hashes=artifact_hashes,
        next_actions=normalized_next_actions,
        checks=checks,
    )


def write_deployment_release_channel_preparation(
    preparation: DeploymentReleaseChannelPreparation,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(preparation.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    inventory_payload: Mapping[str, object] | None,
    inventory_readable: bool,
    inventory_json_valid: bool,
    archive: DeploymentReleaseChannelArchiveSummary,
    inventory_archive_requested: bool,
    package: Mapping[str, object] | None,
    next_actions: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelPreparationCheck, ...]:
    artifacts = _list_value(inventory_payload, "artifacts")
    inventory_checks = _list_value(inventory_payload, "checks")
    failed_inventory_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in inventory_checks
        if isinstance(check, Mapping) and check.get("passed") is not True
    ]
    artifact_hash_failures = [
        _str_or_none(artifact.get("name")) or "unnamed_artifact"
        for artifact in artifacts
        if isinstance(artifact, Mapping) and artifact.get("hash_matches_expected") is not True
    ]
    included_count = _summary_int(inventory_payload, "included_artifact_count")
    return (
        DeploymentReleaseChannelPreparationCheck(
            "inventory_file_readable",
            inventory_readable,
            "deployment_release_handoff_inventory",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_json_valid",
            inventory_json_valid,
            "deployment_release_handoff_inventory",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_schema_supported",
            _optional_int(inventory_payload.get("schema_version") if inventory_payload else None)
            == DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA,
            f"schema_version={inventory_payload.get('schema_version') if inventory_payload else None}",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_status_ready",
            _str_or_none(inventory_payload.get("status") if inventory_payload else None) == "ready",
            str(inventory_payload.get("status") if inventory_payload else None),
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_included_artifacts_present",
            included_count is not None and included_count > 0,
            f"included_artifact_count={included_count}",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_checks_passed",
            len(failed_inventory_checks) == 0 and len(inventory_checks) > 0,
            "failed=" + ",".join(failed_inventory_checks) if failed_inventory_checks else f"checks={len(inventory_checks)}",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "inventory_artifact_hashes_match",
            len(artifact_hash_failures) == 0 and len(artifacts) > 0,
            "failed=" + ",".join(artifact_hash_failures) if artifact_hash_failures else f"artifacts={len(artifacts)}",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "archive_requirement_consistent",
            (not inventory_archive_requested) or archive.path is not None,
            "requested=" + str(inventory_archive_requested),
        ),
        DeploymentReleaseChannelPreparationCheck(
            "archive_file_exists",
            (not archive.requested) or archive.sha256 is not None,
            str(archive.path) if archive.path is not None else "not_requested",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "archive_hash_matches_inventory",
            (not archive.requested) or archive.hash_matches_expected,
            str(archive.expected_sha256),
        ),
        DeploymentReleaseChannelPreparationCheck(
            "package_metadata_present",
            _package_metadata_present(package),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelPreparationCheck(
            "next_actions_recorded",
            len(next_actions) > 0,
            f"count={len(next_actions)}",
        ),
    )


def _release_artifact_hashes(
    inventory_payload: Mapping[str, object] | None,
    *,
    inventory_sha256: str | None,
    archive_sha256: str | None,
) -> dict[str, object]:
    hashes: dict[str, object] = {
        "handoff_inventory_sha256": inventory_sha256,
        "handoff_archive_sha256": archive_sha256,
    }
    hashes.update(dict(_mapping_value(inventory_payload, "artifact_hashes") or {}))
    return hashes


def _read_json_mapping(path: Path, *, root: Path) -> tuple[Mapping[str, object] | None, bool, bool]:
    file_path = _absolute_path(path, root=root)
    if not file_path.is_file():
        return None, False, False
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, True, False
    if not isinstance(payload, Mapping):
        return None, True, False
    return payload, True, True


def _absolute_path(path: Path | None, *, root: Path) -> Path:
    if path is None:
        raise DeploymentReleaseChannelPreparationError("path cannot be None.")
    return path if path.is_absolute() else root / path


def _package_metadata_present(package: Mapping[str, object] | None) -> bool:
    if package is None:
        return False
    return all(bool(_str_or_none(package.get(key))) for key in ("package_name", "runtime", "handler"))


def _summary_int(payload: Mapping[str, object] | None, key: str) -> int | None:
    summary = _mapping_value(payload, "summary")
    if summary is None:
        return None
    value = summary.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


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


def _bool_value(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelPreparationError(f"{field_name} cannot be empty.")
    return value


def _normalize_next_actions(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelPreparationError("at least one next action is required.")
    return normalized


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelPreparationError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
