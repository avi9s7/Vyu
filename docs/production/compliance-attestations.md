# Compliance Attestations

This document defines the local approver attestation record used after a compliance evidence bundle is built.

The implementation is `scripts/record_compliance_attestation.py`. It creates append-only JSONL records that bind an approver decision to the exact SHA-256 hash of a compliance bundle file.

## Attestation Command

```bash
python scripts/record_compliance_attestation.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --approver-id privacy-owner --approver-role privacy_owner --decision approve --comment "Privacy evidence reviewed for pilot intake." --attested-at 2026-06-15T00:30:00Z
```

The command validates that the bundle `run_id`, `tenant_id`, and `workspace_id` match the requested scope before writing a record.

## Record Contents

| Field | Meaning |
| --- | --- |
| `attestation_id` | Deterministic local record ID for the run, approver, and role |
| `run_id` | Bundle run identifier |
| `tenant_id` | Tenant scope reviewed |
| `workspace_id` | Workspace scope reviewed |
| `approver_id` | Local approver identifier |
| `approver_role` | Review role, such as `privacy_owner` or `security_owner` |
| `decision` | `approve`, `request_changes`, or `reject` |
| `comment` | Human-readable review note |
| `attested_at` | Operator-provided timestamp |
| `bundle_status` | Bundle status at attestation time |
| `bundle_sha256` | SHA-256 hash of the exact bundle file reviewed |

## Decision Rules

- `approve` is allowed only when the bundle status is `ready_for_pilot_review`.
- `request_changes` and `reject` may be recorded for bundles that still require attention.
- Wrong tenant/workspace scope fails before the JSONL file is written.
- Records are local evidence only. They are not cryptographic signatures, immutable storage, or external compliance-system approvals.

## Bundle Integration

`scripts/build_compliance_evidence_bundle.py` accepts `--attestations outputs/compliance_attestations.jsonl` to include a summary of matching attestation records in the bundle output. This summary is informational and does not make the bundle ready on its own.
