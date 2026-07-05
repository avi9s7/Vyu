# Reviewer Queue Route Runtime

This document defines the first framework-neutral reviewer queue route runtime for Vyu.

The implementation is `src/vyu/entrypoints/review_queue_routes.py`. It does not start a web server or choose a framework. It maps HTTP-shaped request data into the existing reviewer queue API adapter so a later FastAPI, Flask, serverless, or gateway layer can call the same tested path.

## Route Runtime

| Route | Method | Handler behavior |
| --- | --- | --- |
| `/v1/review-queue` | `GET` | Lists scoped review tasks through `handle_review_queue_list_api` |
| `/v1/review-queue/{review_id}/decision` | `POST` | Records an approve/reject decision through `handle_review_queue_decision_api` |

The runtime reads the authenticated principal from route headers:

- `x-vyu-user-id`
- `x-vyu-role`
- `x-vyu-tenant-id`
- `x-vyu-workspace-id`
- `x-vyu-request-id`, optional

## List Request

The list route accepts query parameters:

- `tenant_id`
- `workspace_id`
- `status`, optional
- `run_id`, optional

The response body matches the existing review queue API adapter and includes `reason` plus `review_tasks`.

## Decision Request

The decision route accepts JSON fields:

- `decision`: `approve` or `reject`
- `comment`
- `decided_at`

The response body matches the existing review decision API adapter and includes `reason` plus `review_task`.

## Error Handling

- Unauthorized principals receive `403` with `review_queue_not_authorized` or `review_decision_not_authorized`.
- Unknown route paths receive `404` with `route_not_found`.
- Malformed route input receives `400` with `route_bad_request`.

## Current Limits

- No web server, router, authentication middleware, CSRF protection, or browser UI is included.
- The route runtime trusts already-normalized headers from a future deployed auth layer.
- Report-export routes are still handled by framework-neutral API/worker adapters and are not wired into a route runtime yet.
