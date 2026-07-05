# Deployment Release Channel Preparation

## Release Channel Preparation Contract

The deployment release channel preparation module builds a deterministic local provenance manifest from `outputs/deployment_release_handoff_inventory.json` and, when available, `outputs/deployment_release_handoff.zip`. It verifies that the handoff archive inventory is schema-supported and `ready`, checks that its artifact checks passed, verifies that inventory artifacts still report matching recorded hashes, and confirms that the optional handoff archive SHA-256 matches the value recorded in the inventory.

Implemented files:

- `src/vyu/deployment/release_channel.py`
- `scripts/prepare_deployment_release_channel.py`
- `tests/test_deployment_release_channel.py`

The module does not execute shell commands, sign artifacts, upload to CI, deploy infrastructure, inspect cloud resources, generate an SBOM, scan vulnerabilities, call KMS, or persist records to production storage. It only reads the local handoff archive inventory, optionally verifies the local handoff archive file hash, and writes a release-channel preparation JSON manifest for operator handoff.

## Preparation Behavior

`build_deployment_release_channel_preparation(...)` records:

1. release-channel name;
2. handoff archive inventory path and SHA-256;
3. optional handoff archive path, SHA-256, expected SHA-256, and hash-match status;
4. package metadata copied from the handoff archive inventory;
5. inventory summary metadata such as included artifact count and byte counts;
6. artifact hashes copied from the handoff archive inventory plus the handoff inventory/archive hashes;
7. operator-visible next actions;
8. ready/blocked checks for inventory readability, JSON validity, schema support, ready status, inventory checks, artifact hash match status, archive presence, archive hash binding, package metadata, and next-action recording.

## Operator Command

Run after `outputs/deployment_release_handoff_inventory.json` and optionally `outputs/deployment_release_handoff.zip` are ready:

```bash
python scripts/prepare_deployment_release_channel.py \
  --inventory outputs/deployment_release_handoff_inventory.json \
  --archive outputs/deployment_release_handoff.zip \
  --created-at 2026-06-15T03:30:00Z \
  --channel local-release-channel \
  --output outputs/deployment_release_channel_preparation.json
```

Expected output for a ready release-channel preparation manifest:

```json
{
  "status": "ready"
}
```

The command exits with status code `0` for ready preparation output, `1` for blocked checks, and `2` for malformed arguments or write/read errors.

## Output Fields

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `channel`
- `inventory_path`
- `inventory_sha256`
- `archive.requested`
- `archive.path`
- `archive.sha256`
- `archive.expected_sha256`
- `archive.hash_matches_expected`
- `package.package_name`
- `package.runtime`
- `package.handler`
- `inventory_summary.included_artifact_count`
- `inventory_summary.included_total_bytes`
- `artifact_hashes.handoff_inventory_sha256`
- `artifact_hashes.handoff_archive_sha256`
- `artifact_hashes.release_evidence_summary_sha256`
- `artifact_hashes.release_review_decision_sha256`
- `artifact_hashes.package_evidence_sha256`
- `next_actions[]`
- `checks[].name`

Important checks include:

- `inventory_file_readable`
- `inventory_json_valid`
- `inventory_schema_supported`
- `inventory_status_ready`
- `inventory_included_artifacts_present`
- `inventory_checks_passed`
- `inventory_artifact_hashes_match`
- `archive_requirement_consistent`
- `archive_file_exists`
- `archive_hash_matches_inventory`
- `package_metadata_present`
- `next_actions_recorded`

## Failure Checks

The preparation manifest is `blocked` when:

- the inventory file is missing;
- the inventory JSON is malformed or not an object;
- the inventory schema version is unsupported;
- the inventory status is not `ready`;
- the inventory reports zero included artifacts;
- any recorded inventory check failed;
- any inventory artifact reports `hash_matches_expected: false`;
- the inventory requested an archive but no archive path is available;
- the archive file is missing when required;
- the archive SHA-256 no longer matches the inventory;
- package metadata is incomplete;
- no operator-visible next action is recorded.

## Relationship to Earlier Deployment Modules

```text
scripts/prepare_deployment_release_channel.py
  -> DeploymentReleaseChannelPreparation
    -> outputs/deployment_release_handoff_inventory.json
      -> outputs/deployment_release_handoff.json
      -> outputs/deployment_release_evidence_summary.json
      -> outputs/deployment_release_review_decision.json
      -> outputs/deployment_package_evidence.json
      -> outputs/deployment_release_package_checklist.json
      -> outputs/deployment_transcript_bundle.json
    -> outputs/deployment_release_handoff.zip
```

This module is intentionally a local preparation layer for a future release channel. It does not perform the future release-channel transfer, signing, SBOM generation, vulnerability scanning, CI/CD publication, cloud deployment, or production persistence.

## Current Limits

- Local JSON preparation manifest only.
- No arbitrary shell execution.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add a local release-channel operator acceptance record that consumes `outputs/deployment_release_channel_preparation.json` and records an approve/block decision before any future signing, CI/CD, SBOM, vulnerability scanning, or cloud-release module is selected.
