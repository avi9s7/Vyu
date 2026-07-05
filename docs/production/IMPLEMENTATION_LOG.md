# VYU Implementation Log

Running record of what was built, verified, merged, and learned during the production migration. This complements `IMPLEMENTATION_STATUS.md` (plan-level gates) and the plan specs under `docs/superpowers/plans/`.

Repository: https://github.com/avi9s7/Vyu  
Last log update: 2026-07-05  
Last verified Git SHA: `6002d02f`

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

**Status:** not started  
**Owner:** unassigned  
**Entry gate:** Plan 2 complete (`ff3b90e6` / Alembic `0002`)  
**Plan spec:** `docs/superpowers/plans/2026-07-05-vyu-plan-03-fastapi-jobs.md`

### Planned scope (from spec — not yet implemented)

- FastAPI application shell, `/v1` routes, Pydantic models
- OpenAPI artifact and contract tests
- Authentication wired to existing identity/tenant boundaries
- Job platform: migration `0003`, outbox, SQS worker, idempotency
- Compose services for API/worker; CI image build and smoke path

### Implementation log entries

*(Add dated subsections here as Plan 3 tasks land — one subsection per merged PR or task exit gate.)*

---

## Quick reference — verification scopes

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
