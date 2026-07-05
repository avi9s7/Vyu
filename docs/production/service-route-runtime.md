# Service Route Runtime

The service route runtime is the framework-neutral top-level request boundary for Vyu route dispatch.

The implementation is `src/vyu/entrypoints/service_routes.py`. It does not start a server or select a framework. It normalizes service-shaped requests, wraps responses in a consistent envelope, and dispatches to the reviewer queue and report-export route runtimes.

## Route Runtime

Implemented behavior:

- `GET /v1/health` returns a health envelope without requiring identity headers.
- `/v1/review-queue` and `/v1/review-queue/{review_id}/decision` dispatch to `ReviewQueueRouteRuntime`.
- `/v1/report-exports` dispatches to `ReportExportRouteRuntime`.
- Request headers are normalized to lowercase.
- `x-vyu-request-id` is preserved or generated.
- `x-vyu-audit-correlation-id` is preserved or defaulted to the request ID.
- Identity headers are validated before route dispatch.
- Optional trusted `identity_claims` can be mapped into internal Vyu identity headers before dispatch.

## Response Envelope

Successful route responses are wrapped as:

```json
{
  "request_id": "request-123",
  "audit_correlation_id": "request-123",
  "status": "ok",
  "reason": "review_queue_loaded",
  "data": {}
}
```

Errors use the same top-level fields and add an `error` object:

```json
{
  "request_id": "request-123",
  "audit_correlation_id": "request-123",
  "status": "error",
  "reason": "identity_required",
  "error": {
    "reason": "identity_required",
    "detail": "Missing required identity headers: x-vyu-role."
  },
  "data": {}
}
```

## Current Limits

- No concrete web framework adapter is implemented here.
- No deployed rate limiting, CORS, TLS, or request-size handling is implemented here.
- Raw token validation belongs in the deployment HTTP adapter or a framework-specific authentication layer.
