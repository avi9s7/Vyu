from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.package_evidence import DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA
from src.vyu.deployment.release_package import DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA
from src.vyu.deployment.transcript_bundle import DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA

DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA = 1


class DeploymentReleaseEvidenceError(RuntimeError):
    """Raised when deployment release evidence cannot be summarized."""


@dataclass(frozen=True)
class DeploymentReleaseEvidenceCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleaseEvidenceInput:
    name: str
    path: Path
    sha256: str | None
    readable: bool
    json_valid: bool
    schema_version: int | None
    status: str | None
    manifest_path: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": self.sha256,
            "readable": self.readable,
            "json_valid": self.json_valid,
            "schema_version": self.schema_version,
            "status": self.status,
            "manifest_path": self.manifest_path,
        }


@dataclass(frozen=True)
class DeploymentReleaseEvidenceSummary:
    created_at: str
    package_evidence_path: Path
    release_checklist_path: Path
    transcript_bundle_path: Path
    inputs: dict[str, DeploymentReleaseEvidenceInput]
    package: dict[str, object]
    artifact_hashes: dict[str, str | None]
    command_summary: dict[str, object]
    checks: tuple[DeploymentReleaseEvidenceCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "package_evidence_path": str(self.package_evidence_path),
            "release_checklist_path": str(self.release_checklist_path),
            "transcript_bundle_path": str(self.transcript_bundle_path),
            "inputs": {name: item.to_json() for name, item in self.inputs.items()},
            "package": dict(self.package),
            "artifact_hashes": dict(self.artifact_hashes),
            "command_summary": dict(self.command_summary),
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_evidence_summary(
    *,
    package_evidence_path: Path,
    release_checklist_path: Path,
    transcript_bundle_path: Path,
    created_at: str | None = None,
) -> DeploymentReleaseEvidenceSummary:
    """Build one local operator-review summary from package, checklist, and transcript evidence."""

    created_at = _normalize_created_at(created_at)
    package_evidence_path = Path(package_evidence_path)
    release_checklist_path = Path(release_checklist_path)
    transcript_bundle_path = Path(transcript_bundle_path)

    evidence_payload, evidence_input = _read_input("package_evidence", package_evidence_path)
    checklist_payload, checklist_input = _read_input("release_checklist", release_checklist_path)
    bundle_payload, bundle_input = _read_input("transcript_bundle", transcript_bundle_path)
    inputs = {
        evidence_input.name: evidence_input,
        checklist_input.name: checklist_input,
        bundle_input.name: bundle_input,
    }

    checks = _build_checks(
        evidence_payload=evidence_payload,
        checklist_payload=checklist_payload,
        bundle_payload=bundle_payload,
        evidence_input=evidence_input,
        checklist_input=checklist_input,
        bundle_input=bundle_input,
    )

    return DeploymentReleaseEvidenceSummary(
        created_at=created_at,
        package_evidence_path=package_evidence_path,
        release_checklist_path=release_checklist_path,
        transcript_bundle_path=transcript_bundle_path,
        inputs=inputs,
        package=_package_summary(evidence_payload, checklist_payload),
        artifact_hashes=_artifact_hash_summary(
            evidence_payload=evidence_payload,
            checklist_payload=checklist_payload,
            evidence_sha256=evidence_input.sha256,
            checklist_sha256=checklist_input.sha256,
            bundle_sha256=bundle_input.sha256,
        ),
        command_summary=_command_summary(evidence_payload, bundle_payload),
        checks=checks,
    )


def write_deployment_release_evidence_summary(
    summary: DeploymentReleaseEvidenceSummary,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleaseEvidenceError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_input(name: str, path: Path) -> tuple[Mapping[str, object] | None, DeploymentReleaseEvidenceInput]:
    path = Path(path)
    sha256 = _sha256(path) if path.is_file() else None
    if not path.is_file():
        return None, DeploymentReleaseEvidenceInput(
            name=name,
            path=path,
            sha256=None,
            readable=False,
            json_valid=False,
            schema_version=None,
            status=None,
            manifest_path=None,
        )
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, DeploymentReleaseEvidenceInput(
            name=name,
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            manifest_path=None,
        )
    if not isinstance(payload, Mapping):
        return None, DeploymentReleaseEvidenceInput(
            name=name,
            path=path,
            sha256=sha256,
            readable=True,
            json_valid=False,
            schema_version=None,
            status=None,
            manifest_path=None,
        )
    return payload, DeploymentReleaseEvidenceInput(
        name=name,
        path=path,
        sha256=sha256,
        readable=True,
        json_valid=True,
        schema_version=_optional_int(payload.get("schema_version")),
        status=payload.get("status") if isinstance(payload.get("status"), str) else None,
        manifest_path=payload.get("manifest_path") if isinstance(payload.get("manifest_path"), str) else None,
    )


def _build_checks(
    *,
    evidence_payload: Mapping[str, object] | None,
    checklist_payload: Mapping[str, object] | None,
    bundle_payload: Mapping[str, object] | None,
    evidence_input: DeploymentReleaseEvidenceInput,
    checklist_input: DeploymentReleaseEvidenceInput,
    bundle_input: DeploymentReleaseEvidenceInput,
) -> tuple[DeploymentReleaseEvidenceCheck, ...]:
    manifest_paths = [item.manifest_path for item in (evidence_input, checklist_input, bundle_input)]
    expected_manifest = next((path for path in manifest_paths if path), None)
    return (
        DeploymentReleaseEvidenceCheck(
            "input_files_readable",
            evidence_input.readable and checklist_input.readable and bundle_input.readable,
            _missing_input_detail(evidence_input, checklist_input, bundle_input),
        ),
        DeploymentReleaseEvidenceCheck(
            "input_json_valid",
            evidence_input.json_valid and checklist_input.json_valid and bundle_input.json_valid,
            _invalid_json_detail(evidence_input, checklist_input, bundle_input),
        ),
        DeploymentReleaseEvidenceCheck(
            "package_evidence_schema_supported",
            evidence_input.schema_version == DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
            f"schema_version={evidence_input.schema_version}",
        ),
        DeploymentReleaseEvidenceCheck(
            "release_checklist_schema_supported",
            checklist_input.schema_version == DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA,
            f"schema_version={checklist_input.schema_version}",
        ),
        DeploymentReleaseEvidenceCheck(
            "transcript_bundle_schema_supported",
            bundle_input.schema_version == DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA,
            f"schema_version={bundle_input.schema_version}",
        ),
        DeploymentReleaseEvidenceCheck(
            "package_evidence_complete",
            evidence_input.status == "complete",
            str(evidence_input.status),
        ),
        DeploymentReleaseEvidenceCheck(
            "release_checklist_ready",
            checklist_input.status == "ready",
            str(checklist_input.status),
        ),
        DeploymentReleaseEvidenceCheck(
            "transcript_bundle_ready",
            bundle_input.status == "ready",
            str(bundle_input.status),
        ),
        DeploymentReleaseEvidenceCheck(
            "manifest_paths_match",
            expected_manifest is not None and all(path == expected_manifest for path in manifest_paths),
            ",".join(str(path) for path in manifest_paths),
        ),
        DeploymentReleaseEvidenceCheck(
            "package_metadata_matches",
            _package_metadata_matches(evidence_payload, checklist_payload),
            "package",
        ),
        DeploymentReleaseEvidenceCheck(
            "package_artifact_hashes_match_checklist",
            _artifact_hashes_match(evidence_payload, checklist_payload),
            "archive_sha256,inventory_sha256",
        ),
        DeploymentReleaseEvidenceCheck(
            "checklist_evidence_hash_matches_input",
            _checklist_evidence_hash_matches(checklist_payload, evidence_input.sha256),
            str(evidence_input.sha256),
        ),
        DeploymentReleaseEvidenceCheck(
            "required_commands_match_transcript_bundle",
            _required_commands_match(evidence_payload, bundle_payload),
            "required_validation_commands",
        ),
        DeploymentReleaseEvidenceCheck(
            "transcript_bundle_coverage_complete",
            _transcript_bundle_coverage_complete(bundle_payload),
            _transcript_bundle_coverage_detail(bundle_payload),
        ),
    )


def _package_summary(
    evidence_payload: Mapping[str, object] | None,
    checklist_payload: Mapping[str, object] | None,
) -> dict[str, object]:
    evidence_package = _mapping_value(evidence_payload, "package")
    if evidence_package is not None:
        return dict(evidence_package)
    checklist_package = _mapping_value(checklist_payload, "package")
    return dict(checklist_package or {})


def _artifact_hash_summary(
    *,
    evidence_payload: Mapping[str, object] | None,
    checklist_payload: Mapping[str, object] | None,
    evidence_sha256: str | None,
    checklist_sha256: str | None,
    bundle_sha256: str | None,
) -> dict[str, str | None]:
    evidence_hashes = _mapping_value(evidence_payload, "artifact_hashes") or {}
    checklist_hashes = _mapping_value(checklist_payload, "artifact_hashes") or {}
    return {
        "package_evidence_sha256": evidence_sha256,
        "release_checklist_sha256": checklist_sha256,
        "transcript_bundle_sha256": bundle_sha256,
        "archive_sha256": _str_or_none(evidence_hashes.get("archive_sha256"))
        or _str_or_none(checklist_hashes.get("archive_sha256")),
        "inventory_sha256": _str_or_none(evidence_hashes.get("inventory_sha256"))
        or _str_or_none(checklist_hashes.get("inventory_sha256")),
        "checklist_evidence_sha256": _str_or_none(checklist_hashes.get("evidence_sha256")),
    }


def _command_summary(
    evidence_payload: Mapping[str, object] | None,
    bundle_payload: Mapping[str, object] | None,
) -> dict[str, object]:
    evidence_commands = _command_list(evidence_payload.get("required_validation_commands") if evidence_payload else None)
    bundle_commands = _bundle_required_commands(bundle_payload)
    bundle_summary = _mapping_value(bundle_payload, "summary") or {}
    return {
        "required_command_count": len(evidence_commands) or len(bundle_commands),
        "bundle_required_command_count": _optional_int(bundle_summary.get("required_command_count")),
        "covered_command_count": _optional_int(bundle_summary.get("covered_command_count")),
        "commands_match": evidence_commands == bundle_commands if evidence_commands and bundle_commands else False,
    }


def _missing_input_detail(*inputs: DeploymentReleaseEvidenceInput) -> str:
    missing = [item.name for item in inputs if not item.readable]
    return "missing=" + ",".join(missing) if missing else "complete"


def _invalid_json_detail(*inputs: DeploymentReleaseEvidenceInput) -> str:
    invalid = [item.name for item in inputs if item.readable and not item.json_valid]
    return "invalid=" + ",".join(invalid) if invalid else "complete"


def _package_metadata_matches(
    evidence_payload: Mapping[str, object] | None,
    checklist_payload: Mapping[str, object] | None,
) -> bool:
    evidence_package = _mapping_value(evidence_payload, "package")
    checklist_package = _mapping_value(checklist_payload, "package")
    return evidence_package is not None and evidence_package == checklist_package


def _artifact_hashes_match(
    evidence_payload: Mapping[str, object] | None,
    checklist_payload: Mapping[str, object] | None,
) -> bool:
    evidence_hashes = _mapping_value(evidence_payload, "artifact_hashes")
    checklist_hashes = _mapping_value(checklist_payload, "artifact_hashes")
    if evidence_hashes is None or checklist_hashes is None:
        return False
    return (
        _str_or_none(evidence_hashes.get("archive_sha256")) is not None
        and _str_or_none(evidence_hashes.get("archive_sha256")) == _str_or_none(checklist_hashes.get("archive_sha256"))
        and _str_or_none(evidence_hashes.get("inventory_sha256")) is not None
        and _str_or_none(evidence_hashes.get("inventory_sha256")) == _str_or_none(checklist_hashes.get("inventory_sha256"))
    )


def _checklist_evidence_hash_matches(
    checklist_payload: Mapping[str, object] | None,
    evidence_sha256: str | None,
) -> bool:
    checklist_hashes = _mapping_value(checklist_payload, "artifact_hashes")
    if checklist_hashes is None or evidence_sha256 is None:
        return False
    return _str_or_none(checklist_hashes.get("evidence_sha256")) == evidence_sha256


def _required_commands_match(
    evidence_payload: Mapping[str, object] | None,
    bundle_payload: Mapping[str, object] | None,
) -> bool:
    return _command_list(evidence_payload.get("required_validation_commands") if evidence_payload else None) == _bundle_required_commands(bundle_payload)


def _transcript_bundle_coverage_complete(bundle_payload: Mapping[str, object] | None) -> bool:
    summary = _mapping_value(bundle_payload, "summary")
    if summary is None:
        return False
    required = _optional_int(summary.get("required_command_count"))
    covered = _optional_int(summary.get("covered_command_count"))
    return required is not None and required > 0 and required == covered


def _transcript_bundle_coverage_detail(bundle_payload: Mapping[str, object] | None) -> str:
    summary = _mapping_value(bundle_payload, "summary") or {}
    return "covered={covered},required={required}".format(
        covered=summary.get("covered_command_count"),
        required=summary.get("required_command_count"),
    )


def _bundle_required_commands(bundle_payload: Mapping[str, object] | None) -> tuple[tuple[str, ...], ...]:
    if not bundle_payload:
        return ()
    value = bundle_payload.get("required_commands")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    commands: list[tuple[str, ...]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return ()
        command = _command_tuple(item.get("command"))
        if command is None:
            return ()
        commands.append(command)
    return tuple(commands)


def _command_list(value: object) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    commands: list[tuple[str, ...]] = []
    for item in value:
        command = _command_tuple(item)
        if command is None:
            return ()
        commands.append(command)
    return tuple(commands)


def _command_tuple(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if any(not isinstance(part, str) or not part.strip() for part in value):
        return None
    return tuple(value)


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
