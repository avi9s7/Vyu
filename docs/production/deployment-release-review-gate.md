# Deployment Release Review Gate

## Release Review Gate Contract

The deployment release review gate records a local operator decision against `outputs/deployment_release_evidence_summary.json`. It binds the decision to the release evidence summary SHA-256 and writes one deterministic JSON decision record for deployment handoff.

Implemented files:

- `src/vyu/deployment/release_review.py`
- `scripts/review_deployment_release_evidence.py`
- `tests/test_deployment_release_review.py`

The review gate does not execute shell commands, sign artifacts, append to a production database, call a CI vendor, deploy infrastructure, or integrate with a production identity provider. It only reads the local release evidence summary and writes a local decision record.

## Review Behavior

`build_deployment_release_review_decision(...)` records:

1. release evidence summary path;
2. summary SHA-256;
3. summary schema version, status, and created timestamp;
4. package metadata from the summary;
5. upstream summary artifact hashes;
6. command-summary metadata from the summary;
7. reviewer ID and reviewer role;
8. operator decision value and comment;
9. decision timestamp;
10. top-level status `approved` or `blocked`.

A review decision is `approved` only when:

- the summary file is readable;
- the summary file is valid JSON;
- the summary schema is supported;
- the summary status is `ready`;
- the reviewer metadata is present;
- the decision is `approve`.

A decision is `blocked` when the operator chooses `block` or when any approval prerequisite fails. This lets operators record explicit holds without approving stale or incomplete deployment evidence.

The top-level JSON includes:

- `schema_version`
- `status`
- `decision_id`
- `decided_at`
- `summary_path`
- `summary.sha256`
- `summary.status`
- `summary.schema_version`
- `package`
- `summary_artifact_hashes.package_evidence_sha256`
- `summary_artifact_hashes.release_checklist_sha256`
- `summary_artifact_hashes.transcript_bundle_sha256`
- `command_summary.commands_match`
- `reviewer.id`
- `reviewer.role`
- `decision.value`
- `decision.comment`
- `blocking_reasons`
- `review_summary.failed`
- `checks[].name`
- `summary_file_readable`
- `summary_json_valid`
- `summary_schema_supported`
- `summary_status_ready`
- `decision_supported`
- `reviewer_metadata_present`
- `approve_requires_ready_summary`

## Operator Command

Run after the release evidence summary is ready:

```bash
python scripts/review_deployment_release_evidence.py \
  --summary outputs/deployment_release_evidence_summary.json \
  --decision approve \
  --reviewer-id deployment-operator \
  --reviewer-role deployment_operator \
  --comment "Deployment release evidence reviewed locally." \
  --decided-at 2026-06-15T02:45:00Z \
  --output outputs/deployment_release_review_decision.json
```

To record an operator hold instead of approval:

```bash
python scripts/review_deployment_release_evidence.py \
  --summary outputs/deployment_release_evidence_summary.json \
  --decision block \
  --reviewer-id deployment-operator \
  --reviewer-role deployment_operator \
  --comment "Holding release for deployment window." \
  --decided-at 2026-06-15T02:45:00Z \
  --output outputs/deployment_release_review_decision.json
```

Expected output for an approved decision:

```json
{
  "status": "approved"
}
```

Expected output for a blocked decision or failed approval prerequisite:

```json
{
  "status": "blocked"
}
```

The command exits with status code `0` for approved decisions, `1` for blocked decisions, and `2` for malformed review metadata or write errors.

## Failure Checks

The review gate blocks approval when:

- the summary file is missing;
- the summary file is not valid JSON;
- the summary schema version is unsupported;
- summary status is not `ready`;
- reviewer metadata or comment is missing;
- the operator decision is `block`.

## Relationship to Earlier Deployment Modules

```text
scripts/review_deployment_release_evidence.py
  -> DeploymentReleaseReviewDecision
    -> outputs/deployment_release_evidence_summary.json
      -> outputs/deployment_package_evidence.json
      -> outputs/deployment_release_package_checklist.json
      -> outputs/deployment_transcript_bundle.json
```

This module is intentionally the local review layer. The release evidence summary binds the upstream package, checklist, and transcript evidence. The review gate records an operator approve/block decision against that bound summary hash.

## Current Limits

- Local JSON decision record only.
- No arbitrary shell execution.
- No CI vendor integration.
- No production persistence or audit database write.
- No KMS, signing, Sigstore, SLSA attestation, SBOM, vulnerability scanning, Docker, Terraform, IAM, OIDC/JWKS, cloud deployment, CORS/WAF, or rate-limit configuration.

## Next Module Boundary

The next deployment module can add a local deployment release handoff bundle that packages the release evidence summary and review decision record into a deterministic handoff manifest, without signing, executing commands, or integrating with CI/cloud infrastructure.
