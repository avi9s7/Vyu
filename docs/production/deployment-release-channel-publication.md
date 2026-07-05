# Deployment Release Channel Publication Manifest

## Release Channel Publication Contract

The deployment release-channel publication module builds a deterministic local no-op publication manifest from `outputs/deployment_release_channel_acceptance.json`. It verifies that the acceptance record is schema-supported and `accepted`, confirms that the operator decision approves the release-channel handoff, checks that no blocking reasons remain, and records the accepted preparation, archive hash binding, package metadata, operator metadata, publication steps, and local-only safety limits.

Implemented files:

- `src/vyu/deployment/release_channel_publication.py`
- `scripts/prepare_deployment_release_channel_publication.py`
- `tests/test_deployment_release_channel_publication.py`

The module does not execute shell commands, sign artifacts, transfer artifacts, upload to CI, deploy infrastructure, inspect cloud resources, generate an SBOM, scan vulnerabilities, call KMS, or persist records to production storage. It only reads the local release-channel acceptance record and writes a local publication-readiness manifest for future operator review.

## Publication Behavior

`build_deployment_release_channel_publication_manifest(...)` records:

1. publication channel name;
2. acceptance record path and SHA-256;
3. acceptance schema version, status, and decision timestamp;
4. package metadata copied from the acceptance record;
5. accepted preparation metadata copied from the acceptance record;
6. preparation artifact hashes copied from the acceptance record;
7. preparation archive SHA-256, expected SHA-256, and hash-match status;
8. preparation inventory SHA-256;
9. operator ID and operator role copied from the acceptance record;
10. approve decision copied from the acceptance record;
11. operator-visible publication checklist steps;
12. local-only limits that preserve the no-op module boundary;
13. ready/blocked checks for acceptance readability, JSON validity, schema support, accepted status, approve decision, absence of blocking reasons, preparation hash/status, inventory/archive hash evidence, package metadata, operator metadata, checklist steps, and local-only limits.

## Operator Command

Run after `outputs/deployment_release_channel_acceptance.json` is accepted:

```bash
python scripts/prepare_deployment_release_channel_publication.py \
  --acceptance outputs/deployment_release_channel_acceptance.json \
  --publication-channel local-release-channel-publication \
  --created-at 2026-06-15T04:00:00Z \
  --output outputs/deployment_release_channel_publication_manifest.json
```

Expected output for a ready local publication manifest:

```json
{
  "status": "ready"
}
```

The command exits with status code `0` for ready output, `1` for blocked checks, and `2` for malformed arguments or write/read errors.

## Output Fields

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `publication_channel`
- `acceptance_path`
- `acceptance.sha256`
- `acceptance.status`
- `acceptance.schema_version`
- `acceptance.decided_at`
- `package.package_name`
- `package.runtime`
- `package.handler`
- `preparation.sha256`
- `preparation.status`
- `preparation.channel`
- `preparation_artifact_hashes.handoff_inventory_sha256`
- `preparation_artifact_hashes.handoff_archive_sha256`
- `preparation_artifact_hashes.release_evidence_summary_sha256`
- `preparation_artifact_hashes.release_review_decision_sha256`
- `preparation_archive.sha256`
- `preparation_archive.expected_sha256`
- `preparation_archive.hash_matches_expected`
- `preparation_inventory_sha256`
- `operator.id`
- `operator.role`
- `decision.value`
- `decision.comment`
- `publication_steps[]`
- `local_only_limits[]`
- `checks[].name`

Important checks include:

- `acceptance_file_readable`
- `acceptance_json_valid`
- `acceptance_schema_supported`
- `acceptance_status_accepted`
- `acceptance_decision_approves`
- `acceptance_blocking_reasons_absent`
- `preparation_hash_present`
- `preparation_status_ready`
- `preparation_inventory_sha256_present`
- `preparation_archive_hash_bound`
- `package_metadata_present`
- `operator_metadata_present`
- `publication_steps_recorded`
- `local_only_limits_recorded`

## Failure Checks

The publication manifest is `blocked` when:

- the acceptance file is missing;
- the acceptance JSON is malformed or not an object;
- the acceptance schema version is unsupported;
- the acceptance status is not `accepted`;
- the acceptance decision is not `approve`;
- the acceptance record contains blocking reasons;
- the accepted preparation SHA-256 is missing;
- the accepted preparation status is not `ready`;
- the preparation inventory SHA-256 is missing;
- the accepted preparation requested an archive but archive hash binding is missing or failed;
- package metadata is incomplete;
- operator ID or operator role is missing;
- no publication checklist step is recorded;
- no local-only safety limit is recorded.

## Relationship to Earlier Deployment Modules

```text
scripts/prepare_deployment_release_channel_publication.py
  -> DeploymentReleaseChannelPublicationManifest
    -> outputs/deployment_release_channel_acceptance.json
      -> outputs/deployment_release_channel_preparation.json
      -> outputs/deployment_release_handoff_inventory.json
      -> outputs/deployment_release_handoff.zip
      -> outputs/deployment_release_handoff.json
      -> outputs/deployment_release_evidence_summary.json
      -> outputs/deployment_release_review_decision.json
```

This module is intentionally a local publication-readiness manifest. It does not perform transfer, signing, SBOM generation, vulnerability scanning, CI/CD publication, cloud deployment, or production persistence.

## Current Limits

- Local JSON publication manifest only.
- No arbitrary shell execution.
- No artifact transfer.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The follow-on deployment module is the local release-channel evidence index in `docs/production/deployment-release-channel-evidence-index.md`, which consumes `outputs/deployment_release_channel_publication_manifest.json`, while still avoiding signing, CI/CD upload, SBOM generation, vulnerability scanning, cloud-release execution, artifact transfer, or production persistence unless that boundary is selected explicitly.
