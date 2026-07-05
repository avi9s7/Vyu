from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.vyu.deployment.release_channel import DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA = 1
DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_DECISIONS = ("approve", "block")


class DeploymentReleaseChannelAcceptanceError(RuntimeError):
    """Raised when release-channel acceptance metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelAcceptanceCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelPreparationInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    channel: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "channel": self.channel,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelAcceptanceRecord:
    decided_at: str
    preparation_path: Path
    preparation: DeploymentReleaseChannelPreparationInput
    operator_id: str
    operator_role: str
    decision: str
    comment: str
    package: dict[str, object]
    preparation_artifact_hashes: dict[str, object]
    preparation_archive: dict[str, object]
    preparation_inventory_sha256: str | None
    next_actions: tuple[str, ...]
    checks: tuple[DeploymentReleaseChannelAcceptanceCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.decision == "approve" and all(check.passed for check in self.checks):
            return "accepted"
        return "blocked"

    @property
    def acceptance_id(self) -> str:
        hash_prefix = (self.preparation.sha256 or "missing-preparation")[:12]
        return "deployment-release-channel-acceptance-{hash}-{operator}-{role}".format(
            hash=hash_prefix,
            operator=_safe_token(self.operator_id),
            role=_safe_token(self.operator_role),
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
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_SCHEMA,
            "status": self.status,
            "acceptance_id": self.acceptance_id,
            "decided_at": self.decided_at,
            "preparation_path": str(self.preparation_path),
            "preparation": self.preparation.to_json(),
            "package": dict(self.package),
            "preparation_artifact_hashes": dict(self.preparation_artifact_hashes),
            "preparation_archive": dict(self.preparation_archive),
            "preparation_inventory_sha256": self.preparation_inventory_sha256,
            "next_actions": list(self.next_actions),
            "operator": {"id": self.operator_id, "role": self.operator_role},
            "decision": {"value": self.decision, "comment": self.comment},
            "blocking_reasons": list(self.blocking_reasons),
            "acceptance_summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_acceptance_record(
    *,
    preparation_path: Path,
    decision: str,
    operator_id: str,
    operator_role: str,
    comment: str,
    decided_at: str | None = None,
    root: Path = Path("."),
) -> DeploymentReleaseChannelAcceptanceRecord:
    """Build a local operator acceptance record bound to a release-channel preparation SHA-256."""

    decision = _normalize_required_value("decision", decision)
    if decision not in DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_DECISIONS:
        raise DeploymentReleaseChannelAcceptanceError(
            f"Unsupported deployment release-channel acceptance decision: {decision}."
        )
    operator_id = _normalize_required_value("operator_id", operator_id)
    operator_role = _normalize_required_value("operator_role", operator_role)
    comment = _normalize_required_value("comment", comment)
    decided_at = _normalize_decided_at(decided_at)

    root = Path(root)
    preparation_path = Path(preparation_path)
    payload, preparation = _read_preparation(preparation_path, root=root)
    checks = _build_checks(
        preparation_payload=payload,
        preparation=preparation,
        decision=decision,
        operator_id=operator_id,
        operator_role=operator_role,
        comment=comment,
    )

    return DeploymentReleaseChannelAcceptanceRecord(
        decided_at=decided_at,
        preparation_path=preparation_path,
        preparation=preparation,
        operator_id=operator_id,
        operator_role=operator_role,
        decision=decision,
        comment=comment,
        package=dict(_mapping_value(payload, "package") or {}),
        preparation_artifact_hashes=dict(_mapping_value(payload, "artifact_hashes") or {}),
        preparation_archive=dict(_mapping_value(payload, "archive") or {}),
        preparation_inventory_sha256=_str_or_none(payload.get("inventory_sha256") if payload else None),
        next_actions=tuple(_string_list_value(payload, "next_actions")),
        checks=checks,
    )


def write_deployment_release_channel_acceptance_record(
    record: DeploymentReleaseChannelAcceptanceRecord,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    preparation_payload: Mapping[str, object] | None,
    preparation: DeploymentReleaseChannelPreparationInput,
    decision: str,
    operator_id: str,
    operator_role: str,
    comment: str,
) -> tuple[DeploymentReleaseChannelAcceptanceCheck, ...]:
    preparation_checks = _list_value(preparation_payload, "checks")
    failed_preparation_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in preparation_checks
        if isinstance(check, Mapping) and check.get("passed") is not True
    ]
    archive = _mapping_value(preparation_payload, "archive")
    archive_requested = _bool_value(archive.get("requested")) if archive else False
    archive_hash_bound = _archive_hash_bound(archive)
    return (
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_file_readable",
            preparation.readable,
            str(preparation.path),
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_json_valid",
            preparation.json_valid,
            "valid" if preparation.json_valid else "invalid",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_schema_supported",
            preparation.schema_version == DEPLOYMENT_RELEASE_CHANNEL_PREPARATION_SCHEMA,
            f"schema_version={preparation.schema_version}",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_status_ready",
            preparation.status == "ready",
            str(preparation.status),
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_checks_passed",
            len(preparation_checks) > 0 and len(failed_preparation_checks) == 0,
            "failed=" + ",".join(failed_preparation_checks) if failed_preparation_checks else f"checks={len(preparation_checks)}",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_inventory_sha256_present",
            bool(_str_or_none(preparation_payload.get("inventory_sha256") if preparation_payload else None)),
            "inventory_sha256",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "preparation_archive_hash_bound",
            (not archive_requested) or archive_hash_bound,
            _archive_hash_detail(archive),
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(preparation_payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "next_actions_present",
            len(_string_list_value(preparation_payload, "next_actions")) > 0,
            f"count={len(_string_list_value(preparation_payload, 'next_actions'))}",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "decision_supported",
            decision in DEPLOYMENT_RELEASE_CHANNEL_ACCEPTANCE_DECISIONS,
            decision,
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "operator_metadata_present",
            bool(operator_id and operator_role and comment),
            "operator_id,operator_role,comment",
        ),
        DeploymentReleaseChannelAcceptanceCheck(
            "approve_requires_ready_preparation",
            decision != "approve" or preparation.status == "ready",
            f"decision={decision},preparation_status={preparation.status}",
        ),
    )


def _read_preparation(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelPreparationInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelPreparationInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            channel=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelPreparationInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            channel=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelPreparationInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            channel=None,
        )
    return payload, DeploymentReleaseChannelPreparationInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        channel=_str_or_none(payload.get("channel")),
    )


def _archive_hash_bound(archive: Mapping[str, object] | None) -> bool:
    if archive is None:
        return False
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


def _string_list_value(payload: Mapping[str, object] | None, key: str) -> list[str]:
    return [value for value in _list_value(payload, key) if isinstance(value, str)]


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _bool_value(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_decided_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelAcceptanceError("decided_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_required_value(name: str, value: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelAcceptanceError(f"{name} cannot be empty.")
    return value


def _safe_token(value: str) -> str:
    token = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip())
    return token.strip("-") or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
