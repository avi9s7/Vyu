from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_export import DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL_TARGET_READINESS_NAME = "local-release-channel-target-readiness"
DEFAULT_RELEASE_CHANNEL_CANDIDATE_TARGET_FAMILIES = (
    "serverless_function",
    "container_service",
    "managed_job_or_worker",
)
DEFAULT_RELEASE_CHANNEL_TARGET_HANDOFF_CHECKLIST = (
    "Choose one deployment target family in a future module before adding provider-specific configuration.",
    "Keep the export summary, evidence index, handoff archive, and package archive together for target evaluation.",
    "Verify security, identity, networking, and observability requirements before any provider-specific implementation.",
    "Do not transfer, sign, upload, scan, persist to production storage, or deploy artifacts from this local readiness note.",
)


class DeploymentReleaseChannelTargetReadinessError(RuntimeError):
    """Raised when release-channel target-readiness metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetReadinessCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelExportSummaryInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    summary_name: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "summary_name": self.summary_name,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelTargetReadinessNote:
    created_at: str
    readiness_name: str
    export_summary_path: Path
    export_summary: DeploymentReleaseChannelExportSummaryInput
    target_selection_scope: str
    selected_target_provider: str | None
    provider_configuration: dict[str, object]
    candidate_target_families: tuple[str, ...]
    handoff_checklist: tuple[str, ...]
    package: dict[str, object]
    operator: dict[str, object]
    evidence_hashes: dict[str, object]
    evidence_counts: dict[str, object]
    export_review_checklist: tuple[str, ...]
    export_blocking_reasons: tuple[str, ...]
    local_only_limits: tuple[str, ...]
    checks: tuple[DeploymentReleaseChannelTargetReadinessCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    @property
    def blocking_reasons(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "readiness_name": self.readiness_name,
            "export_summary_path": str(self.export_summary_path),
            "export_summary": self.export_summary.to_json(),
            "target_selection_scope": self.target_selection_scope,
            "selected_target_provider": self.selected_target_provider,
            "provider_configuration": dict(self.provider_configuration),
            "candidate_target_families": list(self.candidate_target_families),
            "handoff_checklist": list(self.handoff_checklist),
            "package": dict(self.package),
            "operator": dict(self.operator),
            "evidence_hashes": dict(self.evidence_hashes),
            "evidence_counts": dict(self.evidence_counts),
            "export_review_checklist": list(self.export_review_checklist),
            "export_blocking_reasons": list(self.export_blocking_reasons),
            "local_only_limits": list(self.local_only_limits),
            "blocking_reasons": list(self.blocking_reasons),
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "candidate_target_family_count": len(self.candidate_target_families),
                "handoff_checklist_item_count": len(self.handoff_checklist),
                "required_evidence_item_count": int(_number_value(self.evidence_counts, "required_evidence_item_count") or 0),
                "present_required_evidence_item_count": int(_number_value(self.evidence_counts, "present_required_evidence_item_count") or 0),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_target_readiness_note(
    *,
    export_summary_path: Path,
    root: Path = Path("."),
    readiness_name: str = DEFAULT_RELEASE_CHANNEL_TARGET_READINESS_NAME,
    created_at: str | None = None,
    candidate_target_families: Sequence[str] = DEFAULT_RELEASE_CHANNEL_CANDIDATE_TARGET_FAMILIES,
    handoff_checklist: Sequence[str] = DEFAULT_RELEASE_CHANNEL_TARGET_HANDOFF_CHECKLIST,
) -> DeploymentReleaseChannelTargetReadinessNote:
    """Build a local target-selection readiness note from a ready release-channel export summary."""

    root = Path(root)
    export_summary_path = Path(export_summary_path)
    readiness_name = _normalize_required_text(readiness_name, "readiness_name")
    created_at = _normalize_created_at(created_at)
    normalized_target_families = _normalize_text_sequence(candidate_target_families, "candidate_target_families")
    normalized_handoff_checklist = _normalize_text_sequence(handoff_checklist, "handoff_checklist")

    payload, export_summary = _read_export_summary(export_summary_path, root=root)
    evidence_hashes = dict(_mapping_value(payload, "evidence_hashes") or {})
    evidence_counts = dict(_mapping_value(payload, "summary") or {})
    checks = _build_checks(
        payload=payload,
        export_summary=export_summary,
        evidence_hashes=evidence_hashes,
        evidence_counts=evidence_counts,
        candidate_target_families=normalized_target_families,
        handoff_checklist=normalized_handoff_checklist,
    )

    return DeploymentReleaseChannelTargetReadinessNote(
        created_at=created_at,
        readiness_name=readiness_name,
        export_summary_path=export_summary_path,
        export_summary=export_summary,
        target_selection_scope="local_target_family_review_only",
        selected_target_provider=None,
        provider_configuration={},
        candidate_target_families=normalized_target_families,
        handoff_checklist=normalized_handoff_checklist,
        package=dict(_mapping_value(payload, "package") or {}),
        operator=dict(_mapping_value(payload, "operator") or {}),
        evidence_hashes=evidence_hashes,
        evidence_counts=evidence_counts,
        export_review_checklist=tuple(_string_list_value(payload, "review_checklist")),
        export_blocking_reasons=tuple(_string_list_value(payload, "blocking_reasons")),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        checks=checks,
    )


def write_deployment_release_channel_target_readiness_note(
    note: DeploymentReleaseChannelTargetReadinessNote,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(note.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    payload: Mapping[str, object] | None,
    export_summary: DeploymentReleaseChannelExportSummaryInput,
    evidence_hashes: Mapping[str, object],
    evidence_counts: Mapping[str, object],
    candidate_target_families: tuple[str, ...],
    handoff_checklist: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelTargetReadinessCheck, ...]:
    export_checks = _list_of_mappings(payload, "checks")
    failed_export_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in export_checks
        if check.get("passed") is not True
    ]
    export_blocking_reasons = _string_list_value(payload, "blocking_reasons")
    required_total = _number_value(evidence_counts, "required_evidence_item_count")
    required_present = _number_value(evidence_counts, "present_required_evidence_item_count")
    evidence_index_sha = _nested_str(payload, "evidence_index", "sha256")
    evidence_index_hash = _str_or_none(evidence_hashes.get("evidence_index_sha256"))
    return (
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_summary_file_readable",
            export_summary.readable,
            str(export_summary.path),
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_summary_json_valid",
            export_summary.json_valid,
            "valid" if export_summary.json_valid else "invalid",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_summary_schema_supported",
            export_summary.schema_version == DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA,
            f"schema_version={export_summary.schema_version}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_summary_status_ready",
            export_summary.status == "ready",
            str(export_summary.status),
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_summary_checks_passed",
            len(export_checks) > 0 and len(failed_export_checks) == 0,
            "failed=" + ",".join(failed_export_checks) if failed_export_checks else f"checks={len(export_checks)}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "export_blocking_reasons_absent",
            len(export_blocking_reasons) == 0,
            f"count={len(export_blocking_reasons)}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "evidence_index_sha256_present",
            bool(evidence_index_sha and evidence_index_hash),
            "evidence_index.sha256,evidence_hashes.evidence_index_sha256",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "evidence_index_hash_bound",
            bool(evidence_index_sha and evidence_index_hash and evidence_index_sha == evidence_index_hash),
            "evidence_index.sha256 == evidence_hashes.evidence_index_sha256",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "required_evidence_counts_complete",
            isinstance(required_total, int) and required_total > 0 and required_total == required_present,
            f"present={required_present} required={required_total}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "review_checklist_present",
            len(_string_list_value(payload, "review_checklist")) > 0,
            f"count={len(_string_list_value(payload, 'review_checklist'))}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "operator_metadata_present",
            _operator_metadata_present(_mapping_value(payload, "operator")),
            "operator.id,operator.role",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "local_only_limits_present",
            len(_string_list_value(payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "candidate_target_families_recorded",
            len(candidate_target_families) > 0,
            f"count={len(candidate_target_families)}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "no_target_provider_selected",
            True,
            "selected_target_provider=None",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "no_provider_configuration_recorded",
            True,
            "provider_configuration={}",
        ),
        DeploymentReleaseChannelTargetReadinessCheck(
            "handoff_checklist_present",
            len(handoff_checklist) > 0,
            f"count={len(handoff_checklist)}",
        ),
    )


def _read_export_summary(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelExportSummaryInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelExportSummaryInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            summary_name=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelExportSummaryInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            summary_name=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelExportSummaryInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            summary_name=None,
        )
    return payload, DeploymentReleaseChannelExportSummaryInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        summary_name=_str_or_none(payload.get("summary_name")),
    )


def _nested_str(payload: Mapping[str, object] | None, parent: str, key: str) -> str | None:
    value = _mapping_value(payload, parent)
    return _str_or_none(value.get(key) if value else None)


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


def _list_of_mappings(payload: Mapping[str, object] | None, key: str) -> tuple[Mapping[str, object], ...]:
    return tuple(value for value in _list_value(payload, key) if isinstance(value, Mapping))


def _string_list_value(payload: Mapping[str, object] | None, key: str) -> list[str]:
    return [value for value in _list_value(payload, key) if isinstance(value, str)]


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _number_value(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelTargetReadinessError(f"{field_name} cannot be empty.")
    return value


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelTargetReadinessError(f"{field_name} must include at least one item.")
    return normalized


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelTargetReadinessError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
