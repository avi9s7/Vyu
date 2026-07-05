from __future__ import annotations

from src.vyu.deployment.app_entrypoint import (
    DeploymentAppEntrypointError,
    DeploymentServerlessAppEntrypoint,
    create_serverless_app_from_process_env,
    deployment_entrypoint_error_response,
)

_APP: DeploymentServerlessAppEntrypoint | None = None


def handler(event: object, context: object | None = None) -> dict[str, object]:
    """Serverless function entrypoint example.

    Configure the function runtime with VYU_DEPLOYMENT_ENV_FILE pointing to an
    untracked operator config file. This file is a packaging shim only; Vyu's
    authentication, identity mapping, route dispatch, and response envelopes
    remain in src/vyu/deployment and src/vyu/entrypoints.
    """

    global _APP
    if _APP is None:
        try:
            _APP = create_serverless_app_from_process_env()
        except DeploymentAppEntrypointError:
            return deployment_entrypoint_error_response(
                event,
                reason="deployment_entrypoint_config_error",
                detail="VYU_DEPLOYMENT_ENV_FILE is not configured for this deployment entrypoint.",
            )
    return _APP.handle(event, context)


def reset_cached_app_for_tests() -> None:
    """Reset the lazy app cache for deterministic local tests."""

    global _APP
    _APP = None
