# Report Export Policy

## Purpose

This document defines the first production-shaped report export gate for Vyu. It gives future API, worker, and report-download paths a single policy boundary to call before releasing exportable evidence briefs, research reports, or policy outputs.

## Report Export Gate

The implementation is `src/vyu/reports/export.py`.
When called with a production storage adapter, the export gate records prompt-injection, citation-policy, and final report-export allow/block decisions as production audit events before returning the export result.
Framework-neutral API and worker adapters live in `src/vyu/entrypoints/report_export.py` and call the same gate without introducing a web framework or queue dependency.
The framework-neutral route runtime lives in `src/vyu/entrypoints/report_export_routes.py` and maps HTTP-shaped export requests into the same API adapter.
The local operator command `scripts/export_report_from_store.py` loads persisted Phase 4/5 artifacts and the persisted review task before calling the same report export adapter.

Before rendering a report, the export gate checks:

- tenant/workspace authorization with `Action.EXPORT_REPORT`
- human-review export state through `evaluate_export_gate`
- prompt-injection risk in the evidence context
- citation policy for invalid citations and uncited material claims

The gate fails closed. If any check blocks export, the returned result contains no report content and includes a blocking reason.

## Exportable Report Types

| Type | Renderer |
| --- | --- |
| `evidence_brief` | `render_evidence_brief` |
| `research_report` | `render_research_report` |
| `policy_output` | `render_policy_output` |

## Blocking Reasons

| Reason | Meaning |
| --- | --- |
| `export_not_authorized` | Principal lacks export permission in the report scope |
| `review_required` | Human review is required and still pending |
| `review_rejected` | Human review rejected the output |
| `prompt_injection_risk` | Evidence context contains prompt-injection signals |
| `citation_policy_blocked` | Citation validation or citation policy failed |

## Audit Events

When storage is provided, report export can write these production audit event types:

| Event type | Meaning |
| --- | --- |
| `prompt_injection_decision_recorded` | Prompt-injection scan result for the evidence context |
| `citation_policy_decision_recorded` | Citation validation and export-policy result |
| `report_export_decision_recorded` | Final report-export allow/block result, report type, scope, reviewer task, and principal |

## Current Limitations

- There is no deployed web framework, worker queue, or report-download route yet.
- The framework-neutral route runtime exists, but no framework-specific FastAPI/Flask/serverless adapter is wired yet.
- Stored review tasks, review decisions, connector health records, staged connector validation records, privacy approval records, safety decision audit events, and final report-export decision audit events are inspectable through `scripts/inspect_production_store.py`.
