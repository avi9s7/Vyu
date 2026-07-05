# Report Export Route Runtime

The report-export route runtime is the framework-neutral HTTP-shaped boundary for report export.

The implementation is `src/vyu/entrypoints/report_export_routes.py`. It does not start a web server or choose a framework. It maps HTTP-shaped request data into the existing report-export API adapter so a later FastAPI, Flask, serverless, or gateway layer can call the same tested path.

## Route Runtime

Implemented route:

| Path | Method | Behavior |
| --- | --- | --- |
| `/v1/report-exports` | `POST` | Loads the persisted review task and phase-output artifacts, then calls `handle_report_export_api` |

Required body fields:

- `review_id`
- `report_type`

Required identity headers:

- `x-vyu-user-id`
- `x-vyu-role`
- `x-vyu-tenant-id`
- `x-vyu-workspace-id`

Optional headers:

- `x-vyu-request-id`

## Artifact Loading

`PhaseOutputReportArtifactStore` loads the current local phase-output layout:

- `phase4/grounded_answer.json`
- `phase4/evidence_context.json`
- `phase5/governance_audit_record.json`

This keeps the route runtime usable before deployed object storage exists. A future production artifact store can implement the same `ReportExportArtifactStore` protocol.

## Audit Behavior

When the runtime is created with `ProductionStorage`, report-export calls can persist the same audit events as other report-export paths:

- `prompt_injection_decision_recorded`
- `citation_policy_decision_recorded`
- `report_export_decision_recorded`

## Current Limits

- No web framework is selected.
- No deployed object-store loader is implemented.
- The local phase-output artifact store assumes one run per output directory.
- Authentication is still supplied as trusted headers unless the deployment HTTP adapter is placed in front of the service runtime.
