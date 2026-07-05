# VYU FastAPI Application and Job Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a versioned FastAPI service and idempotent SQS worker platform that exposes authenticated research-job APIs without running long work inside HTTP requests.

**Architecture:** FastAPI owns HTTP validation, authentication context, authorization, error envelopes, OpenAPI, and database transactions. PostgreSQL stores jobs, research runs, idempotency records, and outbox events atomically. A separate worker consumes minimal SQS messages and loads authoritative job state from PostgreSQL.

**Tech Stack:** FastAPI, Pydantic v2, Uvicorn, SQLAlchemy 2, Alembic, Psycopg 3, Boto3, Amazon SQS, PyJWT/cryptography, pytest, HTTPX.

---

## Entry Gate

- Plans 1 and 2 are complete.
- Alembic revision `0002` is current.
- Tenant RLS and append-only audit tests pass.

## Planned File Map

| Path | Responsibility |
| --- | --- |
| `apps/api/main.py` | FastAPI process entry point |
| `apps/worker/main.py` | Worker process entry point |
| `src/vyu/api/app.py` | App factory and lifecycle |
| `src/vyu/api/errors.py` | Stable error codes and exception mapping |
| `src/vyu/api/middleware.py` | Request ID, trace, timing, and safe logs |
| `src/vyu/api/dependencies.py` | Settings, sessions, principal, and scope dependencies |
| `src/vyu/api/routers/health.py` | Liveness, readiness, and version |
| `src/vyu/api/routers/research.py` | Research creation/status/cancel/events API |
| `src/vyu/jobs/models.py` | Job, idempotency, outbox, and research-run tables |
| `src/vyu/jobs/repository.py` | Job state machine and leases |
| `src/vyu/jobs/outbox.py` | Transactional outbox publisher |
| `src/vyu/jobs/queue.py` | SQS adapter and message schema |
| `src/vyu/jobs/worker.py` | Poll, lease, dispatch, retry, acknowledge, DLQ behavior |
| `src/vyu/migrations/versions/0003_jobs_research.py` | Job/research schema and RLS |
| `tests/api/` | API contract and authorization tests |
| `tests/integration/jobs/` | Outbox, duplicate delivery, lease, and recovery tests |

## Task 1: Add API and Queue Dependencies

**Files:** `pyproject.toml`, `uv.lock`, `tests/test_python_project_config.py`

- [ ] Add these runtime dependencies:

```toml
  "boto3>=1.36,<2",
  "cryptography>=44,<46",
  "fastapi>=0.115,<1",
  "httpx>=0.28,<1",
  "pyjwt>=2.10,<3",
  "uvicorn[standard]>=0.34,<1",
```

- [ ] Add test assertions that the six packages are declared, run the test and observe failure, update `pyproject.toml`, run `uv lock`, then run frozen sync.

- [ ] Run `uv run python -m unittest discover` and commit:

```powershell
git add pyproject.toml uv.lock tests/test_python_project_config.py
git commit -m "build: add API and queue dependencies"
```

## Task 2: Create Job and Research Schema Revision `0003`

**Files:**

- Create: `src/vyu/jobs/models.py`
- Create: `src/vyu/migrations/versions/0003_jobs_research.py`
- Create: `tests/integration/jobs/test_job_migration.py`

- [ ] Define these PostgreSQL tables with UUID keys and UTC timestamps:

```text
jobs(id, tenant_id, workspace_id, kind, status, attempt, max_attempts,
     payload, result, error_code, available_at, leased_until, lease_owner,
     created_at, started_at, completed_at, updated_at)
idempotency_keys(id, tenant_id, actor_id, route, key, request_sha256,
                 resource_type, resource_id, response_status, expires_at, created_at)
outbox_events(id, tenant_id, workspace_id, topic, aggregate_type,
              aggregate_id, payload, created_at, published_at, attempt, last_error)
research_runs(id, tenant_id, workspace_id, created_by, question, intended_use,
              requested_sources, status, current_step, cancel_requested,
              policy_version, created_at, started_at, completed_at, updated_at)
research_run_events(id, tenant_id, workspace_id, research_run_id, sequence,
                    event_type, safe_message, details, created_at)
```

- [ ] Add constraints:

