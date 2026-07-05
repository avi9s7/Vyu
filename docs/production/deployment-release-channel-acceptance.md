# Deployment Release Channel Acceptance

## Release Channel Acceptance Contract

The deployment release-channel acceptance module records a deterministic local operator approve/block decision for `outputs/deployment_release_channel_preparation.json`. It binds the decision to the preparation manifest SHA-256, verifies the preparation schema and ready status, checks the recorded preparation checks, confirms required inventory/archive hash fields, and writes a local acceptance JSON record for the next operator boundary.

Implemented files:

- `src/vyu/deployment/release_channel_acceptance.py`
- `scripts/accept_deployment_release_channel.py`
- `tests/test_deployment_release_channel_acceptance.py`

The module does not execute shell commands, sign artifacts, upload to CI, transfer artifacts, deploy infrastructure, inspect cloud resources, generate an SBOM, scan vulnerabilities, call KMS, or persist records to production storage. It only reads the local release-channel preparation manifest and writes a local operator decision record.

## Acceptance Behavior

`build_deployment_release_channel_acceptance_record(...)` records:

1. preparation manifest path and SHA-256;
2. preparation schema version, status, creation timestamp, and channel;
3. package metadata copied from the preparation manifest;
4. preparation artifact hashes copied from the preparation manifest;
5. preparation archive SHA-256, expected SHA-256, and hash-match status;
6. preparation inventory SHA-256;
7. operator ID and operator role;
8. approve/block decision and comment;
9. next actions copied from the preparation manifest;
10. accepted/blocked checks for preparation readability, JSON validity, schema support, ready status, preparation checks, inventory hash presence, archive hash binding, package metadata, next actions, decision value, operator metadata, and approval readiness.

## Operator Command

Run after `outputs/deployment_release_channel_preparation.json` is ready:

```bash
python scripts/accept_deployment_release_channel.py \
  --preparation outputs/deployment_release_channel_preparation.json \
  --decision approve \
  --operator-id release-operator \
  --operator-role deployment_operator \
  --comment "Release-channel preparation accepted for local handoff." \
  --decided-at 2026-06-15T03:45:00Z \
  --output outputs/deployment_release_channel_acceptance.json
```

Expected output for an accepted release-channel record:

```json
{
  "status": "accepted"
}
```

The command exits with status code `0` for accepted output, `1` for blocked checks or a block decision, and `2` for malformed arguments or write/read errors.

## Output Fields

The top-level JSON includes:

- `schema_version`
- `status`
- `acceptance_id`
- `decided_at`
- `preparation_path`
- `preparation.sha256`
- `preparation.status`
- `preparation.schema_version`
- `preparation.channel`
- `package.package_name`
- `package.runtime`
- `package.handler`
- `preparation_artifact_hashes.handoff_inventory_sha256`
- `preparation_artifact_hashes.handoff_archive_sha256`
- `preparation_artifact_hashes.release_evidence_summary_sha256`
- `preparation_artifact_hashes.release_review_decision_sha256`
- `preparation_archive.sha256`
- `preparation_archive.expected_sha256`
- `preparation_archive.hash_matches_expected`
- `preparation_inventory_sha256`
- `next_actions[]`
- `operator.id`
- `operator.role`
- `decision.value`
- `decision.comment`
- `blocking_reasons[]`
- `checks[].name`

Important checks include:

- `preparation_file_readable`
- `preparation_json_valid`
- `preparation_schema_supported`
- `preparation_status_ready`
- `preparation_checks_passed`
- `preparation_inventory_sha256_present`
- `preparation_archive_hash_bound`
- `package_metadata_present`
- `next_actions_present`
- `decision_supported`
- `operator_metadata_present`
- `approve_requires_ready_preparation`

## Failure Checks

The acceptance record is `blocked` when:

- the operator decision is `block`;
- the preparation file is missing;
- the preparation JSON is malformed or not an object;
- the preparation schema version is unsupported;
- the preparation status is not `ready`;
- any recorded preparation check failed;
- the preparation inventory SHA-256 is missing;
- the preparation requested an archive but the archive SHA-256 binding is missing or failed;
- package metadata is incomplete;
- no next action is recorded;
- operator ID, operator role, or comment is empty.

## Relationship to Earlier Deployment Modules

```text
scripts/accept_deployment_release_channel.py
  -> DeploymentReleaseChannelAcceptanceRecord
    -> outputs/deployment_release_channel_preparation.json
      -> outputs/deployment_release_handoff_inventory.json
      -> outputs/deployment_release_handoff.zip
      -> outputs/deployment_release_handoff.json
      -> outputs/deployment_release_evidence_summary.json
      -> outputs/deployment_release_review_decision.json
```

This module is intentionally a local operator acceptance layer for a future release channel. It does not perform the future release-channel transfer, signing, SBOM generation, vulnerability scanning, CI/CD publication, cloud deployment, or production persistence.

## Current Limits

- Local JSON acceptance record only.
- No arbitrary shell execution.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The follow-on deployment module is the local release-channel publication manifest in `docs/production/deployment-release-channel-publication.md`, which consumes `outputs/deployment_release_channel_acceptance.json`, while still avoiding signing, CI/CD upload, SBOM generation, vulnerability scanning, cloud-release execution, artifact transfer, or production persistence unless that boundary is selected explicitly.
