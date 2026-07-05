# Reviewer Queue API

## Purpose

This document defines the framework-neutral reviewer queue route contracts that wrap `src/vyu/entrypoints/review_queue.py`. The current repository does not ship a web server; these contracts are implemented today by the entry adapter, the framework-neutral route runtime in `src/vyu/entrypoints/review_queue_routes.py`, and the local `scripts/inspect_review_queue.py` and `scripts/record_review_decision.py` operator commands.

## Route Contracts

### List Review Queue

```text
GET /review-queue?tenant_id={tenant_id}&workspace_id={workspace_id}&status={status}&run_id={run_id}
```

Required authorization:

- Authenticated principal must have `review_output` in the requested tenant/workspace.
- `reviewer`, `workspace_admin`, and `tenant_admin` roles satisfy the default policy.
- `researcher` does not satisfy the default policy.

Adapter mapping:

- Build `ReviewQueueListApiRequest`.
- Populate `ReviewQueueListPayload` with the authenticated principal, tenant/workspace, optional status, and optional run ID.
- Call `handle_review_queue_list_api`.

Success response:

```json
{
  "status_code": 200,
  "request_id": "request-id",
  "tenant_id": "local_tenant",
  "workspace_id": "local_workspace",
  "reason": "review_queue_loaded",
  "review_tasks": []
}
```

Forbidden response:

```json
{
  "status_code": 403,
  "request_id": "request-id",
  "tenant_id": "local_tenant",
  "workspace_id": "local_workspace",
  "reason": "review_queue_not_authorized",
  "review_tasks": []
}
```

### Record Review Decision

```text
POST /review-queue/{review_id}/decision
```

Request body:

```json
{
  "decision": "approve",
  "comment": "Evidence reviewed for export.",
  "decided_at": "2026-06-14T00:05:00Z"
}
```

Required authorization:

- Authenticated principal must have `review_output` for the review task scope.

Adapter mapping:

- Load the authenticated principal from the deployed auth layer.
- Build `ReviewQueueDecisionApiRequest`.
- Populate `ReviewQueueDecisionPayload` with the review ID, decision, comment, and decision timestamp.
- Call `handle_review_queue_decision_api`.

Success response:

```json
{
  "status_code": 200,
  "request_id": "request-id",
  "reason": "review_decision_recorded",
  "review_task": {
    "review_id": "review-local-phase-output-run",
    "run_id": "local-phase-output-run",
    "status": "approved"
  }
}
```

Forbidden response:

```json
{
  "status_code": 403,
  "request_id": "request-id",
  "reason": "review_decision_not_authorized",
  "review_task": null
}
```

## Local Operator Inspection

Until a web server is selected, operators can exercise the list contract against SQLite with:

```bash
python scripts/inspect_review_queue.py --sqlite-db outputs/production.sqlite --tenant-id local_tenant --workspace-id local_workspace --user-id reviewer-1 --role reviewer --status pending --run-id local-phase-output-run
```

The command prints the same response body shape as the list adapter plus `status_code`.

Operators can exercise the decision contract with:

```bash
python scripts/record_review_decision.py --sqlite-db outputs/production.sqlite --review-id review-local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --user-id reviewer-1 --role reviewer --decision approve --comment "Evidence reviewed for export." --decided-at 2026-06-15T00:05:00Z
```

The command prints the same response body shape as the decision adapter plus `status_code`, persists the updated review task, and records a `review_decision_recorded` audit event.

## Current Limitations

- No web server, authentication middleware, or deployed worker queue is wired yet.
- The framework-neutral route runtime maps HTTP-shaped requests into the same API adapter but does not expose a network listener.
- Authentication is represented by explicit CLI/user inputs in the local inspection and decision commands.
