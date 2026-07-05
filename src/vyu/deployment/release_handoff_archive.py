from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import zipfile

from src.vyu.deployment.package_archive import DETERMINISTIC_ZIP_TIMESTAMP
from src.vyu.deployment.release_handoff import DEPLOYMENT_RELEASE_HANDOFF_SCHEMA

DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA = 1


class DeploymentReleaseHandoffArchiveError(RuntimeError):
    """Raised when deployment release handoff archive metadata is invalid."""


@dataclass(frozen=True)
class DeploymentReleaseHandoffArchiveCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseHandoffArchiveArtifact:
    name: str
    path: Path
    archive_entry: str
    exists: bool
    json_valid: bool
    size_bytes: int | None
    sha256: str | None
    expected_sha256: str | None = None
    expected_sha256_source: str | None = None
    include_in_archive: bool = True

    @property
    def hash_matches_expected(self) -> bool:
        return self.expected_sha256 is None or self.sha256 == self.expected_sha256

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "archive_entry": self.archive_entry,
            "exists": self.exists,
            "json_valid": self.json_valid,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "expected_sha256": self.expected_sha256,
            "expected_sha256_source": self.expected_sha256_source,
            "hash_matches_expected": self.hash_matches_expected,
            "include_in_archive": self.include_in_archive,
        }


