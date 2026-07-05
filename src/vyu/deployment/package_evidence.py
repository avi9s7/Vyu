from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from src.vyu.deployment.package_archive import verify_deployment_package_archive
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

DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA = 1


class DeploymentPackageEvidenceError(RuntimeError):
    """Raised when deployment package evidence cannot be produced."""


@dataclass(frozen=True)
class DeploymentPackageEvidenceCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentPackageEvidence:
    created_at: str
    manifest_path: Path
    archive_path: Path
    inventory_path: Path
    package: dict[str, object]
    required_validation_commands: tuple[tuple[str, ...], ...]
    archive_sha256: str | None
    inventory_sha256: str | None
    manifest_validation: dict[str, object]
    archive_verification: dict[str, object]
    checks: tuple[DeploymentPackageEvidenceCheck, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return "complete" if all(check.passed for check in self.checks) else "failed"

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "schema_version": DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
            "status": self.status,
            "created_at": self.created_at,
            "manifest_path": str(self.manifest_path),
            "archive_path": str(self.archive_path),
            "inventory_path": str(self.inventory_path),
            "package": dict(self.package),
            "artifact_hashes": {
                "archive_sha256": self.archive_sha256,
                "inventory_sha256": self.inventory_sha256,
            },
            "required_validation_commands": [list(command) for command in self.required_validation_commands],
            "manifest_validation": self.manifest_validation,
            "archive_verification": self.archive_verification,
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


def build_deployment_package_evidence(
    manifest_path: Path,
    *,
    archive_path: Path,
    inventory_path: Path,
    root: Path = Path("."),
    created_at: str | None = None,
) -> DeploymentPackageEvidence:
    """Create unsigned local integrity/provenance evidence for a built archive."""

    root = Path(root)
    manifest_path = Path(manifest_path)
    archive_path = Path(archive_path)
    inventory_path = Path(inventory_path)
    created_at = _normalize_created_at(created_at)

    try:
        manifest = read_deployment_package_manifest(manifest_path)
        manifest_validation_result = validate_deployment_package_manifest(manifest_path, root=root)
    except DeploymentPackageManifestError as exc:
        raise DeploymentPackageEvidenceError(str(exc)) from exc

    package = {
        "schema_version": manifest.schema_version,
        "package_name": manifest.package_name,
        "deployment_target": manifest.deployment_target,
        "runtime": manifest.runtime,
        "handler": manifest.handler,
        "operator_config_env_var": manifest.operator_config_env_var,
    }
    checks: list[DeploymentPackageEvidenceCheck] = [
        DeploymentPackageEvidenceCheck(
            "manifest_validation_passed",
            manifest_validation_result.passed,
            manifest_validation_result.to_json()["status"],
        )
    ]

    plan: DeploymentPackagePlan | None = None
    if manifest_validation_result.passed:
        try:
            plan = build_deployment_package_plan(manifest_path, root=root)
        except DeploymentPackagePlanError as exc:
            raise DeploymentPackageEvidenceError(str(exc)) from exc

    archive_sha256 = _sha256(archive_path) if archive_path.is_file() else None
    inventory_sha256 = _inventory_sha256(plan) if plan is not None else None

    if plan is None:
        archive_verification = {
            "status": "skipped",
            "archive_path": str(archive_path),
            "reason": "manifest validation failed",
        }
        checks.extend(
            [
                DeploymentPackageEvidenceCheck("archive_sha256_present", False, str(archive_path)),
                DeploymentPackageEvidenceCheck("inventory_sha256_present", False, str(inventory_path)),
                DeploymentPackageEvidenceCheck("archive_verification_passed", False, "skipped"),
                DeploymentPackageEvidenceCheck("inventory_file_exists", inventory_path.is_file(), str(inventory_path)),
                DeploymentPackageEvidenceCheck("inventory_matches_plan", False, "skipped"),
            ]
        )
    else:
        archive_verification_result = verify_deployment_package_archive(
            plan,
            archive_path=archive_path,
            root=root,
        )
        inventory_match = _inventory_matches_plan(inventory_path, plan)
        archive_verification = archive_verification_result.to_json()
        checks.extend(
            [
                DeploymentPackageEvidenceCheck(
                    "archive_sha256_present",
                    archive_sha256 is not None,
                    str(archive_path),
                ),
                DeploymentPackageEvidenceCheck(
                    "inventory_sha256_present",
                    inventory_sha256 is not None,
                    str(inventory_path),
                ),
                DeploymentPackageEvidenceCheck(
                    "archive_verification_passed",
                    archive_verification_result.passed,
                    archive_verification["status"],
                ),
                DeploymentPackageEvidenceCheck(
                    "inventory_file_exists",
                    inventory_path.is_file(),
                    str(inventory_path),
                ),
                DeploymentPackageEvidenceCheck(
                    "inventory_matches_plan",
                    inventory_match,
                    str(inventory_path),
                ),
                DeploymentPackageEvidenceCheck(
                    "validation_commands_recorded",
                    len(manifest.required_validation_commands) > 0,
                    str(len(manifest.required_validation_commands)),
                ),
            ]
        )

    return DeploymentPackageEvidence(
        created_at=created_at,
        manifest_path=manifest_path,
        archive_path=archive_path,
        inventory_path=inventory_path,
        package=package,
        required_validation_commands=manifest.required_validation_commands,
        archive_sha256=archive_sha256,
        inventory_sha256=inventory_sha256,
        manifest_validation=manifest_validation_result.to_json(),
        archive_verification=archive_verification,
        checks=tuple(checks),
    )


def write_deployment_package_evidence(evidence: DeploymentPackageEvidence, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_created_at(value: str | None) -> str:
    if value is not None:
        value = value.strip()
        if not value:
            raise DeploymentPackageEvidenceError("created_at cannot be empty.")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory_sha256(plan: DeploymentPackagePlan) -> str:
    payload = json.dumps(plan.to_json(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inventory_matches_plan(path: Path, plan: DeploymentPackagePlan) -> bool:
    if not Path(path).is_file():
        return False
    try:
        payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return payload == plan.to_json()
