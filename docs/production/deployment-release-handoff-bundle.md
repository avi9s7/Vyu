# Deployment Release Handoff Bundle

## Release Handoff Bundle Contract

The deployment release handoff bundle is a deterministic local manifest that packages the release evidence summary and release review decision into one operator handoff record. It verifies that the approved review decision is bound to the exact release evidence summary file by SHA-256.

Implemented files:

- `src/vyu/deployment/release_handoff.py`
- `scripts/build_deployment_release_handoff.py`
- `tests/test_deployment_release_handoff.py`

The handoff bundle does not execute shell commands, sign artifacts, append to a production database, call a CI vendor, deploy infrastructure, or integrate with a production identity provider. It only reads local JSON evidence already produced by earlier deployment modules.

## Handoff Behavior

`build_deployment_release_handoff_bundle(...)` records:

1. release evidence summary path;
2. deployment release review decision path;
3. SHA-256 for both input files;
4. schema version and status for both input records;
5. package metadata from the release evidence summary;
6. upstream artifact hashes from the release evidence summary;
7. command-summary metadata from the release evidence summary;
8. reviewer metadata from the review decision;
9. decision metadata from the review decision;
10. top-level status `ready` or `blocked`.

A handoff bundle is `ready` only when:

- both input files are readable;
- both input files contain JSON objects;
- the release evidence summary schema is supported;
- the release review decision schema is supported;
- the release evidence summary status is `ready`;
- the release review decision status is `approved`;
- `review_summary_hash_matches_input` confirms the review decision's recorded summary SHA-256 equals the supplied summary file SHA-256;
- `review_summary_path_matches_input` confirms the review decision references the supplied summary path;
- package metadata matches between summary and review;
- upstream artifact hashes match between summary and review;
- the review decision value is `approve`;
- the review decision has no blocking reasons;
- reviewer metadata is present.

The top-level JSON includes:

- `schema_version`
- `status`
- `created_at`
- `summary_path`
- `review_path`
- `inputs.release_evidence_summary.sha256`
- `inputs.release_review_decision.sha256`
- `package`
- `artifact_hashes.release_evidence_summary_sha256`
- `artifact_hashes.release_review_decision_sha256`
- `artifact_hashes.package_evidence_sha256`
- `artifact_hashes.release_checklist_sha256`
- `artifact_hashes.transcript_bundle_sha256`
- `command_summary.commands_match`
- `reviewer.id`
- `reviewer.role`
- `decision.value`
- `decision.comment`
- `checks[].name`
- `review_summary_hash_matches_input`
- `review_summary_path_matches_input`
- `review_status_approved`
- `review_decision_approves`
- `review_blocking_reasons_absent`
- `artifact_hashes_match_review`
- `package_metadata_matches_review`

## Operator Command

Run after the release evidence summary and release review decision are present:

```bash
python scripts/build_deployment_release_handoff.py \
  --summary outputs/deployment_release_evidence_summary.json \
  --review outputs/deployment_release_review_decision.json \
  --created-at 2026-06-15T03:00:00Z \
  --output outputs/deployment_release_handoff.json
```

Expected output when the approved review is bound to the supplied release evidence summary:

```json
{
  "status": "ready"
}
```

Expected output when the review is blocked, stale, mismatched, or not bound to the supplied summary:

```json
{
  "status": "blocked"
}
```

The command exits with status code `0` for ready handoff bundles, `1` for blocked handoff bundles, and `2` for malformed command metadata or write errors.

## Failure Checks

The handoff bundle blocks when:

- either input file is missing;
- either input file is not valid JSON;
- either schema version is unsupported;
- the release evidence summary is not `ready`;
- the release review decision is not `approved`;
- the review decision was recorded against a different summary SHA-256;
- the review decision references a different summary path;
- package metadata differs between summary and review;
- upstream artifact hashes differ between summary and review;
- the review decision is not `approve`;
- review blocking reasons are present;
- reviewer metadata is missing.

## Relationship to Earlier Deployment Modules

```text
scripts/build_deployment_release_handoff.py
  -> DeploymentReleaseHandoffBundle
    -> outputs/deployment_release_evidence_summary.json
      -> package evidence + release checklist + transcript bundle
    -> outputs/deployment_release_review_decision.json
      -> operator approve/block decision bound to summary SHA-256
```

This module is intentionally the final local packaging handoff layer. It does not replace deployment automation; it produces a deterministic local manifest that an operator can inspect before any future CI/CD, signing, SBOM, or cloud deployment work is selected.

## Current Limits

- Local JSON handoff manifest only.
- No arbitrary shell execution.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add a local deployment release handoff archive/inventory that packages the handoff manifest and referenced JSON evidence files into a deterministic local archive, without signing, executing commands, or integrating with CI/cloud infrastructure.
