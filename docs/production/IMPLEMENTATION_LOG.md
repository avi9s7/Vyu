# VYU Implementation Log

Running record of what was built, verified, merged, and learned during the production migration. This complements `IMPLEMENTATION_STATUS.md` (plan-level gates) and the plan specs under `docs/superpowers/plans/`.

Repository: https://github.com/avi9s7/Vyu  
Last log update: 2026-07-06  
Last verified Git SHA: `76f1c178`

---

## Update rule (required after every implementation)

Update this log in the **same pull request** as the code change, before merge. Do not defer documentation to a follow-up PR unless the original PR is blocked and the gap is recorded here as a blocker.

For each completed task, plan slice, or merged PR, append or extend the relevant plan section with:

1. **Date** and **author/owner**
2. **Branch / PR / merge SHA**
3. **Goal** — what behavior or exit gate was targeted
4. **Changes** — files, schema revisions, config, CI, scripts (grouped by area)
5. **Tests & verification** — commands run, CI run URL, expected vs actual
6. **Decisions** — non-obvious design or security choices
7. **Issues fixed** — failures encountered and root cause (especially CI/local parity)
8. **Follow-ups** — known limits, deferred work, next plan entry criteria

Also update in the same PR:

- `docs/production/IMPLEMENTATION_STATUS.md` — one row when a plan gate changes
- Plan-specific docs named in `PRODUCTION_DOCUMENTATION_INDEX.md` (OpenAPI, runbooks, etc.)
- This log’s header **Last log update** and **Last verified Git SHA**

---

## Plan 1 — Repository baseline and engineering system

**Status:** complete  
**Owner:** avi9s7  
**PR:** https://github.com/avi9s7/Vyu/pull/1  
**Merge SHA:** `1b595b07fd7d45ad89b029f4e81ed1af4d3983cb`  
**Completed:** 2026-07-05

### Goal

Establish a reproducible engineering baseline: locked dependencies, lint/type/test/CI gates, clean-clone verification, and frontend test harness — without changing application runtime behavior beyond what Plan 1 specifies.

### Deliverables

| Area | Paths / artifacts |
| --- | --- |
|    | Repository hygiene | `.gitignore`, `.gitattributes`, `.editorconfig`, `.python-version`, `.nvmrc` |
| Python tooling | `pyproject.toml`, `uv.lock`, Ruff, Mypy, pytest, coverage config |
| Verification | `scripts/verify.py` with `--scope backend` and `--scope frontend` |
| CI | `.github/workflows/ci.yml` — backend (Ruff, Mypy, unittest) + frontend (typecheck, lint, Vitest, build) |
| Frontend tests | `apps/web/components/ui/Button.test.tsx`, Vitest setup |
| Status tracking | `docs/production/IMPLEMENTATION_STATUS.md` (created) |
| Upstream lock | `UPSTREAM_LOCK.json`, `UPSTREAM_COMMITS.txt` |

### Verification

- CI backend + frontend: success on PR #1
- Local: `uv run python scripts/verify.py --scope backend` and frontend scope via CI-equivalent npm scripts
- 404+ Python unit tests at exit gate

### Decisions

- **Scope split:** `verify.py` scopes keep backend unit work separate from frontend npm pipeline; Plan 2 added `integration` scope later.
- **Ruff per-file ignores:** Scripts may use late imports (`E402`); package `__init__` re-exports allowed where needed.
- **SQLite POC preserved:** Plan 1 does not remove existing SQLite production storage; PostgreSQL is introduced in Plan 2 alongside it.

### Notes for later plans

- Branch prefix convention: `cursor/<short-description>`
- One focused commit series per plan task; squash merge to `main`
- Do not mark a plan `complete` until merge SHA and durable CI evidence exist

---

## Plan 2 — PostgreSQL persistence and tenancy

