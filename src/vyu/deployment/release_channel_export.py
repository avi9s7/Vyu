from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.release_channel_evidence import DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL_EXPORT_SUMMARY_NAME = "local-release-channel-evidence-export-summary"
DEFAULT_RELEASE_CHANNEL_REVIEW_CHECKLIST = (
    "Verify the evidence index SHA-256 before using this summary for any later handoff work.",
    "Confirm every required release-channel evidence item is present and hash-bound where expected.",
    "Confirm publication steps and local-only limits are acceptable for the selected future release boundary.",
    "Do not transfer, sign, upload, scan, persist to production storage, or deploy artifacts from this local summary.",
)


class DeploymentReleaseChannelExportSummaryError(RuntimeError):
    """Raised when release-channel export-summary metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelExportCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelEvidenceIndexInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    index_name: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "index_name": self.index_name,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelExportSummary:
    created_at: str
    summary_name: str
    evidence_index_path: Path
    evidence_index: DeploymentReleaseChannelEvidenceIndexInput
    publication: dict[str, object]
    package: dict[str, object]
    operator: dict[str, object]
    decision: dict[str, object]
    evidence_hashes: dict[str, object]
    evidence_counts: dict[str, object]
    required_evidence_items: tuple[dict[str, object], ...]
    optional_evidence_items: tuple[dict[str, object], ...]
    publication_steps: tuple[str, ...]
    local_only_limits: tuple[str, ...]
    review_checklist: tuple[str, ...] = DEFAULT_RELEASE_CHANNEL_REVIEW_CHECKLIST
    checks: tuple[DeploymentReleaseChannelExportCheck, ...] = field(default_factory=tuple)

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
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_EXPORT_SUMMARY_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "summary_name": self.summary_name,
            "evidence_index_path": str(self.evidence_index_path),
            "evidence_index": self.evidence_index.to_json(),
            "publication": dict(self.publication),
            "package": dict(self.package),
            "operator": dict(self.operator),
            "decision": dict(self.decision),
            "evidence_hashes": dict(self.evidence_hashes),
            "evidence_counts": dict(self.evidence_counts),
            "required_evidence_items": [dict(item) for item in self.required_evidence_items],
            "optional_evidence_items": [dict(item) for item in self.optional_evidence_items],
            "publication_steps": list(self.publication_steps),
            "local_only_limits": list(self.local_only_limits),
            "review_checklist": list(self.review_checklist),
            "blocking_reasons": list(self.blocking_reasons),
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "required_evidence_item_count": int(_number_value(self.evidence_counts, "required_evidence_item_count") or 0),
                "present_required_evidence_item_count": int(_number_value(self.evidence_counts, "present_required_evidence_item_count") or 0),
                "review_checklist_item_count": len(self.review_checklist),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_export_summary(
    *,
    evidence_index_path: Path,
    root: Path = Path("."),
    summary_name: str = DEFAULT_RELEASE_CHANNEL_EXPORT_SUMMARY_NAME,
    created_at: str | None = None,
    review_checklist: Sequence[str] = DEFAULT_RELEASE_CHANNEL_REVIEW_CHECKLIST,
) -> DeploymentReleaseChannelExportSummary:
    """Build a local operator review/export summary from a ready release-channel evidence index."""

    root = Path(root)
    evidence_index_path = Path(evidence_index_path)
    summary_name = _normalize_required_text(summary_name, "summary_name")
    created_at = _normalize_created_at(created_at)
    normalized_review_checklist = _normalize_text_sequence(review_checklist, "review_checklist")

    payload, evidence_index = _read_evidence_index(evidence_index_path, root=root)
    evidence_items = _list_of_mappings(payload, "evidence_items")
    required_items = tuple(_public_evidence_item(item) for item in evidence_items if item.get("required") is True)
    optional_items = tuple(_public_evidence_item(item) for item in evidence_items if item.get("required") is not True)
    evidence_counts = dict(_mapping_value(payload, "summary") or {})
    evidence_hashes = _build_evidence_hashes(evidence_index=evidence_index, evidence_items=evidence_items)
    checks = _build_checks(
        payload=payload,
        evidence_index=evidence_index,
        evidence_items=evidence_items,
        evidence_counts=evidence_counts,
        review_checklist=normalized_review_checklist,
    )

    return DeploymentReleaseChannelExportSummary(
        created_at=created_at,
        summary_name=summary_name,
        evidence_index_path=evidence_index_path,
        evidence_index=evidence_index,
        publication=dict(_mapping_value(payload, "publication") or {}),
        package=dict(_mapping_value(payload, "package") or {}),
        operator=dict(_mapping_value(payload, "operator") or {}),
        decision=dict(_mapping_value(payload, "decision") or {}),
        evidence_hashes=evidence_hashes,
        evidence_counts=evidence_counts,
        required_evidence_items=required_items,
        optional_evidence_items=optional_items,
        publication_steps=tuple(_string_list_value(payload, "publication_steps")),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        review_checklist=normalized_review_checklist,
        checks=checks,
    )


def write_deployment_release_channel_export_summary(
    summary: DeploymentReleaseChannelExportSummary,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    payload: Mapping[str, object] | None,
    evidence_index: DeploymentReleaseChannelEvidenceIndexInput,
    evidence_items: tuple[Mapping[str, object], ...],
    evidence_counts: Mapping[str, object],
    review_checklist: tuple[str, ...],
) -> tuple[DeploymentReleaseChannelExportCheck, ...]:
    index_checks = _list_of_mappings(payload, "checks")
    failed_index_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in index_checks
        if check.get("passed") is not True
    ]
    item_by_name = {_str_or_none(item.get("name")) or "": item for item in evidence_items}
    required_total = _number_value(evidence_counts, "required_evidence_item_count")
    required_present = _number_value(evidence_counts, "present_required_evidence_item_count")
    return (
        DeploymentReleaseChannelExportCheck(
            "evidence_index_file_readable",
            evidence_index.readable,
            str(evidence_index.path),
        ),
        DeploymentReleaseChannelExportCheck(
            "evidence_index_json_valid",
            evidence_index.json_valid,
            "valid" if evidence_index.json_valid else "invalid",
        ),
        DeploymentReleaseChannelExportCheck(
            "evidence_index_schema_supported",
            evidence_index.schema_version == DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA,
            f"schema_version={evidence_index.schema_version}",
        ),
        DeploymentReleaseChannelExportCheck(
            "evidence_index_status_ready",
            evidence_index.status == "ready",
            str(evidence_index.status),
        ),
        DeploymentReleaseChannelExportCheck(
            "evidence_index_checks_passed",
            len(index_checks) > 0 and len(failed_index_checks) == 0,
            "failed=" + ",".join(failed_index_checks) if failed_index_checks else f"checks={len(index_checks)}",
        ),
        DeploymentReleaseChannelExportCheck(
            "publication_manifest_sha256_present",
            _item_has_sha(item_by_name, "publication_manifest"),
            "publication_manifest",
        ),
        DeploymentReleaseChannelExportCheck(
            "acceptance_record_sha256_present",
            _item_has_sha(item_by_name, "acceptance_record"),
            "acceptance_record",
        ),
        DeploymentReleaseChannelExportCheck(
            "preparation_manifest_sha256_present",
            _item_has_sha(item_by_name, "preparation_manifest"),
            "preparation_manifest",
        ),
        DeploymentReleaseChannelExportCheck(
            "handoff_inventory_sha256_present",
            _item_has_sha(item_by_name, "handoff_inventory"),
            "handoff_inventory",
        ),
        DeploymentReleaseChannelExportCheck(
            "handoff_archive_hash_bound",
            _item_has_sha(item_by_name, "handoff_archive") and item_by_name.get("handoff_archive", {}).get("hash_matches_expected") is True,
            "handoff_archive",
        ),
        DeploymentReleaseChannelExportCheck(
            "release_evidence_summary_sha256_present",
            _item_has_sha(item_by_name, "release_evidence_summary"),
            "release_evidence_summary",
        ),
        DeploymentReleaseChannelExportCheck(
            "release_review_decision_sha256_present",
            _item_has_sha(item_by_name, "release_review_decision"),
            "release_review_decision",
        ),
        DeploymentReleaseChannelExportCheck(
            "package_evidence_sha256_present",
            _item_has_sha(item_by_name, "package_evidence"),
            "package_evidence",
        ),
        DeploymentReleaseChannelExportCheck(
            "required_evidence_counts_complete",
            isinstance(required_total, int) and required_total > 0 and required_total == required_present,
            f"present={required_present} required={required_total}",
        ),
        DeploymentReleaseChannelExportCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelExportCheck(
            "operator_metadata_present",
            _operator_metadata_present(_mapping_value(payload, "operator")),
            "operator.id,operator.role",
        ),
        DeploymentReleaseChannelExportCheck(
            "publication_steps_present",
            len(_string_list_value(payload, "publication_steps")) > 0,
            f"count={len(_string_list_value(payload, 'publication_steps'))}",
        ),
        DeploymentReleaseChannelExportCheck(
            "local_only_limits_present",
            len(_string_list_value(payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelExportCheck(
            "review_checklist_present",
            len(review_checklist) > 0,
            f"count={len(review_checklist)}",
        ),
    )


def _build_evidence_hashes(
    *,
    evidence_index: DeploymentReleaseChannelEvidenceIndexInput,
    evidence_items: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    hashes: dict[str, object] = {
        "evidence_index_sha256": evidence_index.sha256,
    }
    for item in evidence_items:
        name = _str_or_none(item.get("name"))
        sha256 = _str_or_none(item.get("sha256"))
        if name and sha256:
            hashes[f"{name}_sha256"] = sha256
    return hashes


def _read_evidence_index(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelEvidenceIndexInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelEvidenceIndexInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            index_name=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelEvidenceIndexInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            index_name=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelEvidenceIndexInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            index_name=None,
        )
    return payload, DeploymentReleaseChannelEvidenceIndexInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        index_name=_str_or_none(payload.get("index_name")),
    )


def _public_evidence_item(item: Mapping[str, object]) -> dict[str, object]:
    return {
        "name": _str_or_none(item.get("name")),
        "role": _str_or_none(item.get("role")),
        "sha256": _str_or_none(item.get("sha256")),
        "source_field": _str_or_none(item.get("source_field")),
        "required": item.get("required") is True,
        "expected_sha256": _str_or_none(item.get("expected_sha256")),
        "hash_matches_expected": _bool_or_none(item.get("hash_matches_expected")),
        "present": item.get("present") is True,
    }


def _item_has_sha(item_by_name: Mapping[str, Mapping[str, object]], name: str) -> bool:
    return bool(_str_or_none(item_by_name.get(name, {}).get("sha256")))


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


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _normalize_required_text(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise DeploymentReleaseChannelExportSummaryError(f"{field_name} cannot be empty.")
    return value


def _normalize_text_sequence(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(value.strip() for value in values if value.strip())
    if not normalized:
        raise DeploymentReleaseChannelExportSummaryError(f"{field_name} must include at least one item.")
    return normalized


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelExportSummaryError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
