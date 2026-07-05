from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Iterable

from src.vyu.deployment.package_manifest import (
    DeploymentPackageManifest,
    read_deployment_package_manifest,
    validate_deployment_package_manifest,
)


class DeploymentPackagePlanError(RuntimeError):
    """Raised when a deterministic deployment package plan cannot be produced."""


@dataclass(frozen=True)
class DeploymentPackageInventoryItem:
    path: Path
    size_bytes: int
    sha256: str

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path.as_posix(),
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class DeploymentPackagePlan:
    manifest_path: Path
    package_name: str
    runtime: str
    handler: str
    operator_config_env_var: str
    files: tuple[DeploymentPackageInventoryItem, ...] = field(default_factory=tuple)
    excluded_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)

    def to_json(self) -> dict[str, object]:
        return {
            "status": "planned",
            "manifest_path": str(self.manifest_path),
            "package_name": self.package_name,
            "runtime": self.runtime,
            "handler": self.handler,
            "operator_config_env_var": self.operator_config_env_var,
            "summary": {
                "file_count": len(self.files),
                "total_bytes": self.total_bytes,
                "excluded_count": len(self.excluded_paths),
            },
            "files": [item.to_json() for item in self.files],
            "excluded_paths": [path.as_posix() for path in self.excluded_paths],
        }


def build_deployment_package_plan(
    manifest_path: Path,
    *,
    root: Path = Path("."),
) -> DeploymentPackagePlan:
    """Build a deterministic package inventory from a validated manifest."""

    root = Path(root)
    manifest_path = Path(manifest_path)
    validation = validate_deployment_package_manifest(manifest_path, root=root)
    if not validation.passed:
        failed = [check.name for check in validation.checks if not check.passed]
        raise DeploymentPackagePlanError(
            "Deployment package manifest validation failed: " + ", ".join(failed)
        )
    manifest = read_deployment_package_manifest(manifest_path)
    files, excluded = _collect_inventory(manifest, root=root)
    if not files:
        raise DeploymentPackagePlanError("Deployment package plan did not include any files.")
    return DeploymentPackagePlan(
        manifest_path=manifest_path,
        package_name=manifest.package_name,
        runtime=manifest.runtime,
        handler=manifest.handler,
        operator_config_env_var=manifest.operator_config_env_var,
        files=tuple(files),
        excluded_paths=tuple(excluded),
    )


def write_deployment_package_plan(plan: DeploymentPackagePlan, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan.to_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _collect_inventory(
    manifest: DeploymentPackageManifest,
    *,
    root: Path,
) -> tuple[list[DeploymentPackageInventoryItem], list[Path]]:
    candidates: set[Path] = set()
    excluded: set[Path] = set()
    for include_path in manifest.include_paths:
        absolute = root / include_path
        if absolute.is_file():
            candidates.add(include_path)
        elif absolute.is_dir():
            for file_path in _iter_files(absolute):
                candidates.add(file_path.relative_to(root))

    files: list[DeploymentPackageInventoryItem] = []
    for relative in sorted(candidates, key=lambda path: path.as_posix()):
        if _is_excluded(relative, manifest.exclude_paths):
            excluded.add(relative)
            continue
        absolute = root / relative
        if not absolute.is_file():
            continue
        files.append(
            DeploymentPackageInventoryItem(
                path=relative,
                size_bytes=absolute.stat().st_size,
                sha256=_sha256(absolute),
            )
        )
    return files, sorted(excluded, key=lambda path: path.as_posix())


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _is_excluded(relative_path: Path, exclude_paths: tuple[Path, ...]) -> bool:
    rel = relative_path.as_posix()
    parts = set(relative_path.parts)
    for exclude in exclude_paths:
        pattern = exclude.as_posix()
        if pattern in parts:
            return True
        if rel == pattern or rel.startswith(pattern.rstrip("/") + "/"):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatch(rel, pattern):
            return True
        if any(char in pattern for char in "*?[") and fnmatch.fnmatch(relative_path.name, pattern):
            return True
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