**Status:** complete  
**Owner:** avi9s7  
**PR:** https://github.com/avi9s7/Vyu/pull/2  
**Merge SHA:** `ff3b90e6c4b1b683604c39b6db0941a2964c4788`  
**Status doc commit:** `6002d02f`  
**Alembic head:** `0002`  
**Green CI run:** https://github.com/avi9s7/Vyu/actions/runs/28745481470  
**Completed:** 2026-07-05

### Goal

Introduce PostgreSQL as the production system of record for identity/tenancy/audit foundations: SQLAlchemy models, Alembic migrations, focused repositories, row-level security (RLS), tenant registry import, and PostgreSQL integration tests in CI — while keeping the SQLite POC path available.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Application / import script / tests                          │
│  TenancyRepository, AuditRepository, transaction(scope)     │
└───────────────────────────┬─────────────────────────────────┘
                            │ VYU_DATABASE_URL (vyu_app)
                            │ VYU_MIGRATION_DATABASE_URL (vyu_migrator)
┌───────────────────────────▼─────────────────────────────────┐
│  PostgreSQL (pgvector/pgvector:0.8.0-pg17)                  │
│  Tables: tenants, users, workspaces, memberships, audit_events │
│  RLS (FORCE): workspaces, memberships, audit_events         │
│  Session vars: app.tenant_id, app.workspace_id              │
│  Trigger: audit_events append-only (0002)                   │
└─────────────────────────────────────────────────────────────┘
```

**Roles (local / CI):**

| Role | Purpose | RLS |
| --- | --- | --- |
| `test` (CI admin) / compose init | Bootstrap extensions and roles | superuser in CI service |
| `vyu_migrator` | Alembic DDL, registry import admin writes | NOBYPASSRLS — must set scope for RLS tables |
| `vyu_app` | Application runtime | NOBYPASSRLS NOSUPERUSER |

**Migrations:**

| Revision | File | Contents |
| ---: | --- | --- |
| 0001 | `src/vyu/migrations/versions/0001_tenancy_audit.py` | Tenancy + audit schema, pgvector extension, RLS policies, grants to `vyu_app` |
| 0002 | `src/vyu/migrations/versions/0002_audit_append_only.py` | `BEFORE UPDATE OR DELETE` trigger on `audit_events` |

### Deliverables

| Area | Paths |
| --- | --- |
| Local database | `compose.yaml`, `deploy/local/postgres/001_roles.sql`, `.env.example` |
| DB layer | `src/vyu/db/settings.py`, `session.py`, `models/*`, `repositories/*` |
| Migrations | `alembic.ini`, `src/vyu/migrations/env.py`, versions `0001`, `0002` |
| Import CLI | `scripts/import_tenant_registry.py` (`--dry-run` / `--apply`, deterministic UUIDs via `uuid5`) |
| CI | Postgres service in `.github/workflows/ci.yml`; split backend unit vs integration steps |
| Verify | `scripts/verify.py --scope integration` |
| Tests — unit | `tests/unit/db/test_session.py`, `tests/unit/db/test_settings.py` |
| Tests — integration | `tests/integration/db/*` (migrations, RLS, repositories, audit, import) |
| Tests — contract | `tests/test_local_postgres_contract.py` |
| Docs | `docs/production/tenant-governance.md` (PostgreSQL import section), `IMPLEMENTATION_STATUS.md` |

### Dependencies added (`pyproject.toml`)

- `alembic`, `psycopg`, `pydantic-settings`, `sqlalchemy`
- Dev: `testcontainers[postgres]`

### Verification commands

```powershell
# Backend unit (no Docker)
uv run python scripts/verify.py --scope backend

# Integration (Docker local OR CI env vars)
docker compose up -d postgres
uv run alembic upgrade head
$env:VYU_ADMIN_DATABASE_URL="postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu"
$env:VYU_MIGRATION_DATABASE_URL="postgresql+psycopg://vyu_migrator:local-migrator-password@127.0.0.1:5432/vyu"
$env:VYU_DATABASE_URL="postgresql+psycopg://vyu_app:local-vyu-password@127.0.0.1:5432/vyu"
uv run pytest tests/integration/db -vv --tb=short

# Registry import
uv run python scripts/import_tenant_registry.py --registry config/tenant_governance.local.example.json --dry-run
uv run python scripts/import_tenant_registry.py --registry config/tenant_governance.local.example.json --apply
```

### CI integration fixes (chronological)

These were required to get PostgreSQL integration tests green on GitHub Actions:

1. **CI Postgres service instead of testcontainers** — `tests/integration/db/conftest.py` uses `VYU_*_DATABASE_URL` when set; testcontainers only for local Docker.
2. **Role bootstrap SQL** — explicit statements in conftest; `001_roles.sql` for compose init.
3. **pgvector extension** — created by admin bootstrap before migrations (`vyu_migrator` is not superuser).
4. **`CREATE ROLE … PASSWORD`** — PostgreSQL rejects parameterized passwords; use literal local credentials in bootstrap (matches `001_roles.sql`).
5. **RLS seeding in tests** — migration role must set `app.tenant_id` / `app.workspace_id` when inserting into `workspaces`, `memberships`, `audit_events` (same pattern as `import_tenant_registry.py`).
6. **Savepoints on unique violations** — `TenancyRepository` and `AuditRepository` use `begin_nested()` before flush so duplicate-key handling does not invalidate the outer transaction.
7. **Append-only trigger test** — raw psycopg UPDATE must set tenant scope or RLS hides rows and the trigger never fires.
8. **Import idempotency counts** — second `--apply` must report zero new users; only increment when user row did not exist before upsert.

### Decisions

- **FORCE ROW LEVEL SECURITY** on tenant-scoped tables applies to `vyu_migrator` too; admin seeding uses scoped transactions, not BYPASSRLS.
- **SQLite POC retained** — Plan 2 adds PostgreSQL alongside; no removal of existing SQLite paths until parity tests prove replacement (per Plan 1 exit note).
- **JSON registry → PostgreSQL** — one-time import via script; JSON is not authoritative after apply (documented in `tenant-governance.md`).
- **Audit append-only** — DB trigger raises on UPDATE/DELETE; application uses `AuditRepository.append` only.

### Known limits

- Local integration tests require Docker Desktop running (`docker compose up -d postgres`). CI does not depend on local Docker.
- `001_roles.sql` assumes compose `POSTGRES_USER=vyu_app`; CI bootstrap creates both roles via conftest.
- High-volume tenant admin should move from JSON import to transactional admin APIs (Plan 3+).

### Plan 2 commit series (squashed into PR #2)

Included: schema/RLS/repositories, CI postgres service, integration test fixes (bootstrap, scope, savepoints, import idempotency), and status doc update marking Plan 2 in progress → complete after merge.

---

## Plan 3 — FastAPI application and job platform

**Status:** complete  
**Owner:** avi9s7  
**PR:** https://github.com/avi9s7/Vyu/pull/3  
**Merge SHA:** `76f1c178`  
**Branch:** cursor/fastapi-jobs-plan-3 (merged)  
**Entry gate:** Plan 2 complete (`ff3b90e6` / Alembic `0002`)  
**Plan spec:** `docs/superpowers/plans/2026-07-05-vyu-plan-03-fastapi-jobs.md`  
**Current Alembic head:** `0003`

### 2026-07-05 — Tasks 1–4 (commits `4dc25668` … `57f5563e`)

**Goal:** Dependencies, job/research schema, idempotent job repository, and FastAPI shell with stable error contract.

| Task | Commit message | Key paths |
| --- | --- | --- |
| 1 | `build: add API and queue dependencies` | `pyproject.toml`, `uv.lock`, FastAPI/boto3/PyJWT/uvicorn/httpx |
| 2 | `feat: add durable job and research schema` | `0003_jobs_research.py`, `src/vyu/jobs/models.py`, integration migration tests |
| 3 | `feat: add idempotent job state machine` | `src/vyu/jobs/contracts.py`, `repository.py`, lease/idempotency integration tests |
| 4 | `feat: add FastAPI app and stable error contract` | `src/vyu/api/*`, `apps/api/main.py`, `tests/api/*` |

**Schema `0003` tables:** `jobs`, `idempotency_keys`, `outbox_events`, `research_runs`, `research_run_events` — all with FORCE RLS (tenant-only for idempotency keys; tenant+workspace for the rest).

**Verification (local):**

```powershell
uv run python -m unittest discover -q
uv run pytest tests/api -q
uv run ruff check src/vyu/api src/vyu/jobs
uv run mypy
```

**Decisions:**

- Shared PostgreSQL fixture moved to `tests/integration/conftest.py` for db + jobs integration tests.
- Job repository uses nested savepoints pattern inherited from Plan 2 for idempotency key conflicts.
- `create_app()` verifies Alembic revision at startup; tests override with in-memory SQLite engine + `schema_revision_override="0003"`.
- Stable error envelope on all `/v1` routes; request/trace IDs via middleware.

**Remaining (Tasks 5–9):** research API + OpenAPI, SQS outbox publisher, worker runtime, Docker/compose/CI.

### 2026-07-05 — Task 5: OIDC identity and PostgreSQL membership

**Goal:** Bind verified bearer tokens to database membership; expose FastAPI dependencies and protected debug routes for contract tests.

**Key paths:**

| Area | Paths |
| --- | --- |
| Auth layer | `src/vyu/auth/{tokens,settings,principal,resolver}.py` |
| API wiring | `src/vyu/api/{dependencies,exceptions}.py`, `routers/auth_debug.py`, `app.py` |
| IdP | `src/vyu/deployment/idp.py` — `require_email_verified` on `OidcJwksConfig` |
| Tests | `tests/api/{support,conftest,test_authentication,test_tenant_authorization}.py` |

**Behavior:**

- `TokenVerifier` protocol wraps existing HS256 and OIDC JWKS authenticators; claim validation stays framework-free.
- `PrincipalResolver` upserts external identity, loads active exact-scope membership, uses stored role (ignores claimed admin), sets `app.tenant_id` / `app.workspace_id` before audit append, and records allow/deny identity audit events.
- Protected routes use `get_request_principal`; `/v1/health/live` stays public.
- `VYU_AUTH_MODE=local_hs256` allowed only in local/test; rejected in staging/production.

**Verification:**

```powershell
uv run pytest tests/api/test_authentication.py tests/api/test_tenant_authorization.py tests/api/test_health.py -q
uv run mypy src/vyu/api src/vyu/auth
```

*(PostgreSQL required for auth integration tests — Docker testcontainers locally or CI env vars.)*

### 2026-07-05 — Task 6: Asynchronous research API (commit pending)

**Goal:** Authenticated research search submission with idempotency, scoped reads, cancellation, events, and exported OpenAPI.

**Key paths:**

| Area | Paths |
| --- | --- |
| Schemas | `src/vyu/api/schemas/research.py` |
| Router | `src/vyu/api/routers/research.py` |
| Service | `src/vyu/research/{settings,service}.py` |
| OpenAPI | `scripts/export_openapi.py`, `docs/api/openapi.json` |
| Tests | `tests/api/test_research_routes.py` |

**Routes:**

- `POST /v1/research/searches` — requires `Idempotency-Key`; atomically creates research run, job, outbox event, audit event, and initial run event; returns `202`.
- `GET /v1/research/searches` — cursor-paginated list (tenant/workspace scoped via RLS).
- `GET /v1/research/searches/{search_id}` — detail with links.
- `GET /v1/research/searches/{search_id}/events` — ordered event stream.
- `POST /v1/research/searches/{search_id}/cancel` — sets `cancel_requested`, cancels queued job, appends event (history preserved).

**Verification:**

```powershell
uv run pytest tests/api/test_research_routes.py -q
uv run python scripts/export_openapi.py --output docs/api/openapi.json
```

**Remaining (Tasks 8–9):** Docker/compose/CI evidence for Plan 3 exit gate.

### 2026-07-05 — Task 8: Idempotent SQS worker (commit `29620271`)

**Key paths:** `src/vyu/jobs/worker.py`, `apps/worker/main.py`, `tests/integration/jobs/test_worker.py`

- Long-poll consumer with lease acquisition, handler dispatch, heartbeat, retry backoff, and message ack/nack semantics.
- Duplicate terminal jobs ack without rerunning handlers; signal handlers for graceful stop.

### 2026-07-05 — Task 9: Containers, compose, CI (commit `d965b794`)

**Key paths:** `deploy/docker/{api,worker}.Dockerfile`, `compose.yaml`, `.github/workflows/ci.yml`

### 2026-07-06 — CI fix: API integration test isolation (commit pending)

**CI failure:** Run [28754209285](https://github.com/avi9s7/Vyu/actions/runs/28754209285) — backend PostgreSQL step failed on API tests (`DuplicateRecordError` / FK `fk_memberships_user_id_users`).

**Root cause:** `seed_active_membership` reused the same default subject (`user-test-1`) across session-scoped fixtures while `upsert_user` returned an existing user id that did not match the freshly generated `user_id` passed to `add_membership`.

**Fixes:**

| Path | Change |
| --- | --- |
| `tests/api/support.py` | Use `upsert_user` return id for membership; unique subject per `build_auth_test_client` |
| `tests/api/test_tenant_authorization.py` | Bind inactive-user test to upserted user id |
| `src/vyu/api/dependencies.py` | Handle `AuthorizationError` outside the DB transaction block |

**Verification:**

```powershell
uv run python scripts/verify.py --scope backend
```

**CI:** [run 28770959996](https://github.com/avi9s7/Vyu/actions/runs/28770959996) @ `dd674d2a` — backend, frontend, platform success.

**PR:** [#3](https://github.com/avi9s7/Vyu/pull/3) — CI [run 28771384956](https://github.com/avi9s7/Vyu/actions/runs/28771384956) @ `d7c819f8` success (awaiting merge to `main`).

### 2026-07-06 — CI fixes: API tests + Docker digest (commits `37f14d43`, `871dc6f8`, `dd674d2a`)

- API integration: tenancy seed isolation, JWT `exp` beyond 60s leeway, inactive-user email alignment.
- Platform: corrected truncated `python:3.13-slim-bookworm` digest in `deploy/docker/{api,worker}.Dockerfile`.

**Open PR:** https://github.com/avi9s7/Vyu/compare/main...cursor/fastapi-jobs-plan-3

### 2026-07-06 - Plan 3 merged to `main`

**Owner:** avi9s7  
**PR:** [#3](https://github.com/avi9s7/Vyu/pull/3)  
**Merge SHA:** `76f1c178c46f3995d326aba63aa12d774065291a`  
**CI:** [run 28771967025](https://github.com/avi9s7/Vyu/actions/runs/28771967025) on `main` - conclusion success (backend, frontend, platform).

Plan 3 exit gate satisfied after squash merge to `main`.

### 2026-07-06 — Plan 4 Task 1: Terraform environment structure (commit `d64af85f`)

**Goal:** Establish Terraform module layout, remote-state policy, and structure tests.

**Key paths:** `infra/terraform/{versions.tf,modules/*,environments/{dev,staging,prod}}`, `tests/infra/test_terraform_structure.py`, `infra/terraform/bootstrap/README.md`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev fmt -recursive
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra/test_terraform_structure.py -q
```

### 2026-07-06 — Plan 4 Task 2: Network and KMS foundations (commit `64c6cde4`)

**Goal:** Private VPC across three AZs, VPC endpoints, least-privilege security groups, and customer-managed KMS keys.

**Key paths:** `infra/terraform/modules/{network,kms}/*`, `tests/infra/test_network_policy.py`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra -q
```

### 2026-07-06 — Plan 4 Task 3: RDS, S3, SQS, and Secrets (commit `4533a477`)

**Goal:** Encrypted data plane (RDS PostgreSQL 17, versioned S3 buckets, SQS workloads with DLQs), Secrets Manager containers (no versions in Terraform), and operator secret CLI.

**Key paths:** `infra/terraform/modules/{data,queues}/*`, `scripts/configure_secrets.py`, `tests/infra/test_data_policy.py`, environment wiring in `infra/terraform/environments/*/main.tf`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev fmt -recursive
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra -q
uv run ruff check scripts/configure_secrets.py tests/infra/test_data_policy.py
```

