# Compliance Evidence Bundle

This document defines the first local compliance evidence bundle for Vyu pilot review. It packages existing production-shaped evidence into one JSON artifact for reviewer intake.

The implementation is `scripts/build_compliance_evidence_bundle.py`. It does not replace legal, regulatory, clinical safety, privacy, or security review.

## Bundle Command

```bash
python scripts/build_compliance_evidence_bundle.py --sqlite-db outputs/production.sqlite --artifact-manifest outputs/artifact_manifest.json --source-registry config/source_registry.example.json --backup outputs/production_backup.json --drill-json outputs/incident_recovery_drill.json --output outputs/compliance_evidence_bundle.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command validates tenant/workspace scope through the production store before writing the output bundle.

To include local approver records that were already written for a prior bundle, add:

```bash
--attestations outputs/compliance_attestations.jsonl
```

## Bundle Contents

| Field | Meaning |
| --- | --- |
| `status` | `ready_for_pilot_review` when required local evidence is present; otherwise `attention` |
| `attention_reasons` | Machine-readable missing or blocked evidence reasons |
| `policy_documents` | Required production policy document paths and SHA-256 hashes |
| `source_approval` | Approved source records from the artifact manifest and source registry |
| `readiness` | Latest readiness check status and failed checks |
| `review` | Review status counts |
| `report_export` | Report-export allow/block evidence |
| `evidence_memory_retrieval` | Scoped evidence object, index, retrieval run, and research-memory counts |
| `evidence_grading_methodology` | Scoped methodology run, assessment, reviewer rating, and external grading connector counts |
| `governance_box_trust_score` | Scoped production Trust Score, Governance Box, reviewer override, and external governance connector counts |
| `observability` | Local observability snapshot status and attention reasons |
| `backup` | Backup schema versions and record counts |
| `incident_recovery_drill` | Drill status, incident detection, restore-count match, and restored observability status |
| `attestations` | Optional summary of matching local approver decisions from `outputs/compliance_attestations.jsonl` |
| `scoped_inspection` | Counts from scoped production-store inspection |

## Operator Interpretation

- `ready_for_pilot_review` means the local evidence package is complete enough for human pilot-review intake.
- `attention` means reviewers should inspect `attention_reasons` and the referenced evidence before proceeding.
- The bundle proves local artifact completeness and control evidence. It does not certify production compliance or healthcare deployment readiness.

## Current Limits

- The bundle is JSON-only and local.
- It does not include signatures, immutable storage, or external compliance-system uploads.
- It does not package real customer, PHI/ePHI, cloud, SSO, encryption, live external grading-vendor, live external governance-system, monitoring, or incident-response evidence.
