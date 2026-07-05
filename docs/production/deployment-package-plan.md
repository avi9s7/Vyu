# Deployment Package Plan

## Package Plan Contract

The deployment package planner consumes `deploy/serverless/package.manifest.json` and produces a deterministic JSON inventory of files that would be included in a local deployment package handoff.

Implemented files:

- `src/vyu/deployment/package_plan.py`
- `scripts/plan_deployment_package.py`
- `tests/test_deployment_package_plan.py`

This module does not create an archive yet. It is a dry-run inventory planner that verifies package contents before a later archive builder is added.

## Planner Behavior

`build_deployment_package_plan(...)` performs these steps:

1. Validates the manifest through `validate_deployment_package_manifest(...)`.
2. Expands files and directories listed in `include_paths`.
3. Applies manifest `exclude_paths` deterministically.
4. Sorts file paths lexicographically.
5. Records each file path, byte size, and SHA-256 digest.
6. Records excluded candidate paths such as `config/deployment.local.env`.
7. Returns a JSON-serializable `DeploymentPackagePlan`.

The planner excludes local-only or generated paths such as:

- `config/deployment.local.env`
- `upstreams/`
- `.venv/`
- `__pycache__/`
- `*.pyc`

## Operator Command

Run from the repository root:

```bash
python scripts/plan_deployment_package.py --manifest deploy/serverless/package.manifest.json --output outputs/deployment_package_inventory.json
```

The command prints the same JSON payload to stdout and writes it to the optional output path.

Expected status:

```json
{
  "status": "planned"
}
```

The summary includes:

- `file_count`
- `total_bytes`
- `excluded_count`

Each file entry includes:

- `path`
- `size_bytes`
- `sha256`

## Public Objects

`src/vyu/deployment/package_plan.py` exposes:

- `DeploymentPackagePlanError`
- `DeploymentPackageInventoryItem`
- `DeploymentPackagePlan`
- `build_deployment_package_plan(...)`
- `write_deployment_package_plan(...)`

## Relationship to Earlier Deployment Modules

The package plan sits above the package manifest and does not alter runtime behavior:

```text
scripts/plan_deployment_package.py
  -> DeploymentPackagePlan
    -> DeploymentPackageManifest
      -> apps/serverless/handler.py
        -> DeploymentServerlessAppEntrypoint
          -> DeploymentCompositionConfig
```

The planner does not read `VYU_HS256_SECRET`, does not parse `config/deployment.local.env`, and does not include local secret config files in its inventory.

## Current Limits

- No `.zip`, wheel, or container image is built here.
- No dependency pruning is performed.
- No SBOM, vulnerability scan, or secret scanner is implemented here.
- No cloud deployment descriptor is generated.
- No production identity-provider integration is configured.

## Next Module Boundary

The next deployment module should add a deterministic local archive builder that consumes the package plan and writes a package archive while preserving the same exclude rules and inventory checks.