### 2026-07-06 — Plan 4 Task 4: Cognito authorization-code identity (commit `fb6005cc`)

**Goal:** Composed Cognito user pool with authorization-code browser client, confidential machine client, API resource scopes, managed login domain, refresh-token rotation, and enterprise federation inputs.

**Key paths:** `infra/terraform/modules/identity/*`, `deploy/aws/cognito/*` (compatibility wrapper), `tests/infra/test_identity_policy.py`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra/test_identity_policy.py tests/test_aws_cognito_provisioning.py -q
```

### 2026-07-06 — Plan 4 Task 5: ECS application services (commit `1361eaba`)

**Goal:** ECR repositories, isolated ECS Fargate services (web/API/worker), migration task definition, ALB target groups, IAM least-privilege roles, queue-depth autoscaling, and non-root web container.

**Key paths:** `infra/terraform/modules/compute/*`, `deploy/docker/web.Dockerfile`, `tests/infra/test_compute_policy.py`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra -q
```

### 2026-07-06 — Plan 4 Task 6: CloudFront, WAF, TLS, DNS (commit `fd5c4528`)

**Goal:** Route 53 + ACM validation, CloudFront with WAF and security headers, S3 OAC for evidence origin, ALB HTTPS listeners, and API/upload body-size limits at the edge.

**Key paths:** `infra/terraform/modules/edge/*`, `tests/infra/test_edge_policy.py`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra/test_edge_policy.py -q
```

### 2026-07-06 — Plan 4 Task 7: Production telemetry and alarms (commit pending)

**Goal:** SNS alarm routing, CloudWatch dashboards/alarms, ADOT collector config, structured JSON logging with redaction, and OpenTelemetry export hooks.

**Key paths:** `infra/terraform/modules/observability/*`, `src/vyu/observability/*`, `tests/infra/test_observability_policy.py`

**Verification:**

```powershell
terraform -chdir=infra/terraform/environments/dev init -backend=false
terraform -chdir=infra/terraform/environments/dev validate
uv run pytest tests/infra/test_observability_policy.py tests/observability -q
```

---


| Scope | Command | Requires |
| --- | --- | --- |
| `backend` | `uv run python scripts/verify.py --scope backend` | Python 3.13, `uv sync` |
| `frontend` | `uv run python scripts/verify.py --scope frontend` | Node 24, `npm ci` in `apps/web` |
| `integration` | `uv run python scripts/verify.py --scope integration` | PostgreSQL (Docker or CI env vars) |

---

## CI history (production migration)

| Plan | PR | Merge SHA | CI evidence |
| ---: | --- | --- | --- |
| 1 | [#1](https://github.com/avi9s7/Vyu/pull/1) | `1b595b07` | Backend + frontend success on PR #1 |
| 2 | [#2](https://github.com/avi9s7/Vyu/pull/2) | `ff3b90e6` | [Run 28745481470](https://github.com/avi9s7/Vyu/actions/runs/28745481470) — backend unit + PostgreSQL integration + frontend |
| 3 | [#3](https://github.com/avi9s7/Vyu/pull/3) | `76f1c178` | [Run 28771967025](https://github.com/avi9s7/Vyu/actions/runs/28771967025) - backend + frontend + platform on `main` |
