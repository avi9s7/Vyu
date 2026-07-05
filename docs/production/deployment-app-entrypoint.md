# Deployment App Entrypoint

## App Entrypoint Contract

The deployment app entrypoint is the first concrete packaging example for the local deployment graph. It is intentionally dependency-free and does not add a web framework, cloud SDK, infrastructure-as-code, IAM policy, WAF, rate limiter, or production identity-provider integration.

The implemented files are:

- `src/vyu/deployment/app_entrypoint.py`
- `apps/serverless/handler.py`
- `tests/test_deployment_app_entrypoint.py`

The entrypoint consumes the operator config created in `config/deployment.local.example.env` through the `VYU_DEPLOYMENT_ENV_FILE` environment variable.

```bash
export VYU_DEPLOYMENT_ENV_FILE=config/deployment.local.env
```

The packaged handler is:

```python
from apps.serverless.handler import handler
```

The handler accepts API Gateway-style HTTP events and delegates to the existing composed runtime:

```text
apps/serverless/handler.py
  -> DeploymentServerlessAppEntrypoint
    -> DeploymentOperatorConfig
      -> DeploymentCompositionConfig
        -> ServerlessDeploymentHandler
          -> DeploymentApiServiceShell
            -> ServiceDeploymentHttpAdapter
              -> ServiceRouteRuntime
```

## Public Objects

`src/vyu/deployment/app_entrypoint.py` exposes:

- `DEPLOYMENT_ENV_FILE_ENV_VAR`
- `DeploymentAppEntrypointConfig`
- `DeploymentAppEntrypointError`
- `DeploymentServerlessAppEntrypoint`
- `create_serverless_app_from_env_file(...)`
- `create_serverless_app_from_process_env(...)`
- `operator_env_file_from_environ(...)`
- `deployment_entrypoint_error_response(...)`

`apps/serverless/handler.py` exposes:

- `handler(event, context=None)`
- `reset_cached_app_for_tests()`

`reset_cached_app_for_tests()` is only for deterministic local tests.

## Configuration Behavior

The app entrypoint reads only one process-environment setting:

```text
VYU_DEPLOYMENT_ENV_FILE
```

That value must point to an untracked operator config file such as `config/deployment.local.env`. The operator config parser still validates the `.env` contents and rejects placeholder secrets by default.

The app entrypoint does not print `VYU_HS256_SECRET` and does not include secret values in error envelopes.

## Runtime Caching

`DeploymentServerlessAppEntrypoint` caches the composed runtime by default after the first successful request. This matches common serverless warm-start behavior and avoids rebuilding storage, route runtimes, identity mapping, and authenticators on every event.

Caching can be disabled for local validation:

```python
from pathlib import Path

from src.vyu.deployment import create_serverless_app_from_env_file

app = create_serverless_app_from_env_file(
    Path("config/deployment.local.env"),
    cache_runtime=False,
)
```

## Fail-Closed Behavior

If `VYU_DEPLOYMENT_ENV_FILE` is missing, points to an unreadable file, or the file contains invalid operator settings, the packaged handler returns a stable API Gateway-style `500` JSON envelope:

```json
{
  "status": "error",
  "reason": "deployment_entrypoint_config_error"
}
```

The entrypoint preserves an incoming `x-vyu-request-id` when present, otherwise it uses a local default request ID.

## Local Verification

Use the operator config validator before invoking the packaged handler:

```bash
python scripts/validate_deployment_config.py --env-file config/deployment.local.env
```

Then invoke the packaged handler in tests or a local function harness with:

```bash
export VYU_DEPLOYMENT_ENV_FILE=config/deployment.local.env
```

Run the focused regression tests:

```bash
python -m unittest tests.test_deployment_app_entrypoint tests.test_deployment_operator_config tests.test_deployment_smoke -v
```

## Not Implemented Here

This module does not implement:

- deployed API Gateway/Lambda/Cloud Run infrastructure
- production OIDC/SAML/JWKS integration
- real secret-manager integration
- container build manifests
- framework-specific FastAPI or Flask app startup
- CORS/rate-limit/WAF middleware
- long-running workflow workers
