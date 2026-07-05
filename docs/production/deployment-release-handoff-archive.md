# Deployment Release Handoff Archive

## Release Handoff Archive Contract

The deployment release handoff archive module builds a deterministic local inventory, and optionally a deterministic zip archive, for the release handoff evidence set. It consumes `outputs/deployment_release_handoff.json`, verifies that the handoff manifest is schema-supported and `ready`, follows its referenced summary/review files, follows the release evidence summary to the package evidence, release checklist, and transcript bundle JSON files, and verifies recorded SHA-256 bindings before marking the inventory ready.

Implemented files:

- `src/vyu/deployment/release_handoff_archive.py`
- `scripts/build_deployment_release_handoff_archive.py`
- `tests/test_deployment_release_handoff_archive.py`

The module does not execute shell commands, sign artifacts, append to production storage, call CI, deploy infrastructure, inspect cloud resources, or manage identity-provider configuration. It only reads local JSON evidence files, validates hashes already recorded by the handoff chain, writes an inventory JSON, and optionally writes a fixed-metadata zip archive of those JSON evidence files.

## Archive Inventory Behavior

`build_deployment_release_handoff_archive_inventory(...)` records:

1. the handoff manifest path;
2. handoff schema version and `ready` status checks;
3. release evidence summary and review decision paths from the handoff manifest;
4. package evidence, release checklist, and transcript bundle paths from the release evidence summary;
5. file existence, JSON validity, size, SHA-256, archive entry name, and expected SHA-256 for each included artifact;
6. package metadata copied from the handoff manifest;
7. upstream artifact hashes copied from the handoff manifest;
8. deterministic archive path and archive SHA-256 when `--archive` is supplied;
9. ready/blocked checks for path presence, file existence, JSON validity, recorded hash matching, local secret exclusion, generated cache exclusion, archive entry matching, archive entry hash matching, and deterministic zip metadata.

The included archive entries are:

- `outputs/deployment_release_handoff.json`
- `outputs/deployment_release_evidence_summary.json`
- `outputs/deployment_release_review_decision.json`
- `outputs/deployment_package_evidence.json`
- `outputs/deployment_release_package_checklist.json`
- `outputs/deployment_transcript_bundle.json`

For non-standard paths, the archive entry is the path relative to `--root` when possible. The zip writer uses the same fixed metadata convention as the deployment package archive builder.

## Operator Command

Run after `outputs/deployment_release_handoff.json` is ready:

```bash
python scripts/build_deployment_release_handoff_archive.py \
  --handoff outputs/deployment_release_handoff.json \
  --created-at 2026-06-15T03:15:00Z \
  --inventory outputs/deployment_release_handoff_inventory.json \
  --archive outputs/deployment_release_handoff.zip
```

Expected output for a ready handoff archive/inventory:

```json
{
  "status": "ready"
}
```

The command exits with status code `0` for ready inventory/archive output, `1` for blocked inventory/archive checks, and `2` for malformed arguments or write/read errors.

## Output Fields

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `handoff_path`
- `archive.path`
- `archive.sha256`
- `archive.requested`
- `archive.entry_count`
- `package.package_name`
- `artifact_hashes.release_evidence_summary_sha256`
- `artifact_hashes.release_review_decision_sha256`
- `artifact_hashes.package_evidence_sha256`
- `artifact_hashes.release_checklist_sha256`
- `artifact_hashes.transcript_bundle_sha256`
- `summary.artifact_count`
- `summary.included_artifact_count`
- `summary.total_bytes`
- `summary.included_total_bytes`
- `artifacts[].name`
- `artifacts[].path`
- `artifacts[].archive_entry`
- `artifacts[].size_bytes`
- `artifacts[].sha256`
- `artifacts[].expected_sha256`
- `artifacts[].hash_matches_expected`
- `artifacts[].include_in_archive`
- `checks[].name`

Important checks include:

- `handoff_schema_supported`
- `handoff_status_ready`
- `handoff_input_paths_present`
- `release_evidence_paths_present`
- `referenced_files_exist`
- `referenced_json_valid`
- `recorded_hashes_match_files`
- `included_archive_entries_unique`
- `local_secret_config_absent`
- `generated_caches_absent`
- `handoff_archive_written`
- `archive_entries_match_inventory`
- `archive_entry_hashes_match_inventory`
- `archive_metadata_deterministic`

## Failure Checks

The inventory is `blocked` when:

- the handoff file is missing;
- the handoff JSON is malformed or not an object;
- the handoff schema version is unsupported;
- the handoff status is not `ready`;
- the summary/review paths are missing from the handoff;
- the package evidence, release checklist, or transcript bundle paths are missing from the summary;
- any referenced JSON evidence file is missing;
- any referenced JSON evidence file is malformed;
- any recorded SHA-256 value no longer matches the corresponding file;
- a local secret config or generated cache would be included;
- the requested archive cannot be written or verified.

## Relationship to Earlier Deployment Modules

```text
scripts/build_deployment_release_handoff_archive.py
  -> DeploymentReleaseHandoffArchiveInventory
    -> outputs/deployment_release_handoff.json
      -> outputs/deployment_release_evidence_summary.json
        -> outputs/deployment_package_evidence.json
        -> outputs/deployment_release_package_checklist.json
        -> outputs/deployment_transcript_bundle.json
      -> outputs/deployment_release_review_decision.json
```

This module is intentionally a local archive/inventory layer. It does not replace release approval, signing, CI/CD, SBOM generation, vulnerability scanning, cloud deployment, or production persistence.

## Current Limits

- Local JSON inventory and optional zip archive only.
- No arbitrary shell execution.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add local deployment release bundle provenance metadata or release-channel preparation that consumes the handoff archive/inventory, without signing artifacts, executing arbitrary commands, integrating with CI/cloud infrastructure, or persisting to production storage.
