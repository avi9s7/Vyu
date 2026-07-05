# Pilot Release Decision

This document defines the local pilot release-decision summary for Vyu. It combines compliance bundle readiness with required approver attestations into one deterministic go/no-go JSON artifact.

The implementation is `scripts/build_pilot_release_decision.py`. It does not replace legal, regulatory, clinical safety, privacy, security, or executive approval.

## Release Decision Command

```bash
python scripts/build_pilot_release_decision.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --output outputs/pilot_release_decision.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --required-approver-role privacy_owner --required-approver-role security_owner --decided-at 2026-06-15T00:50:00Z
```

The command validates the compliance bundle scope before writing the release-decision output.

## Decision Inputs

| Input | Meaning |
| --- | --- |
| `--bundle` | Compliance evidence bundle to evaluate |
| `--attestations` | JSONL approver attestation records |
| `--required-approver-role` | Role that must have a latest `approve` attestation |
| `--run-id` | Run scope for the decision |
| `--tenant-id` | Tenant scope for the decision |
| `--workspace-id` | Workspace scope for the decision |
| `--decided-at` | Operator-provided decision timestamp |

## Output States

| Status | Meaning |
| --- | --- |
| `approved_for_pilot` | The bundle is `ready_for_pilot_review`, has no attention reasons, and every required approver role has a latest `approve` attestation |
| `blocked` | The bundle is not ready, has attention reasons, or at least one required approver role is missing or not approved |

Blocking reasons are machine-readable, such as `bundle_not_ready_for_pilot_review`, `required_attestation_missing:security_owner`, or `required_attestation_not_approved:security_owner`.

## Current Limits

- The release decision is local JSON only.
- It is not a signature, immutable approval, deployment control, or external governance workflow.
- It does not verify real customer, PHI/ePHI, cloud, SSO, encryption, monitoring, incident-response, or contractual evidence.
