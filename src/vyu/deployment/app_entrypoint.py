from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable, Mapping

from src.vyu.deployment.composition import (
    DeploymentCompositionError,
    DeploymentRuntimeBundle,
    build_deployment_runtime,
)
from src.vyu.deployment.operator_config import (
    DeploymentOperatorConfig,
    DeploymentOperatorConfigError,
    load_deployment_operator_env,
)

DEPLOYMENT_ENV_FILE_ENV_VAR = "VYU_DEPLOYMENT_ENV_FILE"


class DeploymentAppEntrypointError(RuntimeError):
    """Raised when the packaged deployment entrypoint cannot be configured."""


@dataclass(frozen=True)
class DeploymentAppEntrypointConfig:
    """Configuration for a dependency-free deployment app entrypoint.

    The entrypoint reads one explicit operator config file and composes the
    existing local deployment runtime graph. It intentionally does not define
    cloud infrastructure, IAM, rate limits, or production identity-provider
    settings.
    """

    operator_env_file: Path
    cache_runtime: bool = True
    default_request_id: str = "deployment-entrypoint"

    def validate(self) -> None:
        if str(self.operator_env_file).strip() == "":
            raise DeploymentAppEntrypointError("operator_env_file is required.")
        if not self.default_request_id.strip():
            raise DeploymentAppEntrypointError("default_request_id is required.")


class DeploymentServerlessAppEntrypoint:
    """Callable app entrypoint that lazily builds the serverless runtime.

    This object is suitable for tests and for thin framework/cloud packaging
    files. It loads the operator config on first request, builds the composed
    runtime, and delegates events to the already-tested serverless handler.
    """

    def __init__(
        self,
        config: DeploymentAppEntrypointConfig,
        *,
        config_loader: Callable[[Path], DeploymentOperatorConfig] = load_deployment_operator_env,
        runtime_builder: Callable[[object], DeploymentRuntimeBundle] = build_deployment_runtime,
    ) -> None:
        config.validate()
        self.config = config
        self._config_loader = config_loader
        self._runtime_builder = runtime_builder
        self._bundle: DeploymentRuntimeBundle | None = None

    def __call__(self, event: object, context: object | None = None) -> dict[str, object]:
        return self.handle(event, context)

    def handle(self, event: object, context: object | None = None) -> dict[str, object]:
        try:
            bundle = self._runtime_bundle()
        except (DeploymentAppEntrypointError, DeploymentOperatorConfigError, DeploymentCompositionError, OSError):
            return deployment_entrypoint_error_response(
                event,
                reason="deployment_entrypoint_config_error",
                detail="Deployment entrypoint configuration is invalid or unavailable.",
                default_request_id=self.config.default_request_id,
            )
        return bundle.serverless_handler.handle(event, context)

    def _runtime_bundle(self) -> DeploymentRuntimeBundle:
        if self.config.cache_runtime and self._bundle is not None:
            return self._bundle
        try:
            operator_config = self._config_loader(self.config.operator_env_file)
            bundle = self._runtime_builder(operator_config.to_composition_config())
        except (DeploymentOperatorConfigError, DeploymentCompositionError, OSError):
            raise
        except Exception as exc:  # pragma: no cover - concrete deployment errors vary.
            raise DeploymentAppEntrypointError("Unable to build deployment runtime.") from exc
        if self.config.cache_runtime:
            self._bundle = bundle
        return bundle

    def clear_cached_runtime(self) -> None:
        """Clear cached runtime state for deterministic local tests."""

        self._bundle = None


def create_serverless_app_from_env_file(
    env_file: Path,
    *,
    cache_runtime: bool = True,
    default_request_id: str = "deployment-entrypoint",
) -> DeploymentServerlessAppEntrypoint:
    """Create a callable serverless app from an explicit operator config file."""

    return DeploymentServerlessAppEntrypoint(
        DeploymentAppEntrypointConfig(
            operator_env_file=Path(env_file),
            cache_runtime=cache_runtime,
            default_request_id=default_request_id,
        )
    )


def operator_env_file_from_environ(
    environ: Mapping[str, str] | None = None,
    *,
    env_var: str = DEPLOYMENT_ENV_FILE_ENV_VAR,
) -> Path:
    """Resolve the operator config path from an explicit environment mapping."""

    values = os.environ if environ is None else environ
    raw_path = str(values.get(env_var, "")).strip()
    if not raw_path:
        raise DeploymentAppEntrypointError(f"{env_var} must point to an operator config file.")
    return Path(raw_path)


def create_serverless_app_from_process_env(
    environ: Mapping[str, str] | None = None,
    *,
    env_var: str = DEPLOYMENT_ENV_FILE_ENV_VAR,
    cache_runtime: bool = True,
    default_request_id: str = "deployment-entrypoint",
) -> DeploymentServerlessAppEntrypoint:
    """Create the serverless app described by a process-env file pointer."""

    return create_serverless_app_from_env_file(
        operator_env_file_from_environ(environ, env_var=env_var),
        cache_runtime=cache_runtime,
        default_request_id=default_request_id,
    )


def deployment_entrypoint_error_response(
    event: object,
    *,
    reason: str,
    detail: str,
    default_request_id: str = "deployment-entrypoint",
) -> dict[str, object]:
    """Return a stable API Gateway-style error envelope for packaging failures."""

    request_id = _request_id_from_event(event) or default_request_id
    body = {
        "request_id": request_id,
        "audit_correlation_id": request_id,
        "status": "error",
        "reason": reason,
        "error": {
            "reason": reason,
            "detail": detail,
        },
        "data": {
            "reason": reason,
            "detail": detail,
        },
    }
    return {
        "statusCode": 500,
        "headers": {
            "content-type": "application/json",
            "x-vyu-request-id": request_id,
        },
        "body": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "isBase64Encoded": False,
    }


def _request_id_from_event(event: object) -> str | None:
    if not isinstance(event, Mapping):
        return None
    headers = event.get("headers")
    if isinstance(headers, Mapping):
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        request_id = normalized.get("x-vyu-request-id")
        if request_id:
            return request_id
    request_context = event.get("requestContext")
    if isinstance(request_context, Mapping):
        request_id = request_context.get("requestId")
        if request_id:
            return str(request_id)
    return None
