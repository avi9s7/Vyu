# Deployment Smoke Test

This document defines the operator-facing local smoke-test command for the composed Vyu deployment graph.

The implementation is split between `src/vyu/deployment/smoke.py` and `scripts/smoke_test_deployment.py`. It does not start a web server, deploy cloud infrastructure, read environment variables, call external services, or replace production identity-provider validation.

## Smoke Test Contract

The command constructs the same local runtime graph as `src/vyu/deployment/composition.py`, then calls the composed `ServerlessDeploymentHandler` with API Gateway-style event dictionaries.

It runs three checks:

| Check | Event | Expected status | Expected reason |
| --- | --- | ---: | --- |
| `health` | `GET /v1/health` without bearer token | `200` | `service_healthy` |
| `authenticated_review_queue` | `GET /v1/review-queue` with a locally signed HS256 bearer token | `200` | `review_queue_loaded` |
| `fail_closed_bad_token` | `GET /v1/review-queue` with a malformed bearer token | `401` | `auth_token_invalid` |

The command exits `0` only when all checks pass. It exits `1` when the composed runtime returns an unexpected status or reason for any check. It exits `2` when local configuration is invalid.

Example:

```bash
python scripts/smoke_test_deployment.py \
  --sqlite-db outputs/production.sqlite \
  --output-dir outputs \
  --issuer https://issuer.example \
  --audience vyu-api \
  --hs256-secret local-smoke-secret \
  --tenant-id local_tenant \
  --workspace-id local_workspace \
  --user-id reviewer-1 \
  --role vyu:reviewer
```

The JSON output includes:

```json
{
  "status": "pass",
  "summary": {
    "passed": 3,
    "failed": 0,
    "total": 3
  },
  "checks": [
    {
      "name": "health",
      "passed": true,
      "expected_status_code": 200,
      "actual_status_code": 200,
      "expected_reason": "service_healthy",
      "actual_reason": "service_healthy"
    },
    {
      "name": "authenticated_review_queue",
      "passed": true,
      "expected_status_code": 200,
      "actual_status_code": 200,
      "expected_reason": "review_queue_loaded",
      "actual_reason": "review_queue_loaded"
    },
    {
      "name": "fail_closed_bad_token",
      "passed": true,
      "expected_status_code": 401,
      "actual_status_code": 401,
      "expected_reason": "auth_token_invalid",
      "actual_reason": "auth_token_invalid"
    }
  ]
}
```

## Local Token Behavior

`DeploymentSmokeTestConfig` creates a short-lived local HS256 token only for this local smoke path. The token contains issuer, audience, subject, tenant, workspace, role, `iat`, `exp`, email, and email-verification claims. The composed runtime still validates that token through `Hs256BearerTokenAuthenticator` and maps trusted claims through `IdentityMapper`.

This does not introduce a production SSO/OIDC/JWKS provider. Production deployments must replace local HS256 smoke secrets with the approved identity-provider boundary.

## Failure Interpretation

Common failure reasons:

| Reason | Meaning |
| --- | --- |
| `service_healthy` missing | Composition, serverless conversion, or service-route health dispatch is broken. |
| `review_queue_loaded` missing | Token validation, identity mapping, route dispatch, or reviewer queue wiring is broken. |
| `auth_token_invalid` missing | Protected routes may not be failing closed for malformed bearer tokens. |
| `identity_mapping_failed` | The smoke token was authenticated but the configured role, tenant/workspace claims, issuer, or audience could not be mapped. |

## Current Limits

- This is a local smoke test, not a load test, security test, or cloud deployment verification.
- It does not seed review tasks; an empty reviewer queue is a passing local result.
- It does not validate CORS, WAF, rate limits, cloud IAM, TLS, logs, metrics exporters, or API Gateway configuration.
- It does not prove production identity-provider integration.

## Next Module Boundary

The next deployment module should add a local deployment environment example or operator config template that documents the explicit settings consumed by composition and smoke-test commands without storing real secrets.
