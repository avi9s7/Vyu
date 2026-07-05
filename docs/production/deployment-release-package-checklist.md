# Deployment Release Package Checklist

## Checklist Contract

The deployment release package checklist is a local CI-style gate for the serverless packaging boundary. It consumes the deployment package manifest, deterministic inventory, built archive, and unsigned package evidence JSON, then writes one release-readiness checklist for operator review.

Implemented files:

- `src/vyu/deployment/release_package.py`
- `scripts/check_deployment_release_package.py`
- `tests/test_deployment_release_package.py`

The checklist does not deploy infrastructure, sign artifacts, run a CI vendor workflow, or integrate with a production identity provider. It only verifies that the local package artifacts are internally consistent and ready for human/operator review.

## Checklist Behavior

`build_deployment_release_package_checklist(...)` performs these steps:

1. Reads and validates `deploy/serverless/package.manifest.json`.
2. Rebuilds the deterministic package plan from the manifest.
3. Verifies the existing archive against the package plan.
4. Confirms the inventory JSON matches the package plan.
5. Loads `outputs/deployment_package_evidence.json`.
6. Confirms evidence status is `complete`.
7. Confirms evidence schema is supported.
8. Confirms evidence manifest/archive/inventory paths match the checklist inputs.
9. Confirms evidence archive and inventory hashes match the current local artifacts.
10. Confirms the manifest records required command coverage for config validation, package validation, planning, archive build, evidence generation, release checklist, and deployment smoke testing.
11. Emits checklist status `ready` only when every check passes; otherwise it emits `blocked`.

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `manifest_path`
- `archive_path`
- `inventory_path`
- `evidence_path`
- `package`
- `artifact_hashes.archive_sha256`
- `artifact_hashes.inventory_sha256`
- `artifact_hashes.evidence_sha256`
- `required_command_coverage`
- `manifest_validation`
- `archive_verification`
- `evidence`
- checks such as `required_command_coverage_complete`, `evidence_hashes_match_artifacts`, and `inventory_matches_plan`
- `checks`

## Operator Command

Run after the archive, inventory, and package evidence have been built:

```bash
python scripts/check_deployment_release_package.py \
  --manifest deploy/serverless/package.manifest.json \
  --archive outputs/vyu_deployment_package.zip \
  --inventory outputs/deployment_package_inventory.json \
  --evidence outputs/deployment_package_evidence.json \
  --output outputs/deployment_release_package_checklist.json
```

For deterministic rehearsals or tests, pass an explicit timestamp:

```bash
python scripts/check_deployment_release_package.py \
  --manifest deploy/serverless/package.manifest.json \
  --archive outputs/vyu_deployment_package.zip \
  --inventory outputs/deployment_package_inventory.json \
  --evidence outputs/deployment_package_evidence.json \
  --output outputs/deployment_release_package_checklist.json \
  --created-at 2026-06-15T01:05:00Z
```

Expected output status when all checks pass:

```json
{
  "status": "ready"
}
```

The command exits with status code `0` for ready checklists, `1` for written but blocked checklists, and `2` for malformed input that prevents checklist generation.

## Failure Checks

The checklist blocks when:

- manifest validation fails;
- required command coverage is incomplete;
- the archive is missing;
- the inventory is missing;
- archive verification fails;
- the inventory JSON does not match the package plan;
- the evidence file is missing or invalid;
- evidence status is not `complete`;
- evidence schema is unsupported;
- evidence paths do not match the checklist inputs;
- evidence artifact hashes do not match the current local artifacts;
- evidence archive verification status is not `pass`.

## Relationship to Earlier Deployment Modules

```text
scripts/check_deployment_release_package.py
  -> DeploymentReleasePackageChecklist
    -> DeploymentPackageEvidence JSON
    -> DeploymentPackageArchiveVerification
    -> DeploymentPackagePlan
    -> DeploymentPackageManifest
      -> apps/serverless/handler.py
```

This module gates the local artifact set produced by the previous deployment package modules. It does not replace the operator smoke test; it verifies that the smoke-test command is present in the manifest's required validation/build command list.

## Current Limits

- This is a local JSON checklist only.
- It does not execute commands; it verifies manifest command coverage and artifact consistency.
- It does not add KMS, code signing, Sigstore, SLSA attestations, OIDC/JWKS, SBOM, vulnerability scanning, secret scanning, Docker, Terraform, IAM, CI vendor integration, or cloud deployment.
- It does not select a production API framework or identity provider.

## Next Module Boundary

The next deployment module can add command-result capture or local CI transcript evidence around this checklist, still without selecting cloud infrastructure or production identity-provider integration.