- Job status is one of `queued`, `running`, `succeeded`, `failed`, `blocked`, `cancelled`.
- Research status is one of `queued`, `planning`, `searching`, `retrieving`, `synthesizing`, `review_required`, `completed`, `failed`, `blocked`, `cancelled`.
- Idempotency `(tenant_id, actor_id, route, key)` is unique.
- Research event `(research_run_id, sequence)` is unique.
- Outbox indexes unpublished events by `created_at`.
- Job lease index covers `status`, `available_at`, and `leased_until`.

- [ ] Enable and force RLS on every new table using exact tenant/workspace policies from Plan 2.

- [ ] Write migration tests that upgrade from `0002` to `0003`, inspect tables/constraints/policies, downgrade to `0002`, and upgrade again.

- [ ] Verify:

```powershell
uv run alembic upgrade head
uv run pytest tests/integration/jobs/test_job_migration.py tests/integration/db -q
```

Expected: current revision `0003`; all migration and RLS tests pass.

- [ ] Commit:

```powershell
git add src/vyu/jobs/models.py src/vyu/migrations/versions/0003_jobs_research.py tests/integration/jobs/test_job_migration.py
git commit -m "feat: add durable job and research schema"
```

## Task 3: Implement the Job State Machine and Idempotency

**Files:**

- Create: `src/vyu/jobs/contracts.py`
- Create: `src/vyu/jobs/repository.py`
- Create: `tests/integration/jobs/test_job_repository.py`

- [ ] Write tests for these legal transitions:

```text
queued -> running
running -> succeeded | failed | blocked | cancelled
queued -> cancelled
failed -> queued only when attempt < max_attempts and available_at is set
```

Assert every other transition raises `InvalidJobTransition` and leaves the database unchanged.

- [ ] Implement immutable dataclasses `NewJob`, `JobRecord`, `JobLease`, `IdempotencyRequest`, and `IdempotencyResult`.

- [ ] Implement required repository methods:

```python
create_job(new_job, session) -> JobRecord
acquire_job(job_id, worker_id, lease_seconds, session) -> JobLease | None
extend_lease(job_id, worker_id, lease_seconds, session) -> JobLease
complete_job(job_id, worker_id, result, session) -> JobRecord
fail_job(job_id, worker_id, error_code, retry_at, session) -> JobRecord
request_cancellation(job_id, session) -> JobRecord
get_or_create_idempotent(request, create_resource, session) -> IdempotencyResult
```

Use `SELECT ... FOR UPDATE SKIP LOCKED` when leasing. Hash normalized JSON with SHA-256. Reusing a key with a different request hash raises `IdempotencyConflict`.

- [ ] Test simultaneous lease attempts with two database sessions; exactly one worker obtains the lease.

- [ ] Verify and commit:

```powershell
uv run pytest tests/integration/jobs/test_job_repository.py -q
uv run ruff check src/vyu/jobs tests/integration/jobs
uv run mypy
git add src/vyu/jobs tests/integration/jobs pyproject.toml
git commit -m "feat: add idempotent job state machine"
```

## Task 4: Create the FastAPI App Factory and Error Contract

**Files:**

- Create: `src/vyu/api/app.py`
- Create: `src/vyu/api/errors.py`
- Create: `src/vyu/api/middleware.py`
- Create: `src/vyu/api/routers/health.py`
- Create: `apps/api/main.py`
- Create: `tests/api/test_health.py`
- Create: `tests/api/test_error_contract.py`

- [ ] Write tests asserting:

- `GET /v1/health/live` returns `200` without authentication.
- `GET /v1/health/ready` verifies database connectivity and returns `503` with code `dependency_unavailable` when the check fails.
- `GET /v1/version` returns build SHA, image digest when provided, environment, and schema revision without secrets.
- Unknown routes use the common error envelope.
- Validation errors return code `validation_error`, field paths, request ID, and trace ID.
- Unhandled exceptions return `internal_error` without exception text.

- [ ] Use this response shape everywhere:

```json
{
  "request_id": "req_...",
  "trace_id": "...",
  "status": "error",
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "retryable": false,
    "fields": [{"path": "body.question", "code": "string_too_short"}]
  }
}
```

- [ ] Middleware accepts a valid `x-request-id` of at most 128 safe characters or generates a UUID, records duration/status, and never logs authorization, cookie, body, prompt, or document content.

- [ ] `create_app(settings_override=None)` performs composition only. It does not create tables. Startup verifies expected Alembic revision and required dependencies.

