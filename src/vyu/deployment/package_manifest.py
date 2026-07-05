from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from src.vyu.deployment.app_entrypoint import DEPLOYMENT_ENV_FILE_ENV_VAR

SUPPORTED_PACKAGE_MANIFEST_SCHEMA = 1


class DeploymentPackageManifestError(ValueError):
    """Raised when deployment package metadata is malformed."""


@dataclass(frozen=True)
class DeploymentPackageValidationCheck:
    name: str
    passed: bool
    detail: str

    def to_json(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentPackageValidationResult:
    manifest_path: Path
    package_name: str
    checks: tuple[DeploymentPackageValidationCheck, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_json(self) -> dict[str, object]:
        passed = sum(1 for check in self.checks if check.passed)
        failed = len(self.checks) - passed
        return {
            "status": "pass" if failed == 0 else "fail",
            "manifest_path": str(self.manifest_path),
            "package_name": self.package_name,
            "summary": {"passed": passed, "failed": failed, "total": len(self.checks)},
            "checks": [check.to_json() for check in self.checks],
        }


@dataclass(frozen=True)
class DeploymentPackageManifest:
    """Minimal metadata contract for packaging the local serverless entrypoint.

    This manifest describes what to package and what to validate. It is not a
    cloud deployment descriptor and intentionally excludes infrastructure,
    secret values, IAM, CORS, WAF, rate limits, and production identity-provider
    configuration.
    """

    schema_version: int
    package_name: str
    deployment_target: str
    runtime: str
    handler: str
    operator_config_env_var: str
    operator_config_example: Path
    include_paths: tuple[Path, ...]
    exclude_paths: tuple[Path, ...]
    required_validation_commands: tuple[tuple[str, ...], ...]
    infrastructure_managed_elsewhere: bool
    secret_values_in_manifest: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> "DeploymentPackageManifest":
        required = (
            "schema_version",
            "package_name",
            "deployment_target",
            "runtime",
            "handler",
            "operator_config_env_var",
            "operator_config_example",
            "include_paths",
            "exclude_paths",
            "required_validation_commands",
            "infrastructure_managed_elsewhere",
            "secret_values_in_manifest",
        )
        missing = [key for key in required if key not in mapping]
        if missing:
            raise DeploymentPackageManifestError(
                "Missing deployment package manifest fields: " + ", ".join(missing)
            )
        return cls(
            schema_version=_int_field(mapping, "schema_version"),
            package_name=_str_field(mapping, "package_name"),
            deployment_target=_str_field(mapping, "deployment_target"),
            runtime=_str_field(mapping, "runtime"),
            handler=_str_field(mapping, "handler"),
            operator_config_env_var=_str_field(mapping, "operator_config_env_var"),
            operator_config_example=Path(_str_field(mapping, "operator_config_example")),
            include_paths=_path_tuple(mapping, "include_paths"),
            exclude_paths=_path_tuple(mapping, "exclude_paths"),
            required_validation_commands=_command_tuple(mapping, "required_validation_commands"),
            infrastructure_managed_elsewhere=_bool_field(mapping, "infrastructure_managed_elsewhere"),
            secret_values_in_manifest=_bool_field(mapping, "secret_values_in_manifest"),
            notes=tuple(str(item) for item in _sequence_field(mapping, "notes", required=False)),
        )

    def validate(self, *, root: Path, manifest_path: Path) -> DeploymentPackageValidationResult:
        root = Path(root)
        checks = [
            _check(
                "schema_version_supported",
                self.schema_version == SUPPORTED_PACKAGE_MANIFEST_SCHEMA,
                f"schema_version={self.schema_version}",
            ),
            _check(
                "handler_importable",
                _handler_importable(self.handler),
                self.handler,
            ),
            _check(
                "operator_config_env_var",
                self.operator_config_env_var == DEPLOYMENT_ENV_FILE_ENV_VAR,
                self.operator_config_env_var,
            ),
            _check(
                "operator_config_example_exists",
                (root / self.operator_config_example).is_file(),
                str(self.operator_config_example),
            ),
            _check(
                "include_paths_exist",
                all((root / path).exists() for path in self.include_paths),
                ", ".join(str(path) for path in self.include_paths),
            ),
            _check(
                "local_secret_config_excluded",
                Path("config/deployment.local.env") in self.exclude_paths,
                ", ".join(str(path) for path in self.exclude_paths),
            ),
            _check(
                "infrastructure_managed_elsewhere",
                self.infrastructure_managed_elsewhere,
                str(self.infrastructure_managed_elsewhere),
            ),
            _check(
                "secret_values_not_in_manifest",
                not self.secret_values_in_manifest,
                str(self.secret_values_in_manifest),
            ),
            _check(
                "validation_commands_present",
                len(self.required_validation_commands) >= 3,
                str(len(self.required_validation_commands)),
            ),
        ]
        return DeploymentPackageValidationResult(
            manifest_path=Path(manifest_path),
            package_name=self.package_name,
            checks=tuple(checks),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_name": self.package_name,
            "deployment_target": self.deployment_target,
            "runtime": self.runtime,
            "handler": self.handler,
            "operator_config_env_var": self.operator_config_env_var,
            "operator_config_example": self.operator_config_example.as_posix(),
            "include_paths": [path.as_posix() for path in self.include_paths],
            "exclude_paths": [path.as_posix() for path in self.exclude_paths],
            "required_validation_commands": [list(command) for command in self.required_validation_commands],
            "infrastructure_managed_elsewhere": self.infrastructure_managed_elsewhere,
            "secret_values_in_manifest": self.secret_values_in_manifest,
            "notes": list(self.notes),
        }


def read_deployment_package_manifest(path: Path) -> DeploymentPackageManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeploymentPackageManifestError(f"Invalid JSON deployment package manifest: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise DeploymentPackageManifestError("Deployment package manifest must be a JSON object.")
    return DeploymentPackageManifest.from_mapping(payload)


def validate_deployment_package_manifest(
    manifest_path: Path,
    *,
    root: Path = Path("."),
) -> DeploymentPackageValidationResult:
    manifest = read_deployment_package_manifest(manifest_path)
    return manifest.validate(root=Path(root), manifest_path=Path(manifest_path))


def _check(name: str, passed: bool, detail: str) -> DeploymentPackageValidationCheck:
    return DeploymentPackageValidationCheck(name=name, passed=passed, detail=detail)


def _handler_importable(handler: str) -> bool:
    module_name, separator, attribute_name = handler.rpartition(".")
    if not separator or not module_name or not attribute_name:
        return False
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return callable(getattr(module, attribute_name, None))


def _int_field(mapping: Mapping[str, object], key: str) -> int:
    try:
        return int(str(mapping[key]))
    except (TypeError, ValueError) as exc:
        raise DeploymentPackageManifestError(f"{key} must be an integer.") from exc


def _bool_field(mapping: Mapping[str, object], key: str) -> bool:
    value = mapping[key]
    if isinstance(value, bool):
        return value
    raise DeploymentPackageManifestError(f"{key} must be a boolean.")


def _str_field(mapping: Mapping[str, object], key: str) -> str:
    value = str(mapping[key]).strip()
    if not value:
        raise DeploymentPackageManifestError(f"{key} cannot be empty.")
    return value


def _path_tuple(mapping: Mapping[str, object], key: str) -> tuple[Path, ...]:
    return tuple(Path(str(item)) for item in _sequence_field(mapping, key))


def _command_tuple(mapping: Mapping[str, object], key: str) -> tuple[tuple[str, ...], ...]:
    commands = []
    for command in _sequence_field(mapping, key):
        if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
            raise DeploymentPackageManifestError(f"{key} must contain command arrays.")
        values = tuple(str(item) for item in command)
        if not values:
            raise DeploymentPackageManifestError(f"{key} cannot contain empty commands.")
        commands.append(values)
    return tuple(commands)


def _sequence_field(
    mapping: Mapping[str, object],
    key: str,
    *,
    required: bool = True,
) -> Sequence[object]:
    if key not in mapping:
        if required:
            raise DeploymentPackageManifestError(f"{key} is required.")
        return ()
    value = mapping[key]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DeploymentPackageManifestError(f"{key} must be a list.")
    return value
