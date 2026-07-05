# Deployment Package Archive

## Archive Builder Contract

The deployment package archive builder consumes the deterministic package plan and writes a reproducible local zip archive. It is the first archive-writing packaging boundary for the serverless entrypoint, but it still does not deploy anything to cloud infrastructure.

Implemented files:

- `src/vyu/deployment/package_archive.py`
- `scripts/build_deployment_archive.py`
- `tests/test_deployment_package_archive.py`

The builder preserves the package-plan exclude rules and verifies that archive entries exactly match the planned inventory.

## Builder Behavior

`build_deployment_package_archive(...)` performs these steps:

1. Builds a validated `DeploymentPackagePlan` from `deploy/serverless/package.manifest.json`.
2. Optionally writes the package inventory JSON.
3. Writes a zip archive with deterministic entry ordering.
4. Uses a fixed zip timestamp for every entry.
5. Writes files with stable `0644` external permissions.
6. Computes the archive SHA-256 digest.
7. Computes the package inventory SHA-256 digest.
8. Verifies archive contents against the plan before reporting success.

The verification checks are:

- `archive_exists`
- `entries_match_plan`
- `entry_hashes_match_plan`
- `local_secret_config_absent`
- `generated_caches_absent`

## Operator Command

Run from the repository root:

```bash
python scripts/build_deployment_archive.py --manifest deploy/serverless/package.manifest.json --archive outputs/vyu_deployment_package.zip --inventory outputs/deployment_package_inventory.json
```

Expected output status:

```json
{
  "status": "built"
}
```

The output includes:

- `archive_sha256`
- `inventory_sha256`
- `summary.file_count`
- `summary.total_bytes`
- verification check results

## Determinism Rules

The archive builder uses:

- sorted package-plan paths
- SHA-256 digests from the package plan
- a fixed zip timestamp: `DETERMINISTIC_ZIP_TIMESTAMP`
- stable file mode metadata
- no generated cache files
- no local secret config file

Building the same plan twice should produce the same archive SHA-256.

## Relationship to Earlier Deployment Modules

```text
scripts/build_deployment_archive.py
  -> DeploymentPackageArchive
    -> DeploymentPackagePlan
      -> DeploymentPackageManifest
        -> apps/serverless/handler.py
```

Runtime behavior remains owned by the previously completed deployment modules:

- app entrypoint
- operator config
- composition factory
- serverless handler
- API service shell
- deployment HTTP adapter
- service route runtime

## Current Limits

- This builder writes a local zip archive only.
- It does not build a wheel, container image, SBOM, provenance attestation, or signed artifact.
- It does not run vulnerability scanning or secret scanning.
- It does not upload artifacts to an object store.
- It does not create Lambda, Cloud Run, API Gateway, CORS, WAF, TLS, IAM, or production OIDC/JWKS configuration.

## Next Module Boundary

The next deployment module should add package integrity/provenance evidence for the built archive, such as a signed or unsigned local build manifest that records archive SHA-256, inventory SHA-256, source manifest path, and validation command results.