- [ ] Verify:

```powershell
uv run pytest tests/api/test_health.py tests/api/test_error_contract.py -q
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/health/live
Invoke-RestMethod http://127.0.0.1:8000/v1/version
```

Expected: safe `200` responses with request IDs.

- [ ] Commit:

```powershell
git add src/vyu/api apps/api tests/api pyproject.toml
git commit -m "feat: add FastAPI app and stable error contract"
```

## Task 5: Bind OIDC Identity and PostgreSQL Membership

**Files:**

- Create: `src/vyu/api/dependencies.py`
- Create: `src/vyu/auth/principal.py`
- Modify: `src/vyu/deployment/idp.py`
- Create: `tests/api/test_authentication.py`
- Create: `tests/api/test_tenant_authorization.py`

- [ ] Reuse the existing OIDC/JWKS cryptographic validation only after tests prove issuer, audience, algorithm, token use, expiry, and email-verification checks. Move framework-independent claim validation behind a `TokenVerifier` protocol; do not import FastAPI in the verifier.

- [ ] Define `RequestPrincipal` with trusted `user_id`, issuer, subject, email, tenant/workspace scope, role, and authentication method.

- [ ] The FastAPI dependency must:

1. Require bearer authentication for protected routes.
2. Verify the token.
3. Upsert the external identity without trusting tenant role claims.
4. Load an active exact-scope membership from PostgreSQL.
5. Narrow the claimed role to the stored role.
6. Set `TenantScope` on the transaction.
7. Append allowed/denied identity audit events.

- [ ] Tests must prove missing/invalid/expired tokens return `401`, inactive membership returns `403`, cross-tenant resource returns `404`, and a claimed admin role is narrowed to stored reviewer.

- [ ] Keep local HS256 support behind `VYU_AUTH_MODE=local_hs256` and make settings reject that mode in staging/production.

- [ ] Verify and commit:

```powershell
uv run pytest tests/api/test_authentication.py tests/api/test_tenant_authorization.py -q
git add src/vyu/api/dependencies.py src/vyu/auth src/vyu/deployment/idp.py tests/api
git commit -m "security: bind OIDC identities to database membership"
```

## Task 6: Add Research Creation, Status, Cancellation, and Events

**Files:**

- Create: `src/vyu/api/schemas/research.py`
- Create: `src/vyu/api/routers/research.py`
- Create: `src/vyu/research/service.py`
- Create: `tests/api/test_research_routes.py`

- [ ] Define strict request schema:

```text
question: trimmed string, 10..2000 characters
source_ids: 1..10 unique source IDs
date_from/date_to: optional valid range
evidence_types: unique approved enum values
population/intervention/comparator: optional, each <= 500 characters
only_approved_sources: must be true in staging/production
```

- [ ] `POST /v1/research/searches` requires `Idempotency-Key`, creates research/job/outbox/audit records in one transaction, and returns `202` with `search_id`, `job_id`, `status=queued`, and URLs.

- [ ] `GET` list/detail/events routes enforce scope and cursor pagination. Cancel sets `cancel_requested` and emits an event; it does not delete history.

- [ ] Tests cover duplicate same-body idempotency, conflicting-body idempotency, invalid date range, unapproved source, cross-tenant lookup, cancellation, and event ordering.

- [ ] Generate OpenAPI and assert route/schema snapshots:

```powershell
uv run pytest tests/api/test_research_routes.py -q
uv run python scripts/export_openapi.py --output docs/api/openapi.json
```

- [ ] Commit:

```powershell
git add src/vyu/api/schemas src/vyu/api/routers/research.py src/vyu/research tests/api/test_research_routes.py scripts/export_openapi.py docs/api/openapi.json
git commit -m "feat: add asynchronous research API"
```

## Task 7: Publish Outbox Events to SQS

**Files:**

- Create: `src/vyu/jobs/queue.py`
- Create: `src/vyu/jobs/outbox.py`
- Create: `tests/integration/jobs/test_outbox_publisher.py`

- [ ] Define message schema containing only `schema_version`, `message_id`, `job_id`, `tenant_id`, `workspace_id`, `kind`, `attempt`, and `created_at`. Do not include the research question or source documents.

- [ ] Implement `SqsQueue.send(message)` with explicit queue URL, connect/read timeouts, and no SDK retry amplification beyond the configured policy.

