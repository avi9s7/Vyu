# Human Review Workflow

## Purpose

This document defines the first production-shaped human review and export-gating workflow for Vyu. It is a local control baseline for pilot-style review and does not replace a full reviewer UI, queue service, notification system, or production audit store.

## Review Task Model

A review task is created from a governed run and includes:

- `review_id`
- `run_id`
- `tenant_id`
- `workspace_id`
- review status
- governance review reason
- creation timestamp
- optional reviewer decision record

The local implementation is `src/vyu/review/`.
Persisted queue service helpers are implemented in `src/vyu/review/queue.py`.
Framework-neutral API and worker adapters live in `src/vyu/entrypoints/review_queue.py`.
Route contracts are documented in `docs/production/reviewer-queue-api.md`, and the first framework-neutral route runtime is documented in `docs/production/reviewer-queue-route-runtime.md`.

## Statuses

| Status | Meaning |
| --- | --- |
| `not_required` | Governance does not require review before export |
| `pending` | Human review is required and no decision has been recorded |
| `approved` | An authorized reviewer approved export |
| `rejected` | An authorized reviewer rejected export |

## Reviewer Decisions

Authorized reviewers can record:

- `approve`
- `reject`
- reviewer comment
- decision timestamp

Review decisions use `AuthorizationPolicy.require` with the `review_output` action, so researchers cannot approve or reject high-risk outputs by default.

## Reviewer Queue

The queue service can:

- load persisted review tasks for a tenant/workspace scope
- filter queued tasks by review status
- record authorized approve/reject decisions with audit events

Queue loading uses the same `review_output` authorization action as review decisions. It returns only tasks in the requested tenant/workspace scope.

API-shaped and worker-shaped adapters can list queues and record decisions through the same service boundary without introducing a web framework or queue dependency.

The representative phase-output runner creates a pending persisted review task for the run when its generated governance box requires human review. The standard local fixture currently creates `review-local-phase-output-run`.

## Export Gate

Export decisions use the `export_report` authorization action and the review task status.

| Condition | Export decision |
| --- | --- |
| Principal lacks `export_report` permission | Blocked: `export_not_authorized` |
| Review is not required | Allowed: `review_not_required` |
| Review is pending | Blocked: `review_required` |
| Review is approved | Allowed: `review_approved` |
| Review is rejected | Blocked: `review_rejected` |

## Current Limitations

- There is no reviewer queue UI.
- There are no notifications or reviewer UI yet.
- A framework-neutral reviewer queue route runtime exists, but no web server, auth middleware, or deployed worker queue is wired yet.
- Framework-neutral report-export API and worker adapters exist, but report-export routes are not wired into a route runtime yet.
