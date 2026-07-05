from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.vyu.deployment.package_archive import verify_deployment_package_archive
from src.vyu.deployment.package_evidence import DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA
from src.vyu.deployment.package_manifest import (
    DeploymentPackageManifestError,
    read_deployment_package_manifest,
    validate_deployment_package_manifest,
)
from src.vyu.deployment.package_plan import (
    DeploymentPackagePlan,
    DeploymentPackagePlanError,
    build_deployment_package_plan,
)

DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA = 1

REQUIRED_COMMAND_SCRIPT_MARKERS = (
    "scripts/validate_deployment_config.py",
    "scripts/validate_deployment_package.py",
    "scripts/plan_deployment_package.py",
    "scripts/build_deployment_archive.py",
    "scripts/write_deployment_package_evidence.py",
    "scripts/smoke_test_deployment.py",
)


class DeploymentReleasePackageError(RuntimeError):
    """Raised when a deployment release-package checklist cannot be produced."""


@dataclass(frozen=True)
class DeploymentReleasePackageCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentReleasePackageChecklist:
    created_at: str
    manifest_path: Path
    archive_path: Path
    inventory_path: Path
    evidence_path: Path
    package: dict[str, object]
    artifact_hashes: dict[str, str | None]
    required_command_coverage: dict[str, bool]
    manifest_validation: dict[str, object]
    archive_verification: dict[str, object]
    evidence: dict[str, object]
    checks: tuple[DeploymentReleasePackageCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "ready" if all(check.passed for check in self.checks) else "blocked"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "manifest_path": str(self.manifest_path),
            "archive_path": str(self.archive_path),
            "inventory_path": str(self.inventory_path),
            "evidence_path": str(self.evidence_path),
            "package": dict(self.package),
            "artifact_hashes": dict(self.artifact_hashes),
            "required_command_coverage": dict(self.required_command_coverage),
            "manifest_validation": self.manifest_validation,
            "archive_verification": self.archive_verification,
            "evidence": self.evidence,
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_release_package_checklist(
    manifest_path: Path,
    *,
    archive_path: Path,
    inventory_path: Path,
    evidence_path: Path,
    root: Path = Path("."),
    created_at: str | None = None,
) -> DeploymentReleasePackageChecklist:
    """Build a deterministic local release-package readiness checklist."""

    root = Path(root)
    manifest_path = Path(manifest_path)
    archive_path = Path(archive_path)
    inventory_path = Path(inventory_path)
    evidence_path = Path(evidence_path)
    created_at = _normalize_created_at(created_at)

    try:
        manifest = read_deployment_package_manifest(manifest_path)
        manifest_validation_result = validate_deployment_package_manifest(manifest_path, root=root)
    except DeploymentPackageManifestError as exc:
        raise DeploymentReleasePackageError(str(exc)) from exc

    package = {
        "schema_version": manifest.schema_version,
        "package_name": manifest.package_name,
        "deployment_target": manifest.deployment_target,
        "runtime": manifest.runtime,
        "handler": manifest.handler,
        "operator_config_env_var": manifest.operator_config_env_var,
    }
    command_coverage = _required_command_coverage(manifest.required_validation_commands)
    checks: list[DeploymentReleasePackageCheck] = [
        DeploymentReleasePackageCheck(
            "manifest_validation_passed",
            manifest_validation_result.passed,
            manifest_validation_result.to_json()["status"],
        ),
        DeploymentReleasePackageCheck(
            "required_command_coverage_complete",
            all(command_coverage.values()),
            _missing_command_detail(command_coverage),
        ),
    ]

    plan: DeploymentPackagePlan | None = None
    if manifest_validation_result.passed:
        try:
            plan = build_deployment_package_plan(manifest_path, root=root)
        except DeploymentPackagePlanError as exc:
            raise DeploymentReleasePackageError(str(exc)) from exc

    archive_sha256 = _sha256(archive_path) if archive_path.is_file() else None
    inventory_sha256 = _inventory_sha256(plan) if plan is not None else None
    evidence_sha256 = _sha256(evidence_path) if evidence_path.is_file() else None
    evidence_payload = _read_json_file(evidence_path)

    if plan is None:
        archive_verification = {
            "status": "skipped",
            "archive_path": str(archive_path),
            "reason": "manifest validation failed",
        }
        inventory_matches_plan = False
    else:
        archive_verification_result = verify_deployment_package_archive(
            plan,
            archive_path=archive_path,
            root=root,
        )
        archive_verification = archive_verification_result.to_json()
        inventory_matches_plan = _inventory_matches_plan(inventory_path, plan)
        checks.extend(
            [
                DeploymentReleasePackageCheck(
                    "archive_file_exists",
                    archive_path.is_file(),
                    str(archive_path),
                ),
                DeploymentReleasePackageCheck(
                    "inventory_file_exists",
                    inventory_path.is_file(),
                    str(inventory_path),
                ),
                DeploymentReleasePackageCheck(
                    "archive_verification_passed",
                    archive_verification_result.passed,
                    archive_verification["status"],
                ),
                DeploymentReleasePackageCheck(
                    "inventory_matches_plan",
                    inventory_matches_plan,
                    str(inventory_path),
                ),
            ]
        )

    evidence_checks = _evidence_checks(
        evidence_payload,
        manifest_path=manifest_path,
        archive_path=archive_path,
        inventory_path=inventory_path,
        expected_archive_sha256=archive_sha256,
        expected_inventory_sha256=inventory_sha256,
    )
    checks.extend(evidence_checks)

    return DeploymentReleasePackageChecklist(
        created_at=created_at,
        manifest_path=manifest_path,
        archive_path=archive_path,
        inventory_path=inventory_path,
        evidence_path=evidence_path,
        package=package,
        artifact_hashes={
            "archive_sha256": archive_sha256,
            "inventory_sha256": inventory_sha256,
            "evidence_sha256": evidence_sha256,
        },
        required_command_coverage=command_coverage,
        manifest_validation=manifest_validation_result.to_json(),
        archive_verification=archive_verification,
        evidence=_evidence_summary(evidence_payload, evidence_path=evidence_path),
        checks=tuple(checks),
    )


def write_deployment_release_package_checklist(
    checklist: DeploymentReleasePackageChecklist,
    output_path: Path,
) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(checklist.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentReleasePackageError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _required_command_coverage(commands: Sequence[Sequence[str]]) -> dict[str, bool]:
    command_strings = [" ".join(str(part) for part in command) for command in commands]
    return {
        marker: any(marker in command for command in command_strings)
        for marker in REQUIRED_COMMAND_SCRIPT_MARKERS
    }


def _missing_command_detail(coverage: Mapping[str, bool]) -> str:
    missing = [marker for marker, present in coverage.items() if not present]
    return "missing=" + ",".join(missing) if missing else "complete"


def _evidence_checks(
    evidence_payload: Any,
    *,
    manifest_path: Path,
    archive_path: Path,
    inventory_path: Path,
    expected_archive_sha256: str | None,
    expected_inventory_sha256: str | None,
) -> tuple[DeploymentReleasePackageCheck, ...]:
    if not isinstance(evidence_payload, Mapping):
        return (
            DeploymentReleasePackageCheck("evidence_file_exists", False, "missing or invalid JSON"),
            DeploymentReleasePackageCheck("evidence_status_complete", False, "missing or invalid JSON"),
            DeploymentReleasePackageCheck("evidence_schema_supported", False, "missing or invalid JSON"),
            DeploymentReleasePackageCheck("evidence_paths_match_inputs", False, "missing or invalid JSON"),
            DeploymentReleasePackageCheck("evidence_hashes_match_artifacts", False, "missing or invalid JSON"),
            DeploymentReleasePackageCheck("evidence_archive_verification_passed", False, "missing or invalid JSON"),
        )

    artifact_hashes = evidence_payload.get("artifact_hashes")
    if not isinstance(artifact_hashes, Mapping):
        artifact_hashes = {}
    archive_verification = evidence_payload.get("archive_verification")
    if not isinstance(archive_verification, Mapping):
        archive_verification = {}

    paths_match = (
        str(evidence_payload.get("manifest_path")) == str(manifest_path)
        and str(evidence_payload.get("archive_path")) == str(archive_path)
        and str(evidence_payload.get("inventory_path")) == str(inventory_path)
    )
    hashes_match = (
        artifact_hashes.get("archive_sha256") == expected_archive_sha256
        and artifact_hashes.get("inventory_sha256") == expected_inventory_sha256
    )
    return (
        DeploymentReleasePackageCheck("evidence_file_exists", True, "loaded"),
        DeploymentReleasePackageCheck(
            "evidence_status_complete",
            evidence_payload.get("status") == "complete",
            str(evidence_payload.get("status")),
        ),
        DeploymentReleasePackageCheck(
            "evidence_schema_supported",
            evidence_payload.get("schema_version") == DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
            f"schema_version={evidence_payload.get('schema_version')}",
        ),
        DeploymentReleasePackageCheck(
            "evidence_paths_match_inputs",
            paths_match,
            f"manifest={evidence_payload.get('manifest_path')} archive={evidence_payload.get('archive_path')} inventory={evidence_payload.get('inventory_path')}",
        ),
        DeploymentReleasePackageCheck(
            "evidence_hashes_match_artifacts",
            hashes_match,
            "archive_sha256, inventory_sha256",
        ),
        DeploymentReleasePackageCheck(
            "evidence_archive_verification_passed",
            archive_verification.get("status") == "pass",
            str(archive_verification.get("status")),
        ),
    )


def _evidence_summary(evidence_payload: Any, *, evidence_path: Path) -> dict[str, object]:
    if not isinstance(evidence_payload, Mapping):
        return {"path": str(evidence_path), "status": "missing_or_invalid"}
    artifact_hashes = evidence_payload.get("artifact_hashes")
    archive_verification = evidence_payload.get("archive_verification")
    return {
        "path": str(evidence_path),
        "schema_version": evidence_payload.get("schema_version"),
        "status": evidence_payload.get("status"),
        "created_at": evidence_payload.get("created_at"),
        "artifact_hashes": artifact_hashes if isinstance(artifact_hashes, Mapping) else {},
        "archive_verification_status": archive_verification.get("status")
        if isinstance(archive_verification, Mapping)
        else None,
    }


def _read_json_file(path: Path) -> Any:
    if not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _inventory_matches_plan(path: Path, plan: DeploymentPackagePlan) -> bool:
    payload = _read_json_file(path)
    return payload == plan.to_json()


def _inventory_sha256(plan: DeploymentPackagePlan | None) -> str | None:
    if plan is None:
        return None
    payload = json.dumps(plan.to_json(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