- [ ] Publisher locks unpublished outbox rows with `SKIP LOCKED`, sends one message, then records `published_at`. If sending fails, it records safe `last_error` and increments attempt without marking published.

- [ ] Tests use LocalStack or a stubbed Boto3 client and prove unpublished recovery, duplicate publisher safety, minimal message payload, and no publish before database commit.

- [ ] Verify and commit:

```powershell
uv run pytest tests/integration/jobs/test_outbox_publisher.py -q
git add src/vyu/jobs/queue.py src/vyu/jobs/outbox.py tests/integration/jobs/test_outbox_publisher.py
git commit -m "feat: publish transactional outbox events to SQS"
```

## Task 8: Implement Idempotent Worker Execution

**Files:**

- Create: `src/vyu/jobs/worker.py`
- Create: `apps/worker/main.py`
- Create: `tests/integration/jobs/test_worker.py`

- [ ] Worker loop uses SQS long polling, validates message schema, loads job by ID and scope, acquires a lease, dispatches by job kind, extends visibility/lease by heartbeat, and deletes the message only after the terminal state commits.

- [ ] Duplicate message for a succeeded/blocked/cancelled job is acknowledged without rerunning the handler.

- [ ] Retryable failure increments attempt and schedules exponential backoff with jitter. Terminal, policy, validation, and exhausted failures persist safe codes and acknowledge so SQS redrive policy can isolate poison messages.

- [ ] Tests prove duplicate delivery, worker crash before commit, crash after commit before delete, lease expiration, cancellation, heartbeat, retry exhaustion, and unknown job kind.

- [ ] Add signal handling so ECS stop requests cease polling, finish or release the active lease within the stop timeout, and exit nonzero only for process-level failure.

- [ ] Verify and commit:

```powershell
uv run pytest tests/integration/jobs/test_worker.py -q
git add src/vyu/jobs/worker.py apps/worker tests/integration/jobs/test_worker.py
git commit -m "feat: add idempotent SQS worker runtime"
```

## Task 9: Add API/Worker Containers and CI

**Files:**

- Create: `deploy/docker/api.Dockerfile`
- Create: `deploy/docker/worker.Dockerfile`
- Create: `.dockerignore`
- Modify: `compose.yaml`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/production/IMPLEMENTATION_STATUS.md`

- [ ] Use a pinned Python 3.13 slim image digest, non-root UID, read-only-compatible filesystem, exec-form command, `uv sync --frozen --no-dev`, health check, and no copied `.env`, Git metadata, outputs, caches, or tests in runtime layers.

- [ ] API command runs one Uvicorn process per ECS task. Horizontal ECS tasks, not multiple hidden processes, provide replication.

- [ ] Worker image uses the same application wheel and a different exec command.

- [ ] Compose adds API, worker, and LocalStack services. API waits for PostgreSQL migration/health; worker waits for PostgreSQL and LocalStack.

- [ ] CI builds both images, scans them in Plan 4's security workflow, starts compose, runs migrations, submits one authenticated test research job, observes `queued`, and verifies duplicate submission returns the same IDs.

- [ ] Update Plan 3 status with OpenAPI artifact, migration `0003`, CI run, image test digests, duplicate-delivery evidence, and tenant authorization evidence.

- [ ] Commit:

```powershell
git add deploy/docker .dockerignore compose.yaml .github/workflows/ci.yml docs/production/IMPLEMENTATION_STATUS.md
git commit -m "build: containerize API and worker platform"
```

## Exit Gate

- FastAPI liveness, readiness, version, errors, auth, and research routes pass contract tests.
- OpenAPI is generated and checked for drift.
- Research submission atomically creates research, job, outbox, and audit records.
- Same idempotency key/body returns original IDs; different body conflicts.
- SQS messages contain no question or document content.
- Duplicate and crash tests prove external work is not repeated after terminal persistence.
- Cross-tenant API tests pass.
- API and worker containers run as non-root and pass compose smoke tests.
- Existing POC tests remain green.

## Handoff to Plan 4

Plan 4 deploys these immutable API/worker images and the migration task to AWS. Plan 5 registers ingestion handlers; Plan 6 registers research planning/retrieval handlers; Plan 7 registers synthesis handlers. Do not add those workflows directly to the generic worker loop.

