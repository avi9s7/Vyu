# Deployment Release-Channel Evidence Export Summary Contract

The deployment release-channel evidence export summary module in `src/vyu/deployment/release_channel_export.py`, backed by `scripts/build_deployment_release_channel_export_summary.py`, builds a deterministic local JSON operator-review checklist from `outputs/deployment_release_channel_evidence_index.json`. It verifies that the evidence index is schema-supported and `ready`, confirms all evidence-index checks passed, and records the release-channel hashes and review checklist items an operator would inspect before choosing a later deployment target.

This is a local review boundary only. It does not transfer artifacts, sign artifacts, upload to CI/CD, generate SBOMs, scan vulnerabilities, persist records to production storage, inspect cloud infrastructure, or deploy anything.

## Command

```bash
python scripts/build_deployment_release_channel_export_summary.py \
  --evidence-index outputs/deployment_release_channel_evidence_index.json \
  --summary-name local-release-channel-evidence-export-summary \
  --created-at 2026-06-15T04:30:00Z \
  --output outputs/deployment_release_channel_export_summary.json
```

Operators may override the default checklist by passing one or more `--review-item` values. When omitted, the command records the default local checklist.

## Output

The command writes `outputs/deployment_release_channel_export_summary.json` with:

1. schema version;
2. top-level `ready` or `blocked` status;
3. summary name;
4. evidence-index path and SHA-256;
5. evidence-index schema, status, creation time, and index name;
6. publication, package, operator, and decision metadata copied from the evidence index;
7. evidence hash rollup for the evidence index and each named evidence item;
8. evidence counts from the evidence index;
9. required and optional evidence item summaries;
10. publication steps;
11. local-only limits;
12. review checklist items;
13. blocking reasons; and
14. check results with pass/fail details.

Expected output for a ready local export summary:

```json
{
  "schema_version": 1,
  "status": "ready",
  "summary_name": "local-release-channel-evidence-export-summary",
  "evidence_index": {
    "path": "outputs/deployment_release_channel_evidence_index.json",
    "sha256": "...",
    "readable": true,
    "json_valid": true,
    "schema_version": 1,
    "status": "ready",
    "index_name": "local-release-channel-evidence-index"
  },
  "evidence_hashes": {
    "evidence_index_sha256": "...",
    "publication_manifest_sha256": "...",
    "acceptance_record_sha256": "...",
    "preparation_manifest_sha256": "...",
    "handoff_inventory_sha256": "...",
    "handoff_archive_sha256": "...",
    "release_evidence_summary_sha256": "...",
    "release_review_decision_sha256": "...",
    "package_evidence_sha256": "..."
  },
  "summary": {
    "required_evidence_item_count": 8,
    "present_required_evidence_item_count": 8,
    "review_checklist_item_count": 4
  },
  "blocking_reasons": []
}
```

## Checks

A `ready` summary requires all checks to pass:

- `evidence_index_file_readable`
- `evidence_index_json_valid`
- `evidence_index_schema_supported`
- `evidence_index_status_ready`
- `evidence_index_checks_passed`
- `publication_manifest_sha256_present`
- `acceptance_record_sha256_present`
- `preparation_manifest_sha256_present`
- `handoff_inventory_sha256_present`
- `handoff_archive_hash_bound`
- `release_evidence_summary_sha256_present`
- `release_review_decision_sha256_present`
- `package_evidence_sha256_present`
- `required_evidence_counts_complete`
- `package_metadata_present`
- `operator_metadata_present`
- `publication_steps_present`
- `local_only_limits_present`
- `review_checklist_present`

## Blocking behavior

The summary is `blocked` when:

- the evidence index file is missing or not valid JSON;
- the evidence-index schema version is unsupported;
- the evidence index status is not `ready`;
- any evidence-index check failed;
- a required evidence item hash is missing;
- required evidence counts do not match;
- the handoff archive is not hash-bound;
- package or operator metadata is absent;
- publication steps or local-only limits are absent; or
- no operator review checklist items are supplied.

## Relationship to earlier release-channel artifacts

This module consumes the evidence index created by `scripts/build_deployment_release_channel_evidence.py` and does not re-open or re-verify each upstream release artifact. It creates a compact operator-facing summary/checklist around the hash chain already recorded in the evidence index.

The expected local chain is:

```text
deployment_release_channel_publication_manifest.json
  -> deployment_release_channel_evidence_index.json
  -> deployment_release_channel_export_summary.json
```

## Limits

This module intentionally avoids:

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

The follow-on deployment module is the local target-readiness note in `docs/production/deployment-release-channel-target-readiness.md`, which consumes `outputs/deployment_release_channel_export_summary.json`, while still avoiding signing, CI/CD upload, SBOM generation, vulnerability scanning, cloud-release execution, artifact transfer, or production persistence unless that boundary is selected explicitly.
