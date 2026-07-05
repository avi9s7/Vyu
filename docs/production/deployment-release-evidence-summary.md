# Deployment Release Evidence Summary

## Release Evidence Summary Contract

The deployment release evidence summary is a local operator-review record for the serverless packaging boundary. It consumes the unsigned package evidence JSON, the release-package checklist JSON, and the transcript bundle JSON, then writes one ready/blocked summary that binds those records together by SHA-256 and consistency checks.

Implemented files:

- `src/vyu/deployment/release_evidence.py`
- `scripts/build_deployment_release_evidence.py`
- `tests/test_deployment_release_evidence.py`

The summary does not execute shell commands, sign artifacts, upload evidence, call a CI vendor, deploy infrastructure, or integrate with a production identity provider. It only reads local JSON evidence that has already been produced by earlier deployment modules.

## Summary Behavior

`build_deployment_release_evidence_summary(...)` records:

1. package evidence path, release checklist path, and transcript bundle path;
2. SHA-256 for each input evidence file;
3. schema version, status, and manifest path for each input record;
4. package metadata from the package evidence and release checklist;
5. archive and inventory hashes from package evidence/checklist records;
6. checklist evidence hash binding back to the package evidence input file;
7. required-command coverage from package evidence and transcript bundle records;
8. top-level status `ready` or `blocked`.

A release evidence summary is `ready` only when:

- all three input evidence files are readable;
- all three input files contain JSON objects;
- all three schema versions are supported;
- package evidence status is `complete`;
- release checklist status is `ready`;
- transcript bundle status is `ready`;
- all manifest paths match;
- package metadata matches between package evidence and release checklist;
- archive and inventory hashes match between package evidence and release checklist;
- `checklist_evidence_hash_matches_input` confirms the checklist's `artifact_hashes.evidence_sha256` equals the SHA-256 of the supplied package evidence file;
- `required_commands_match_transcript_bundle` confirms package evidence commands match transcript bundle commands;
- `transcript_bundle_coverage_complete` confirms every required command has transcript coverage.

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `package_evidence_path`
- `release_checklist_path`
- `transcript_bundle_path`
- `inputs.package_evidence.sha256`
- `inputs.release_checklist.sha256`
- `inputs.transcript_bundle.sha256`
- `package`
- `artifact_hashes.package_evidence_sha256`
- `artifact_hashes.release_checklist_sha256`
- `artifact_hashes.transcript_bundle_sha256`
- `artifact_hashes.archive_sha256`
- `artifact_hashes.inventory_sha256`
- `artifact_hashes.checklist_evidence_sha256`
- `command_summary.commands_match`
- `summary.passed`
- `summary.failed`
- `checks[].name`
- `checklist_evidence_hash_matches_input`
- `package_artifact_hashes_match_checklist`
- `manifest_paths_match`
- `required_commands_match_transcript_bundle`
- `transcript_bundle_coverage_complete`

## Operator Command

Run after package evidence, release checklist, and transcript bundle files have been produced:

```bash
python scripts/build_deployment_release_evidence.py \
  --package-evidence outputs/deployment_package_evidence.json \
  --release-checklist outputs/deployment_release_package_checklist.json \
  --transcript-bundle outputs/deployment_transcript_bundle.json \
  --output outputs/deployment_release_evidence_summary.json
```

For deterministic rehearsals or tests, pass an explicit timestamp:

```bash
python scripts/build_deployment_release_evidence.py \
  --package-evidence outputs/deployment_package_evidence.json \
  --release-checklist outputs/deployment_release_package_checklist.json \
  --transcript-bundle outputs/deployment_transcript_bundle.json \
  --created-at 2026-06-15T02:30:00Z \
  --output outputs/deployment_release_evidence_summary.json
```

Expected output when all upstream evidence is internally consistent:

```json
{
  "status": "ready"
}
```

Expected output when upstream evidence is missing, stale, blocked, or mismatched:

```json
{
  "status": "blocked"
}
```

The command exits with status code `0` for ready summaries, `1` for blocked summaries, and `2` for malformed command metadata or write errors.

## Failure Checks

The summary blocks when:

- an input evidence file is missing;
- an input evidence file is not valid JSON;
- an input schema version is unsupported;
- package evidence is not `complete`;
- release checklist is not `ready`;
- transcript bundle is not `ready`;
- manifest paths differ across the three inputs;
- package metadata differs between package evidence and release checklist;
- archive or inventory hashes differ between package evidence and release checklist;
- the checklist evidence hash does not match the supplied package evidence file;
- required commands differ between package evidence and transcript bundle;
- transcript bundle coverage is incomplete.

## Relationship to Earlier Deployment Modules

```text
scripts/build_deployment_release_evidence.py
  -> DeploymentReleaseEvidenceSummary
    -> outputs/deployment_package_evidence.json
    -> outputs/deployment_release_package_checklist.json
    -> outputs/deployment_transcript_bundle.json
```

This module is intentionally a summary layer. Package evidence verifies the archive/inventory boundary. The release checklist verifies the package artifact set. The transcript bundle verifies command evidence. The release evidence summary binds those three outputs into one local operator-review record.

## Current Limits

- Local JSON summary only.
- No arbitrary shell execution.
- No CI vendor integration.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.
- No persistent deployment approval database; this summary is file-based evidence.

## Next Module Boundary

The next deployment module can add a local deployment release evidence review gate that records an operator approve/block decision against `outputs/deployment_release_evidence_summary.json` and its SHA-256, without signing, executing commands, persisting to production storage, or integrating with a CI/cloud provider.
