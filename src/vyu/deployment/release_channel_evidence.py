from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.vyu.deployment.release_channel_publication import DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA

DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA = 1
DEFAULT_RELEASE_CHANNEL_EVIDENCE_INDEX_NAME = "local-release-channel-evidence-index"


class DeploymentReleaseChannelEvidenceIndexError(RuntimeError):
    """Raised when release-channel evidence index metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseChannelEvidenceCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseChannelPublicationInput:
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    created_at: str | None
    publication_channel: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "created_at": self.created_at,
            "publication_channel": self.publication_channel,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelEvidenceItem:
    name: str
    role: str
    sha256: str | None
    source_field: str
    required: bool = True
    expected_sha256: str | None = None
    hash_matches_expected: bool | None = None

    @property
    def present(self) -> bool:
        return bool(self.sha256)

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "sha256": self.sha256,
            "source_field": self.source_field,
            "required": self.required,
            "expected_sha256": self.expected_sha256,
            "hash_matches_expected": self.hash_matches_expected,
            "present": self.present,
        }


@dataclass(frozen=True)
class DeploymentReleaseChannelEvidenceIndex:
    created_at: str
    index_name: str
    publication_path: Path
    publication: DeploymentReleaseChannelPublicationInput
    package: dict[str, object]
    operator: dict[str, object]
    decision: dict[str, object]
    publication_steps: tuple[str, ...]
    local_only_limits: tuple[str, ...]
    evidence_items: tuple[DeploymentReleaseChannelEvidenceItem, ...]
    checks: tuple[DeploymentReleaseChannelEvidenceCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_CHANNEL_EVIDENCE_INDEX_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "index_name": self.index_name,
            "publication_path": str(self.publication_path),
            "publication": self.publication.to_json(),
            "package": dict(self.package),
            "operator": dict(self.operator),
            "decision": dict(self.decision),
            "publication_steps": list(self.publication_steps),
            "local_only_limits": list(self.local_only_limits),
            "evidence_items": [item.to_json() for item in self.evidence_items],
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
                "evidence_item_count": len(self.evidence_items),
                "required_evidence_item_count": sum(1 for item in self.evidence_items if item.required),
                "present_required_evidence_item_count": sum(1 for item in self.evidence_items if item.required and item.present),
            },
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_channel_evidence_index(
    *,
    publication_path: Path,
    root: Path = Path("."),
    index_name: str = DEFAULT_RELEASE_CHANNEL_EVIDENCE_INDEX_NAME,
    created_at: str | None = None,
) -> DeploymentReleaseChannelEvidenceIndex:
    """Build a local release-channel evidence index from a ready publication manifest."""

    root = Path(root)
    publication_path = Path(publication_path)
    index_name = _normalize_required_text(index_name, "index_name")
    created_at = _normalize_created_at(created_at)

    payload, publication = _read_publication(publication_path, root=root)
    evidence_items = _build_evidence_items(payload, publication_sha256=publication.sha256)
    checks = _build_checks(
        publication_payload=payload,
        publication=publication,
        evidence_items=evidence_items,
    )

    return DeploymentReleaseChannelEvidenceIndex(
        created_at=created_at,
        index_name=index_name,
        publication_path=publication_path,
        publication=publication,
        package=dict(_mapping_value(payload, "package") or {}),
        operator=dict(_mapping_value(payload, "operator") or {}),
        decision=dict(_mapping_value(payload, "decision") or {}),
        publication_steps=tuple(_string_list_value(payload, "publication_steps")),
        local_only_limits=tuple(_string_list_value(payload, "local_only_limits")),
        evidence_items=evidence_items,
        checks=checks,
    )


def write_deployment_release_channel_evidence_index(
    index: DeploymentReleaseChannelEvidenceIndex,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(index.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_checks(
    *,
    publication_payload: Mapping[str, object] | None,
    publication: DeploymentReleaseChannelPublicationInput,
    evidence_items: tuple[DeploymentReleaseChannelEvidenceItem, ...],
) -> tuple[DeploymentReleaseChannelEvidenceCheck, ...]:
    publication_checks = _list_value(publication_payload, "checks")
    failed_publication_checks = [
        _str_or_none(check.get("name")) or "unnamed_check"
        for check in publication_checks
        if isinstance(check, Mapping) and check.get("passed") is not True
    ]
    required_missing = [item.name for item in evidence_items if item.required and not item.present]
    archive_item = next((item for item in evidence_items if item.name == "handoff_archive"), None)
    return (
        DeploymentReleaseChannelEvidenceCheck(
            "publication_file_readable",
            publication.readable,
            str(publication.path),
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "publication_json_valid",
            publication.json_valid,
            "valid" if publication.json_valid else "invalid",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "publication_schema_supported",
            publication.schema_version == DEPLOYMENT_RELEASE_CHANNEL_PUBLICATION_SCHEMA,
            f"schema_version={publication.schema_version}",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "publication_status_ready",
            publication.status == "ready",
            str(publication.status),
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "publication_checks_passed",
            len(publication_checks) > 0 and len(failed_publication_checks) == 0,
            "failed=" + ",".join(failed_publication_checks) if failed_publication_checks else f"checks={len(publication_checks)}",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "acceptance_sha256_present",
            bool(_nested_str(publication_payload, "acceptance", "sha256")),
            "acceptance.sha256",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "acceptance_status_accepted",
            _nested_str(publication_payload, "acceptance", "status") == "accepted",
            str(_nested_str(publication_payload, "acceptance", "status")),
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "decision_approves",
            _nested_str(publication_payload, "decision", "value") == "approve",
            str(_nested_str(publication_payload, "decision", "value")),
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "preparation_sha256_present",
            bool(_nested_str(publication_payload, "preparation", "sha256")),
            "preparation.sha256",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "preparation_status_ready",
            _nested_str(publication_payload, "preparation", "status") == "ready",
            str(_nested_str(publication_payload, "preparation", "status")),
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "preparation_inventory_sha256_present",
            bool(_str_or_none(publication_payload.get("preparation_inventory_sha256") if publication_payload else None)),
            "preparation_inventory_sha256",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "handoff_archive_hash_bound",
            archive_item is not None and archive_item.present and archive_item.hash_matches_expected is True,
            "handoff_archive",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "package_metadata_present",
            _package_metadata_present(_mapping_value(publication_payload, "package")),
            "package_name,runtime,handler",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "operator_metadata_present",
            _operator_metadata_present(_mapping_value(publication_payload, "operator")),
            "operator.id,operator.role",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "publication_steps_present",
            len(_string_list_value(publication_payload, "publication_steps")) > 0,
            f"count={len(_string_list_value(publication_payload, 'publication_steps'))}",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "local_only_limits_present",
            len(_string_list_value(publication_payload, "local_only_limits")) > 0,
            f"count={len(_string_list_value(publication_payload, 'local_only_limits'))}",
        ),
        DeploymentReleaseChannelEvidenceCheck(
            "required_evidence_items_present",
            len(required_missing) == 0,
            "missing=" + ",".join(required_missing) if required_missing else f"required={sum(1 for item in evidence_items if item.required)}",
        ),
    )


def _build_evidence_items(
    payload: Mapping[str, object] | None,
    *,
    publication_sha256: str | None,
) -> tuple[DeploymentReleaseChannelEvidenceItem, ...]:
    archive = _mapping_value(payload, "preparation_archive")
    artifact_hashes = _mapping_value(payload, "preparation_artifact_hashes")
    items = [
        DeploymentReleaseChannelEvidenceItem(
            name="publication_manifest",
            role="release_channel_publication_manifest",
            sha256=publication_sha256,
            source_field="publication_file.sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="acceptance_record",
            role="release_channel_acceptance_record",
            sha256=_nested_str(payload, "acceptance", "sha256"),
            source_field="acceptance.sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="preparation_manifest",
            role="release_channel_preparation_manifest",
            sha256=_nested_str(payload, "preparation", "sha256"),
            source_field="preparation.sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="handoff_inventory",
            role="release_handoff_inventory",
            sha256=_str_or_none(payload.get("preparation_inventory_sha256") if payload else None),
            source_field="preparation_inventory_sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="handoff_archive",
            role="release_handoff_archive",
            sha256=_str_or_none(archive.get("sha256") if archive else None),
            source_field="preparation_archive.sha256",
            expected_sha256=_str_or_none(archive.get("expected_sha256") if archive else None),
            hash_matches_expected=_bool_or_none(archive.get("hash_matches_expected") if archive else None),
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="release_evidence_summary",
            role="release_evidence_summary",
            sha256=_str_or_none(artifact_hashes.get("release_evidence_summary_sha256") if artifact_hashes else None),
            source_field="preparation_artifact_hashes.release_evidence_summary_sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="release_review_decision",
            role="release_review_decision",
            sha256=_str_or_none(artifact_hashes.get("release_review_decision_sha256") if artifact_hashes else None),
            source_field="preparation_artifact_hashes.release_review_decision_sha256",
        ),
        DeploymentReleaseChannelEvidenceItem(
            name="package_evidence",
            role="deployment_package_evidence",
            sha256=_str_or_none(artifact_hashes.get("package_evidence_sha256") if artifact_hashes else None),
            source_field="preparation_artifact_hashes.package_evidence_sha256",
        ),
    ]
    optional_names = (
        ("deployment_release_checklist", "deployment_release_checklist", "release_checklist_sha256"),
        ("deployment_transcript_bundle", "deployment_transcript_bundle", "transcript_bundle_sha256"),
        ("handoff_archive_from_artifacts", "release_handoff_archive", "handoff_archive_sha256"),
    )
    for name, role, key in optional_names:
        value = _str_or_none(artifact_hashes.get(key) if artifact_hashes else None)
        if value:
            items.append(
                DeploymentReleaseChannelEvidenceItem(
                    name=name,
                    role=role,
                    sha256=value,
                    source_field=f"preparation_artifact_hashes.{key}",
                    required=False,
                )
            )
    return tuple(items)


def _read_publication(
    path: Path,
    *,
    root: Path,
) -> tuple[Mapping[str, object] | None, DeploymentReleaseChannelPublicationInput]:
    path = Path(path)
    file_path = path if path.is_absolute() else root / path
    sha256 = _sha256(file_path) if file_path.is_file() else None
    if not file_path.is_file():
        return None, DeploymentReleaseChannelPublicationInput(
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            publication_channel=None,
        )
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseChannelPublicationInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            publication_channel=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseChannelPublicationInput(
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            created_at=None,
            publication_channel=None,
        )
    return payload, DeploymentReleaseChannelPublicationInput(
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=_str_or_none(payload.get("status")),
        created_at=_str_or_none(payload.get("created_at")),
        publication_channel=_str_or_none(payload.get("publication_channel")),
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


def _string_list_value(payload: Mapping[str, object] | None, key: str) -> list[str]:
    return [value for value in _list_value(payload, key) if isinstance(value, str)]


def _optional_int(value: object) -> int | None:
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
        raise DeploymentReleaseChannelEvidenceIndexError(f"{field_name} cannot be empty.")
    return value


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseChannelEvidenceIndexError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
