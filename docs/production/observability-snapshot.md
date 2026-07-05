# Observability Snapshot

This document defines the first local production-shaped observability snapshot for Vyu. It summarizes one scoped run from the SQLite production store so operators can quickly see readiness, review, connector, evidence-memory/retrieval, evidence-grading methodology, external grading connector, Governance Box/Trust Score, external governance connector, report-export, and audit-event state without reading every raw record.

The implementation is `scripts/summarize_production_observability.py`. It is not a deployed metrics backend, log pipeline, tracing system, alert manager, or dashboard.

## Snapshot Command

```bash
python scripts/summarize_production_observability.py --sqlite-db outputs/production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command returns JSON and rejects the request if the run is outside the requested tenant/workspace scope.

## Snapshot Fields

| Field | Meaning |
| --- | --- |
| `status` | `ok` when no attention reasons are present; otherwise `attention` |
| `attention_reasons` | Machine-readable reasons such as `review_pending`, `readiness_missing`, or `allowed_report_export_missing` |
| `readiness` | Latest readiness status, result ID, failed checks, and result count |
| `review` | Review task count and review status counts |
| `connectors` | Connector health and staged-validation counts by status and source |
| `evidence_memory_retrieval` | Evidence object, retrieval index, retrieval run, and production research-memory record counts |
| `evidence_grading_methodology` | Methodology run, document assessment, reviewer rating, external request/response, strength-band, source, and human-review counts |
| `governance_box_trust_score` | Production Trust Score, Governance Box, reviewer override, external governance request/response, decision/export status, provider, and overall-score counts |
| `report_export` | Report-export attempts, allowed/blocked counts, and latest reason |
| `audit_events` | Total audit-event count and event-type counts |

## Operator Interpretation

- `ok` means the local run has passing readiness evidence, no pending or rejected review tasks, and at least one allowed report-export decision.
- `attention` means at least one prerequisite is missing or blocked. Operators should inspect `attention_reasons` first, then use `scripts/inspect_production_store.py` for raw record detail.
- The snapshot is scoped to a single run and tenant/workspace. It does not aggregate across customers, environments, or time windows.

## Current Limits

- No alert routing, SLOs, dashboards, or production telemetry export exist yet.
- No long-term trend storage exists beyond the underlying SQLite records.
- The snapshot reports local record state only; it does not prove infrastructure health, live evidence-grading vendor availability, live external governance-system availability, live service availability, or incident response readiness.
