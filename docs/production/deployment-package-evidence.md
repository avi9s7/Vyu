# Deployment Package Evidence

## Evidence Contract

The deployment package evidence module writes an unsigned local integrity/provenance JSON document for a built deployment archive. It consumes the archive, inventory, manifest, and archive verification path that already exist locally; it does not deploy infrastructure or sign artifacts.

Implemented files:

- `src/vyu/deployment/package_evidence.py`
- `scripts/write_deployment_package_evidence.py`
- `tests/test_deployment_package_evidence.py`

The evidence document is intended to give operators a stable JSON handoff for package review before any future signing, SBOM, CI/CD, or cloud deployment work is selected.

## Evidence Behavior

`build_deployment_package_evidence(...)` performs these steps:

1. Reads and validates `deploy/serverless/package.manifest.json`.
2. Rebuilds the deterministic package plan from the manifest.
3. Verifies the existing archive against the package plan.
4. Confirms the inventory JSON exists and matches the package plan.
5. Computes the archive SHA-256.
6. Computes the canonical inventory SHA-256 using the same package-plan payload contract as the archive builder.
7. Records package metadata from the manifest: package name, schema, deployment target, runtime, handler, and operator config environment variable.
8. Records the required validation/build commands from the manifest.
9. Emits evidence status `complete` only when all checks pass; otherwise it emits `failed`.

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `manifest_path`
- `archive_path`
- `inventory_path`
- `package`
- `artifact_hashes.archive_sha256`
- `artifact_hashes.inventory_sha256`
- `required_validation_commands`
- `manifest_validation`
- `archive_verification`
- checks such as `archive_verification_passed` and `inventory_matches_plan`
- `checks`

## Operator Command

Run after the archive and inventory have been built:

```bash
python scripts/write_deployment_package_evidence.py \
  --manifest deploy/serverless/package.manifest.json \
  --archive outputs/vyu_deployment_package.zip \
  --inventory outputs/deployment_package_inventory.json \
  --output outputs/deployment_package_evidence.json
```

For deterministic rehearsals or tests, pass an explicit timestamp:

```bash
python scripts/write_deployment_package_evidence.py \
  --manifest deploy/serverless/package.manifest.json \
  --archive outputs/vyu_deployment_package.zip \
  --inventory outputs/deployment_package_inventory.json \
  --output outputs/deployment_package_evidence.json \
  --created-at 2026-06-15T00:40:00Z
```

Expected output status when all checks pass:

```json
{
  "status": "complete"
}
```

The command exits with status code `0` for complete evidence, `1` for written but failed evidence, and `2` for malformed input that prevents evidence generation.

## Failure Checks

Evidence fails closed when:

- the manifest validation does not pass;
- the archive is missing;
- archive entries do not match the package plan;
- archive entry hashes do not match the package plan;
- the archive includes local secret config;
- the archive includes generated caches;
- the inventory file is missing;
- the inventory JSON does not match the package plan.

## Relationship to Earlier Deployment Modules

```text
scripts/write_deployment_package_evidence.py
  -> DeploymentPackageEvidence
    -> DeploymentPackageArchiveVerification
      -> DeploymentPackagePlan
        -> DeploymentPackageManifest
          -> apps/serverless/handler.py
```

The evidence module relies on the archive builder and package planner contracts but does not rebuild or upload deployment infrastructure.

## Current Limits

- Evidence is unsigned local JSON only.
- It does not add KMS, code signing, Sigstore, SLSA attestations, OIDC/JWKS, SBOM, vulnerability scanning, secret scanning, Docker, Terraform, IAM, or cloud deployment.
- It does not prove that commands were executed in CI; it records the required validation/build commands that should be run for this package boundary.
- It does not replace compliance bundle or pilot release-decision evidence.

## Next Module Boundary

The next deployment module can build on this evidence file by adding a higher-level release package checklist or CI gate around the local deployment artifacts. It should still avoid production cloud infrastructure until the first deployment target is selected.
