# Deployment Release-Channel Target Readiness Contract

The deployment release-channel target-readiness module in `src/vyu/deployment/release_channel_target.py`, backed by `scripts/build_deployment_release_channel_target_readiness.py`, builds a deterministic local JSON target-selection readiness note from `outputs/deployment_release_channel_export_summary.json`. It verifies that the export summary is schema-supported and `ready`, confirms the evidence-index hash binding and evidence counts, and records local handoff checklist items for choosing a future deployment target family.

This module does not select a real provider, configure infrastructure, transfer artifacts, sign artifacts, upload to CI/CD, generate SBOMs, scan vulnerabilities, persist records to production storage, or deploy anything.

## Command

```bash
python scripts/build_deployment_release_channel_target_readiness.py \
  --export-summary outputs/deployment_release_channel_export_summary.json \
  --readiness-name local-release-channel-target-readiness \
  --created-at 2026-06-15T04:45:00Z \
  --output outputs/deployment_release_channel_target_readiness.json
```

Operators may override the default candidate target-family placeholders by passing one or more `--target-family` values. Operators may override the default environment handoff checklist by passing one or more `--handoff-item` values.

## Output

The command writes `outputs/deployment_release_channel_target_readiness.json` with:

1. schema version;
2. top-level `ready` or `blocked` status;
3. readiness note name;
4. export-summary path and SHA-256;
5. export-summary schema, status, creation time, and summary name;
6. target-selection scope;
7. null `selected_target_provider`;
8. empty `provider_configuration`;
9. candidate target-family placeholders;
10. environment handoff checklist items;
11. package and operator metadata;
12. evidence hashes and evidence counts;
13. export-review checklist and local-only limits;
14. export blocking reasons; and
15. target-readiness check results with pass/fail details.

Expected output for a ready local target-readiness note:

```json
{
  "schema_version": 1,
  "status": "ready",
  "readiness_name": "local-release-channel-target-readiness",
  "target_selection_scope": "local_target_family_review_only",
  "selected_target_provider": null,
  "provider_configuration": {},
  "candidate_target_families": [
    "serverless_function",
    "container_service",
    "managed_job_or_worker"
  ],
  "summary": {
    "candidate_target_family_count": 3,
    "handoff_checklist_item_count": 4,
    "required_evidence_item_count": 8,
    "present_required_evidence_item_count": 8
  },
  "blocking_reasons": []
}
```

## Checks

A `ready` target-readiness note requires all checks to pass:

- `export_summary_file_readable`
- `export_summary_json_valid`
- `export_summary_schema_supported`
- `export_summary_status_ready`
- `export_summary_checks_passed`
- `export_blocking_reasons_absent`
- `evidence_index_sha256_present`
- `evidence_index_hash_bound`
- `required_evidence_counts_complete`
- `review_checklist_present`
- `package_metadata_present`
- `operator_metadata_present`
- `local_only_limits_present`
- `candidate_target_families_recorded`
- `no_target_provider_selected`
- `no_provider_configuration_recorded`
- `handoff_checklist_present`

## Blocking behavior

The target-readiness note is `blocked` when:

- the export-summary file is missing or not valid JSON;
- the export-summary schema version is unsupported;
- the export summary status is not `ready`;
- any export-summary check failed;
- export-summary blocking reasons are present;
- the evidence-index hash is missing or not bound between `evidence_index.sha256` and `evidence_hashes.evidence_index_sha256`;
- required evidence counts are incomplete;
- review checklist, local-only limits, candidate target families, or handoff checklist items are absent; or
- package/operator metadata is absent.

## Relationship to earlier release-channel artifacts

This module consumes the export summary created by `scripts/build_deployment_release_channel_export_summary.py` and does not re-open or re-verify each upstream release artifact. It creates a compact target-selection readiness note around the reviewed release-channel evidence summary.

The expected local chain is:

```text
deployment_release_channel_evidence_index.json
  -> deployment_release_channel_export_summary.json
  -> deployment_release_channel_target_readiness.json
```

## Limits

This module intentionally avoids:

- target provider selection;
- provider configuration;
- shell execution;
- artifact transfer;
- signing, KMS, or key handling;
- CI/CD upload or vendor APIs;
- SBOM generation;
- vulnerability scanning;
- cloud release execution;
- production persistence; and
- infrastructure or identity-provider configuration.

## Next boundary

The follow-on deployment module is the local release-channel target decision record in `docs/production/deployment-release-channel-target-decision.md`, which consumes `outputs/deployment_release_channel_target_readiness.json`, while still avoiding provider-specific configuration, signing, CI/CD upload, SBOM generation, vulnerability scanning, cloud-release execution, artifact transfer, or production persistence unless that boundary is selected explicitly.