@dataclass(frozen=True)
class DeploymentReleaseHandoffArchiveInventory:
    created_at: str
    handoff_path: Path
    archive_path: Path | None
    archive_sha256: str | None
    package: dict[str, object]
    artifact_hashes: dict[str, object]
    artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...] = field(default_factory=tuple)
    checks: tuple[DeploymentReleaseHandoffArchiveCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        included_artifacts = [artifact for artifact in self.artifacts if artifact.include_in_archive]
        return {
            "schema_version": DEPLOYMENT_RELEASE_HANDOFF_ARCHIVE_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "handoff_path": str(self.handoff_path),
            "archive": {
                "path": str(self.archive_path) if self.archive_path is not None else None,
                "sha256": self.archive_sha256,
                "requested": self.archive_path is not None,
                "entry_count": len(included_artifacts),
            },
            "package": dict(self.package),
            "artifact_hashes": dict(self.artifact_hashes),
            "summary": {
                "artifact_count": len(self.artifacts),
                "included_artifact_count": len(included_artifacts),
                "total_bytes": sum(artifact.size_bytes or 0 for artifact in self.artifacts),
                "included_total_bytes": sum(artifact.size_bytes or 0 for artifact in included_artifacts),
                "passed": passed,
                "failed": failed,
                "total": len(self.checks),
            },
            "artifacts": [artifact.to_json() for artifact in self.artifacts],
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_handoff_archive_inventory(
    *,
    handoff_path: Path,
    root: Path = Path("."),
    created_at: str | None = None,
    archive_path: Path | None = None,
) -> DeploymentReleaseHandoffArchiveInventory:
    """Build a deterministic local inventory, and optionally a zip archive, for handoff evidence."""

    root = Path(root)
    handoff_path = Path(handoff_path)
    archive_path = Path(archive_path) if archive_path is not None else None
    created_at = _normalize_created_at(created_at)

    handoff_payload, handoff_readable, handoff_json_valid = _read_json_mapping(handoff_path, root=root)
    summary_path = _handoff_input_path(handoff_payload, "release_evidence_summary", "summary_path")
    review_path = _handoff_input_path(handoff_payload, "release_review_decision", "review_path")

    summary_payload, _, _ = _read_json_mapping(summary_path, root=root) if summary_path else (None, False, False)
    review_payload, _, _ = _read_json_mapping(review_path, root=root) if review_path else (None, False, False)

    package_evidence_path = _summary_input_path(summary_payload, "package_evidence", "package_evidence_path")
    release_checklist_path = _summary_input_path(summary_payload, "release_checklist", "release_checklist_path")
    transcript_bundle_path = _summary_input_path(summary_payload, "transcript_bundle", "transcript_bundle_path")

    artifact_hashes = dict(_mapping_value(handoff_payload, "artifact_hashes") or {})
    artifacts = tuple(
        artifact
        for artifact in (
            _artifact(
                "deployment_release_handoff",
                handoff_path,
                root=root,
                expected_sha256=None,
                expected_sha256_source=None,
            ),
            _artifact(
                "release_evidence_summary",
                summary_path,
                root=root,
                expected_sha256=_expected_hash(
                    handoff_payload,
                    input_name="release_evidence_summary",
                    artifact_key="release_evidence_summary_sha256",
                ),
                expected_sha256_source="handoff.artifact_hashes.release_evidence_summary_sha256",
            ),
            _artifact(
                "release_review_decision",
                review_path,
                root=root,
                expected_sha256=_expected_hash(
                    handoff_payload,
                    input_name="release_review_decision",
                    artifact_key="release_review_decision_sha256",
                ),
                expected_sha256_source="handoff.artifact_hashes.release_review_decision_sha256",
            ),
            _artifact(
                "deployment_package_evidence",
                package_evidence_path,
                root=root,
                expected_sha256=_str_or_none(artifact_hashes.get("package_evidence_sha256")),
                expected_sha256_source="handoff.artifact_hashes.package_evidence_sha256",
            ),
            _artifact(
                "deployment_release_package_checklist",
                release_checklist_path,
                root=root,
                expected_sha256=_str_or_none(artifact_hashes.get("release_checklist_sha256")),
                expected_sha256_source="handoff.artifact_hashes.release_checklist_sha256",
            ),
            _artifact(
                "deployment_transcript_bundle",
                transcript_bundle_path,
                root=root,
                expected_sha256=_str_or_none(artifact_hashes.get("transcript_bundle_sha256")),
                expected_sha256_source="handoff.artifact_hashes.transcript_bundle_sha256",
            ),
        )
        if artifact is not None
    )

    checks = list(
        _build_inventory_checks(
            handoff_payload=handoff_payload,
            handoff_readable=handoff_readable,
            handoff_json_valid=handoff_json_valid,
            summary_path=summary_path,
            review_path=review_path,
            package_evidence_path=package_evidence_path,
            release_checklist_path=release_checklist_path,
            transcript_bundle_path=transcript_bundle_path,
            artifacts=artifacts,
        )
    )

    archive_sha256: str | None = None
    if archive_path is not None:
        archive_checks, archive_sha256 = _write_and_verify_archive_if_ready(
            archive_path=archive_path,
            root=root,
            artifacts=artifacts,
            pre_archive_checks=tuple(checks),
        )
        checks.extend(archive_checks)

    return DeploymentReleaseHandoffArchiveInventory(
        created_at=created_at,
        handoff_path=handoff_path,
        archive_path=archive_path,
        archive_sha256=archive_sha256,
        package=dict(_mapping_value(handoff_payload, "package") or {}),
        artifact_hashes=artifact_hashes,
        artifacts=artifacts,
        checks=tuple(checks),
    )


def write_deployment_release_handoff_archive_inventory(
    inventory: DeploymentReleaseHandoffArchiveInventory,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(inventory.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_inventory_checks(
    *,
    handoff_payload: Mapping[str, object] | None,
    handoff_readable: bool,
    handoff_json_valid: bool,
    summary_path: Path | None,
    review_path: Path | None,
    package_evidence_path: Path | None,
    release_checklist_path: Path | None,
    transcript_bundle_path: Path | None,
    artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...],
) -> tuple[DeploymentReleaseHandoffArchiveCheck, ...]:
    archive_entries = [artifact.archive_entry for artifact in artifacts if artifact.include_in_archive]
    return (
        DeploymentReleaseHandoffArchiveCheck(
            "handoff_file_readable",
            handoff_readable,
            "deployment_release_handoff",
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "handoff_json_valid",
            handoff_json_valid,
            "deployment_release_handoff",
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "handoff_schema_supported",
            _optional_int(handoff_payload.get("schema_version") if handoff_payload else None)
            == DEPLOYMENT_RELEASE_HANDOFF_SCHEMA,
            f"schema_version={handoff_payload.get('schema_version') if handoff_payload else None}",
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "handoff_status_ready",
            _str_or_none(handoff_payload.get("status") if handoff_payload else None) == "ready",
            str(handoff_payload.get("status") if handoff_payload else None),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "handoff_input_paths_present",
            summary_path is not None and review_path is not None,
            _missing_path_detail(
                {
                    "release_evidence_summary": summary_path,
                    "release_review_decision": review_path,
                }
            ),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "release_evidence_paths_present",
            package_evidence_path is not None
            and release_checklist_path is not None
            and transcript_bundle_path is not None,
            _missing_path_detail(
                {
                    "package_evidence": package_evidence_path,
                    "release_checklist": release_checklist_path,
                    "transcript_bundle": transcript_bundle_path,
                }
            ),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "referenced_files_exist",
            all(artifact.exists for artifact in artifacts),
            _artifact_failure_detail(artifacts, "exists"),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "referenced_json_valid",
            all(artifact.json_valid for artifact in artifacts),
            _artifact_failure_detail(artifacts, "json_valid"),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "recorded_hashes_match_files",
            all(artifact.hash_matches_expected for artifact in artifacts),
            _hash_failure_detail(artifacts),
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "included_archive_entries_unique",
            len(set(archive_entries)) == len(archive_entries),
            f"entries={len(archive_entries)} unique={len(set(archive_entries))}",
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "local_secret_config_absent",
            not any("config/deployment.local.env" in artifact.archive_entry for artifact in artifacts),
            "config/deployment.local.env",
        ),
        DeploymentReleaseHandoffArchiveCheck(
            "generated_caches_absent",
            not any("__pycache__" in artifact.archive_entry or artifact.archive_entry.endswith(".pyc") for artifact in artifacts),
            "__pycache__, *.pyc",
        ),
    )


def _write_and_verify_archive_if_ready(
    *,
    archive_path: Path,
    root: Path,
    artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...],
    pre_archive_checks: tuple[DeploymentReleaseHandoffArchiveCheck, ...],
) -> tuple[tuple[DeploymentReleaseHandoffArchiveCheck, ...], str | None]:
    if not all(check.passed for check in pre_archive_checks):
        return (
            (
                DeploymentReleaseHandoffArchiveCheck(
                    "handoff_archive_written",
                    False,
                    "blocked_by_inventory_checks",
                ),
            ),
            None,
        )

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    included = tuple(sorted((artifact for artifact in artifacts if artifact.include_in_archive), key=lambda item: item.archive_entry))
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact in included:
            data = _resolve_path(artifact.path, root=root).read_bytes()
            info = zipfile.ZipInfo(artifact.archive_entry, date_time=DETERMINISTIC_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)

    archive_sha256 = _sha256(_absolute_path(archive_path, root=root))
    verification_checks = _verify_archive(archive_path=archive_path, root=root, artifacts=included)
    return verification_checks, archive_sha256


def _verify_archive(
    *,
    archive_path: Path,
    root: Path,
    artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...],
) -> tuple[DeploymentReleaseHandoffArchiveCheck, ...]:
    archive_file = _absolute_path(archive_path, root=root)
    if not archive_file.is_file():
        return (
            DeploymentReleaseHandoffArchiveCheck("handoff_archive_written", False, str(archive_path)),
        )

    expected_entries = [artifact.archive_entry for artifact in artifacts]
    expected_hashes = {artifact.archive_entry: artifact.sha256 for artifact in artifacts}
    try:
        with zipfile.ZipFile(archive_file, "r") as archive:
            infos = archive.infolist()
            entry_names = [info.filename for info in infos]
            entry_hashes = {info.filename: hashlib.sha256(archive.read(info.filename)).hexdigest() for info in infos}
            deterministic_metadata = all(
                info.date_time == DETERMINISTIC_ZIP_TIMESTAMP and (info.external_attr >> 16) == 0o100644
                for info in infos
            )
    except zipfile.BadZipFile:
        return (
            DeploymentReleaseHandoffArchiveCheck("handoff_archive_written", True, str(archive_path)),
            DeploymentReleaseHandoffArchiveCheck("archive_readable", False, "bad zip file"),
        )

    return (
        DeploymentReleaseHandoffArchiveCheck("handoff_archive_written", True, str(archive_path)),
        DeploymentReleaseHandoffArchiveCheck("archive_entries_match_inventory", entry_names == expected_entries, f"entries={len(entry_names)} expected={len(expected_entries)}"),
        DeploymentReleaseHandoffArchiveCheck("archive_entry_hashes_match_inventory", entry_hashes == expected_hashes, f"entries={len(entry_hashes)} expected={len(expected_hashes)}"),
        DeploymentReleaseHandoffArchiveCheck("archive_metadata_deterministic", deterministic_metadata, str(DETERMINISTIC_ZIP_TIMESTAMP)),
    )


def _artifact(
    name: str,
    path: Path | None,
    *,
    root: Path,
    expected_sha256: str | None,
    expected_sha256_source: str | None,
) -> DeploymentReleaseHandoffArchiveArtifact | None:
    if path is None:
        return None
    display_path = Path(path)
    file_path = _absolute_path(display_path, root=root)
    exists = file_path.is_file()
    size_bytes = file_path.stat().st_size if exists else None
    sha256 = _sha256(file_path) if exists else None
    json_valid = _is_valid_json_mapping(file_path) if exists else False
    return DeploymentReleaseHandoffArchiveArtifact(
        name=name,
        path=display_path,
        archive_entry=_archive_entry(display_path, root=root),
        exists=exists,
        json_valid=json_valid,
        size_bytes=size_bytes,
        sha256=sha256,
        expected_sha256=expected_sha256,
        expected_sha256_source=expected_sha256_source if expected_sha256 else None,
        include_in_archive=True,
    )


def _read_json_mapping(path: Path | None, *, root: Path) -> tuple[Mapping[str, object] | None, bool, bool]:
    if path is None:
        return None, False, False
    file_path = _absolute_path(Path(path), root=root)
    if not file_path.is_file():
        return None, False, False
    try:
        payload: Any = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, True, False
    if not isinstance(payload, Mapping):
        return None, True, False
    return payload, True, True


def _handoff_input_path(
    handoff_payload: Mapping[str, object] | None,
    input_name: str,
    top_level_key: str,
) -> Path | None:
    if handoff_payload is None:
        return None
    top_level = _str_or_none(handoff_payload.get(top_level_key))
    if top_level:
        return Path(top_level)
    inputs = _mapping_value(handoff_payload, "inputs")
    item = _mapping_value(inputs, input_name)
    item_path = _str_or_none(item.get("path")) if item else None
    return Path(item_path) if item_path else None


def _summary_input_path(
    summary_payload: Mapping[str, object] | None,
    input_name: str,
    top_level_key: str,
) -> Path | None:
    if summary_payload is None:
        return None
    top_level = _str_or_none(summary_payload.get(top_level_key))
    if top_level:
        return Path(top_level)
    inputs = _mapping_value(summary_payload, "inputs")
    item = _mapping_value(inputs, input_name)
    item_path = _str_or_none(item.get("path")) if item else None
    return Path(item_path) if item_path else None


def _expected_hash(
    handoff_payload: Mapping[str, object] | None,
    *,
    input_name: str,
    artifact_key: str,
) -> str | None:
    artifact_hashes = _mapping_value(handoff_payload, "artifact_hashes")
    value = _str_or_none(artifact_hashes.get(artifact_key)) if artifact_hashes else None
    if value:
        return value
    inputs = _mapping_value(handoff_payload, "inputs")
    item = _mapping_value(inputs, input_name)
    return _str_or_none(item.get("sha256")) if item else None


def _absolute_path(path: Path, *, root: Path) -> Path:
    return path if path.is_absolute() else root / path


def _resolve_path(path: Path, *, root: Path) -> Path:
    return _absolute_path(path, root=root)


def _archive_entry(path: Path, *, root: Path) -> str:
    path = Path(path)
    if path.is_absolute():
        try:
            return path.relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.name
    return path.as_posix()


def _is_valid_json_mapping(path: Path) -> bool:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return isinstance(payload, Mapping)


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
            raise DeploymentReleaseHandoffArchiveError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _missing_path_detail(paths: Mapping[str, Path | None]) -> str:
    missing = [name for name, value in paths.items() if value is None]
    return "missing=" + ",".join(missing) if missing else "complete"


def _artifact_failure_detail(
    artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...],
    attribute: str,
) -> str:
    missing = [artifact.name for artifact in artifacts if not bool(getattr(artifact, attribute))]
    return "failed=" + ",".join(missing) if missing else "complete"


def _hash_failure_detail(artifacts: tuple[DeploymentReleaseHandoffArchiveArtifact, ...]) -> str:
    failed = [artifact.name for artifact in artifacts if not artifact.hash_matches_expected]
    return "failed=" + ",".join(failed) if failed else "complete"
