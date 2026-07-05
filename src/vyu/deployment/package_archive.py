from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import zipfile

from src.vyu.deployment.package_plan import (
    DeploymentPackagePlan,
    DeploymentPackagePlanError,
    build_deployment_package_plan,
    write_deployment_package_plan,
)

DETERMINISTIC_ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)


class DeploymentPackageArchiveError(RuntimeError):
    """Raised when a deterministic deployment archive cannot be built."""


@dataclass(frozen=True)
class DeploymentPackageArchiveCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentPackageArchiveVerification:
    archive_path: Path
    checks: tuple[DeploymentPackageArchiveCheck, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "status": "pass" if failed == 0 else "fail",
            "archive_path": str(self.archive_path),
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


@dataclass(frozen=True)
class DeploymentPackageArchive:
    archive_path: Path
    manifest_path: Path
    package_name: str
    file_count: int
    total_bytes: int
    archive_sha256: str
    inventory_sha256: str
    verification: DeploymentPackageArchiveVerification

    def to_json(self) -> dict[str, object]:
        return {
            "status": "built" if self.verification.passed else "verification_failed",
            "archive_path": str(self.archive_path),
            "manifest_path": str(self.manifest_path),
            "package_name": self.package_name,
            "summary": {
                "file_count": self.file_count,
                "total_bytes": self.total_bytes,
            },
            "archive_sha256": self.archive_sha256,
            "inventory_sha256": self.inventory_sha256,
            "verification": self.verification.to_json(),
        }


def build_deployment_package_archive(
    manifest_path: Path,
    *,
    archive_path: Path,
    root: Path = Path("."),
    inventory_output_path: Path | None = None,
) -> DeploymentPackageArchive:
    """Build a deterministic local zip archive from the package plan."""

    root = Path(root)
    archive_path = Path(archive_path)
    try:
        plan = build_deployment_package_plan(manifest_path, root=root)
    except DeploymentPackagePlanError as exc:
        raise DeploymentPackageArchiveError(str(exc)) from exc
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if inventory_output_path is not None:
        write_deployment_package_plan(plan, inventory_output_path)
    _write_zip(plan, root=root, archive_path=archive_path)
    verification = verify_deployment_package_archive(plan, archive_path=archive_path, root=root)
    if not verification.passed:
        failed = [check.name for check in verification.checks if not check.passed]
        raise DeploymentPackageArchiveError(
            "Deployment package archive verification failed: " + ", ".join(failed)
        )
    return DeploymentPackageArchive(
        archive_path=archive_path,
        manifest_path=Path(manifest_path),
        package_name=plan.package_name,
        file_count=len(plan.files),
        total_bytes=plan.total_bytes,
        archive_sha256=_sha256(archive_path),
        inventory_sha256=_inventory_sha256(plan),
        verification=verification,
    )


def verify_deployment_package_archive(
    plan: DeploymentPackagePlan,
    *,
    archive_path: Path,
    root: Path = Path("."),
) -> DeploymentPackageArchiveVerification:
    archive_path = Path(archive_path)
    checks: list[DeploymentPackageArchiveCheck] = []
    if not archive_path.is_file():
        return DeploymentPackageArchiveVerification(
            archive_path=archive_path,
            checks=(
                DeploymentPackageArchiveCheck(
                    "archive_exists",
                    False,
                    str(archive_path),
                ),
            ),
        )

    planned_paths = [item.path.as_posix() for item in plan.files]
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            entry_names = archive.namelist()
            entry_hashes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in entry_names}
    except zipfile.BadZipFile:
        return DeploymentPackageArchiveVerification(
            archive_path=archive_path,
            checks=(DeploymentPackageArchiveCheck("archive_readable", False, "bad zip file"),),
        )

    planned_hashes = {item.path.as_posix(): item.sha256 for item in plan.files}
    checks.extend(
        [
            DeploymentPackageArchiveCheck("archive_exists", True, str(archive_path)),
            DeploymentPackageArchiveCheck(
                "entries_match_plan",
                entry_names == planned_paths,
                f"entries={len(entry_names)} planned={len(planned_paths)}",
            ),
            DeploymentPackageArchiveCheck(
                "entry_hashes_match_plan",
                entry_hashes == planned_hashes,
                f"entries={len(entry_hashes)} planned={len(planned_hashes)}",
            ),
            DeploymentPackageArchiveCheck(
                "local_secret_config_absent",
                "config/deployment.local.env" not in entry_names,
                "config/deployment.local.env",
            ),
            DeploymentPackageArchiveCheck(
                "generated_caches_absent",
                not any("__pycache__" in name or name.endswith(".pyc") for name in entry_names),
                "__pycache__, *.pyc",
            ),
        ]
    )
    return DeploymentPackageArchiveVerification(archive_path=archive_path, checks=tuple(checks))


def _write_zip(plan: DeploymentPackagePlan, *, root: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in plan.files:
            relative = item.path.as_posix()
            data = (root / item.path).read_bytes()
            info = zipfile.ZipInfo(relative, date_time=DETERMINISTIC_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory_sha256(plan: DeploymentPackagePlan) -> str:
    payload = json.dumps(plan.to_json(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
