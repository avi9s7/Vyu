# Deployment Release Channel Evidence Index

## Release Channel Evidence Index Contract

The deployment release-channel evidence index module builds a deterministic local JSON evidence index from `outputs/deployment_release_channel_publication_manifest.json`. It verifies that the publication manifest is schema-supported and `ready`, confirms the accepted release-channel approval chain, and records a compact index of required evidence hashes for downstream operator review.

Implemented files:

- `src/vyu/deployment/release_channel_evidence.py`
- `scripts/build_deployment_release_channel_evidence.py`
- `tests/test_deployment_release_channel_evidence.py`

The module does not execute shell commands, sign artifacts, transfer artifacts, upload to CI, deploy infrastructure, inspect cloud resources, generate an SBOM, scan vulnerabilities, call KMS, or persist records to production storage. It only reads the local release-channel publication manifest and writes a local evidence-index JSON file.

## Evidence Index Behavior

`build_deployment_release_channel_evidence_index(...)` records:

1. evidence index name;
2. publication manifest path and SHA-256;
3. publication schema version, status, timestamp, and channel;
4. package metadata copied from the publication manifest;
5. operator ID and operator role copied from the publication manifest;
6. approve decision copied from the publication manifest;
7. publication steps and local-only limits copied from the publication manifest;
8. required evidence items for publication, acceptance, preparation, handoff inventory, handoff archive, release evidence summary, release review decision, and deployment package evidence;
9. optional evidence items for release checklist and transcript bundle hashes when present;
10. ready/blocked checks for publication readability, JSON validity, schema support, ready status, publication checks, approval state, accepted preparation metadata, inventory/archive hash evidence, package metadata, operator metadata, publication steps, local-only limits, and required evidence item presence.

## Operator Command

Run after `outputs/deployment_release_channel_publication_manifest.json` is ready:

```bash
python scripts/build_deployment_release_channel_evidence.py \
  --publication outputs/deployment_release_channel_publication_manifest.json \
  --index-name local-release-channel-evidence-index \
  --created-at 2026-06-15T04:15:00Z \
  --output outputs/deployment_release_channel_evidence_index.json
```

Expected output for a ready local evidence index:

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
- `index_name`
- `publication_path`
- `publication.sha256`
- `publication.status`
- `publication.schema_version`
- `publication.publication_channel`
- `package.package_name`
- `package.runtime`
- `package.handler`
- `operator.id`
- `operator.role`
- `decision.value`
- `decision.comment`
- `publication_steps[]`
- `local_only_limits[]`
- `evidence_items[]`
- `evidence_items[].name`
- `evidence_items[].role`
- `evidence_items[].sha256`
- `evidence_items[].source_field`
- `evidence_items[].required`
- `evidence_items[].present`
- `evidence_items[].expected_sha256`
- `evidence_items[].hash_matches_expected`
- `summary.evidence_item_count`
- `summary.required_evidence_item_count`
- `summary.present_required_evidence_item_count`
- `checks[].name`

Important checks include:

- `publication_file_readable`
- `publication_json_valid`
- `publication_schema_supported`
- `publication_status_ready`
- `publication_checks_passed`
- `acceptance_sha256_present`
- `acceptance_status_accepted`
- `decision_approves`
- `preparation_sha256_present`
- `preparation_status_ready`
- `preparation_inventory_sha256_present`
- `handoff_archive_hash_bound`
- `package_metadata_present`
- `operator_metadata_present`
- `publication_steps_present`
- `local_only_limits_present`
- `required_evidence_items_present`

## Required Evidence Items

The index always expects these required items to be present:

- `publication_manifest`
- `acceptance_record`
- `preparation_manifest`
- `handoff_inventory`
- `handoff_archive`
- `release_evidence_summary`
- `release_review_decision`
- `package_evidence`

The index also records optional evidence items when their hashes are available in the publication manifest, such as release checklist and transcript bundle hashes.

## Failure Checks

The evidence index is `blocked` when:

- the publication manifest file is missing;
- the publication JSON is malformed or not an object;
- the publication schema version is unsupported;
- the publication status is not `ready`;
- any recorded publication check failed;
- the acceptance SHA-256 is missing;
- the accepted status is not `accepted`;
- the decision value is not `approve`;
- the preparation SHA-256 is missing;
- the accepted preparation status is not `ready`;
- the preparation inventory SHA-256 is missing;
- the handoff archive hash binding is missing or failed;
- package metadata is incomplete;
- operator metadata is incomplete;
- no publication step is recorded;
- no local-only safety limit is recorded;
- any required evidence item is missing.

## Relationship to Earlier Deployment Modules

```text
scripts/build_deployment_release_channel_evidence.py
  -> DeploymentReleaseChannelEvidenceIndex
    -> outputs/deployment_release_channel_publication_manifest.json
      -> outputs/deployment_release_channel_acceptance.json
      -> outputs/deployment_release_channel_preparation.json
      -> outputs/deployment_release_handoff_inventory.json
      -> outputs/deployment_release_handoff.zip
      -> outputs/deployment_release_handoff.json
      -> outputs/deployment_release_evidence_summary.json
      -> outputs/deployment_release_review_decision.json
      -> outputs/deployment_package_evidence.json
```

This module is intentionally a local evidence-index artifact. It does not perform transfer, signing, SBOM generation, vulnerability scanning, CI/CD publication, cloud deployment, or production persistence.

## Current Limits

- Local JSON evidence index only.
- No arbitrary shell execution.
- No artifact transfer.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The follow-on deployment module is the local release-channel evidence export summary in `docs/production/deployment-release-channel-export-summary.md`, which consumes `outputs/deployment_release_channel_evidence_index.json`, while still avoiding signing, CI/CD upload, SBOM generation, vulnerability scanning, cloud-release execution, artifact transfer, or production persistence unless that boundary is selected explicitly.
