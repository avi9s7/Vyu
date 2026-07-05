# Deployment Package Manifest

## Package Manifest Contract

The deployment package manifest is a local metadata contract for the first serverless-style packaging skeleton. It records which entrypoint should be packaged, which local files are intentionally included, which local-only or generated paths must be excluded, and which validation commands must pass before an operator treats the package boundary as ready for handoff.

Implemented files:

- `deploy/serverless/package.manifest.json`
- `src/vyu/deployment/package_manifest.py`
- `scripts/validate_deployment_package.py`
- `tests/test_deployment_package_manifest.py`

This is not cloud infrastructure. It does not create Lambda, Cloud Run, API Gateway, Terraform, CloudFormation, SAM, Serverless Framework, Docker, Kubernetes, IAM, CORS, WAF, TLS, or production OIDC/JWKS configuration.

## Manifest Fields

The checked-in manifest uses schema version `1` and includes:

| Field | Meaning |
| --- | --- |
| `schema_version` | Supported manifest schema version. |
| `package_name` | Local package boundary name. |
| `deployment_target` | Descriptive target such as `serverless-http`; not a cloud provider. |
| `runtime` | Runtime expectation, currently `python3.11`. |
| `handler` | Import path for the callable entrypoint, currently `apps.serverless.handler.handler`. |
| `operator_config_env_var` | Must be `VYU_DEPLOYMENT_ENV_FILE`. |
| `operator_config_example` | Checked-in non-secret template path. |
| `include_paths` | Source paths intended to be included in a package handoff. |
| `exclude_paths` | Local secret/generated/review paths that must not be packaged. |
| `required_validation_commands` | Operator commands that should pass before package handoff. |
| `infrastructure_managed_elsewhere` | Must remain `true`; this manifest is not infrastructure. |
| `secret_values_in_manifest` | Must remain `false`; real secrets must not be committed. |
| `notes` | Human-readable constraints and limitations. |

## Validation Checks

`validate_deployment_package_manifest(...)` and `scripts/validate_deployment_package.py` check:

- `schema_version_supported`
- `handler_importable`
- `operator_config_env_var`
- `operator_config_example_exists`
- `include_paths_exist`
- `local_secret_config_excluded`
- `infrastructure_managed_elsewhere`
- `secret_values_not_in_manifest`
- `validation_commands_present`

The validator prints JSON with a `pass` or `fail` status and per-check details.

## Operator Command

Run from the repository root:

```bash
python scripts/validate_deployment_package.py --manifest deploy/serverless/package.manifest.json
```

A passing result means the local package metadata is internally consistent. It does not mean the app has been deployed or security-reviewed in a cloud environment.

## Relationship to Earlier Deployment Modules

The package manifest sits above the existing deployment stack:

```text
deploy/serverless/package.manifest.json
  -> apps/serverless/handler.py
    -> DeploymentServerlessAppEntrypoint
      -> DeploymentOperatorConfig
        -> DeploymentCompositionConfig
          -> ServerlessDeploymentHandler
            -> DeploymentApiServiceShell
              -> ServiceDeploymentHttpAdapter
                -> ServiceRouteRuntime
```

The manifest deliberately references the operator config pointer `VYU_DEPLOYMENT_ENV_FILE` rather than storing secret values.

## Required Exclusions

The manifest must exclude:

- `config/deployment.local.env`
- `upstreams/`
- `.venv/`
- `__pycache__/`
- `*.pyc`

The `config/deployment.local.env` file may contain local secrets and must remain untracked and unpackaged.

## Current Limits

- No archive build command is implemented yet.
- No dependency pruning or reproducible wheel build is implemented yet.
- No container image, SBOM, vulnerability scan, or secret scan is implemented here.
- No cloud deployment descriptor is implemented here.
- No production identity-provider integration is implemented here.

## Next Module Boundary

The next deployment module should add a local package/archive builder or dry-run package planner that consumes this manifest and produces a deterministic package inventory without including local secrets or generated caches.
