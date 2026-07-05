# VYU Production Build Handbook

**Audience:** A junior developer who can write Python and TypeScript but has not worked on VYU, healthcare evidence systems, AWS production infrastructure, or regulated workflows.  
**Purpose:** Explain exactly how to navigate and execute the production migration plans without treating the current POC as production software.  
**Architecture source of truth:** `docs/superpowers/specs/2026-07-05-vyu-production-platform-design.md`  

---

## 1. What You Are Building

VYU is a governed biomedical research application. A user submits a research question, VYU searches approved evidence sources, retrieves relevant evidence, generates a cited answer, calculates governance information, routes risky results to a human reviewer, and exports only an approved report.

The first production release:

- Uses public biomedical literature and approved non-PHI tenant documents.
- Must not receive or process patient records or PHI/ePHI.
- Must not diagnose, choose treatment, calculate dosage, or make patient-specific recommendations.
- Must preserve the source, document, retrieval, model, prompt, policy, reviewer, and export history for every answer.
- Must fail closed when source approval, authorization, data classification, citation validation, audit persistence, or required human review cannot be proven.

The production workflow is:

```text
login
  -> submit research question
  -> validate intended use and source scope
  -> enqueue research job
  -> search approved sources
  -> normalize evidence
  -> lexical + vector retrieval
  -> evidence assessment
  -> grounded synthesis
  -> citation validation
  -> Trust Score + Governance Box
  -> human review when required
  -> approved report export
```

## 2. What Exists Today

The current repository is a local proof of concept with useful production-shaped modules. It is not a deployable product.

Verified strengths:

- 388 Python tests pass.
- Source registries, source gates, PubMed transport, and Research MCP planning/replay exist.
- Identity mapping, OIDC/JWKS validation, role authorization, and a local tenant registry exist.
- Local retrieval, evidence methodology, Trust Score, Governance Box, review queue, export gate, and audit records exist.
- Next.js builds and lints.
- Production intent, privacy, safety, threat-model, runbook, and release-evidence documents exist.

Verified gaps:

- Git has no baseline history; almost every file is untracked.
- The frontend is mostly placeholder pages and has no tests.
- The dashboard defaults to fixture data.
- The backend has no deployed FastAPI application or complete research API.
- Long-running jobs have no real queue or worker deployment.
- SQLite and local files are still the primary persistence boundary.
- There is no integrated document-ingestion service.
- Dense retrieval and answer generation are deterministic placeholders.
- Model gateway and grounded synthesis exist only in unapplied patch archives.
- Terraform provisions Cognito only, not the full platform.
- There are no production containers, CI/CD pipeline, AWS network, RDS, S3, SQS, WAF, alarms, or restore evidence.
- The current local production-readiness artifact fails against the current schema.

Never describe the current repository as production-ready.

## 3. Documentation Reading Order

Read these documents in order before changing code:

1. `docs/production/JUNIOR_DEVELOPER_HANDBOOK.md` — this file.
2. `docs/superpowers/specs/2026-07-05-vyu-production-platform-design.md` — scope, current status, architecture, API, data model, security, and release gates.
3. `docs/production/intended-use.md` — allowed product use.
4. `docs/production/forbidden-uses.md` — prohibited behavior.
5. `docs/production/privacy-data-flow.md` — current privacy boundary.
6. `docs/production/threat-model.md` — known threats and controls.
7. The implementation plan assigned to you under `docs/superpowers/plans/`.
8. The source and tests named in that plan.

Do not read every historical patch and attempt to merge it. `Additional_scripts_patch_v13` through `v16` are references only.

## 4. Implementation Plan Order

Execute the plans in the following order. Do not begin a dependent plan until the previous plan's exit gate passes.

| Order | Plan | Produces |
| ---: | --- | --- |
| 1 | Repository baseline and engineering system | Trustworthy Git baseline, dependency locks, clean-clone verification, CI |
| 2 | PostgreSQL persistence and tenancy | Alembic schema, repositories, tenant isolation, migration path |
| 3 | FastAPI application and job platform | Versioned API, OpenAPI, auth dependencies, outbox, SQS worker state machine |
| 4 | AWS infrastructure and deployment | Reproducible dev/staging/prod platform and CI/CD |
| 5 | Evidence ingestion | Governed upload, scanning, parsing, chunking, lineage |
| 6 | Governed connectors and retrieval | Live PubMed, approved-source execution, pgvector/full-text retrieval, evaluation |
| 7 | Model gateway and grounded synthesis | Configurable providers, prompts, structured cited answers, safety validation |
| 8 | Governance, review, and exports | End-to-end Governance Box, reviewer UI/API behavior, PDF/DOCX exports |
| 9 | Frontend product completion | Real authentication and complete production workflows |
| 10 | Operational and pilot readiness | Observability, SLOs, performance, recovery, security, runbooks, pilot approval |

Plans 5 and 6 may overlap after Plans 1-4 are stable. Plans 7-9 depend on the API, database, and job foundations. Plan 10 validates the integrated product and cannot be completed in isolation.

## 5. Required Developer Tools

Install these tools before Plan 1. Use versions pinned by the repository once Plan 1 creates version files and lock files.

- Git.
- Python 3.13.
- `uv` for Python environments and dependency locking.
- Node.js active LTS and npm.
- Docker Desktop with Docker Compose v2.
- Terraform 1.x.
- AWS CLI v2.
- PostgreSQL client tools including `psql`.
- An editor with Python, Ruff, mypy/Pylance, ESLint, and TypeScript support.

Verify the tools in PowerShell:

```powershell
git --version
python --version
uv --version
node --version
npm.cmd --version
docker version
docker compose version
terraform version
aws --version
psql --version
```

Expected:

- Every command exits `0`.
- Python reports `3.13.x`.
- Terraform reports a `1.x` release allowed by `infra/terraform/versions.tf` after that file exists.
- Docker reports both client and server; a client-only response means Docker Desktop is not running.

On this Windows workstation, use `npm.cmd`, not the PowerShell `npm.ps1` shim, if execution policy blocks unsigned scripts.

## 6. First-Day Repository Setup

After Plan 1 is merged, use:

```powershell
git clone <approved-vyu-repository-url>
Set-Location PROJECT_VYU
uv sync --all-groups --frozen
npm.cmd ci --prefix apps/web
docker compose up -d postgres localstack
uv run alembic upgrade head
uv run pytest tests/unit -q
npm.cmd test --prefix apps/web
```

Expected:

- Dependency installation uses lock files without changing them.
- PostgreSQL and LocalStack report healthy.
- Alembic reaches the current revision.
- Unit and frontend tests pass.

If any command changes a lock file during a normal setup, stop. The tool version or lock is inconsistent and must be corrected in its own reviewed change.

## 7. Vocabulary

| Term | Meaning in VYU |
| --- | --- |
| Tenant | A customer organization and the highest data-isolation boundary |
| Workspace | A project/team boundary inside a tenant |
| Principal | The authenticated user or service account plus trusted claims |
| Source policy | Approval, permitted uses, license, retention, and access conditions for an evidence source |
| Research run | One versioned execution of a research question and scope |
| Job | Durable asynchronous work record processed by a worker |
| Outbox | Database table used to publish messages without losing the database/message consistency boundary |
| Evidence object | A normalized, versioned document or source result with provenance and checksum |
| Chunk | A citation-addressable segment of one document version |
| Retrieval run | Persisted query, index version, filters, scores, included hits, and excluded hits |
| Claim | One factual statement in an answer that requires evidence support |
| Citation | A link from a claim to an exact evidence chunk |
| Trust Score | Explainable governance score with versioned component inputs |
| Governance Box | User-visible provenance, limitations, warnings, policy, review, and export state |
| Review event | Append-only assignment, comment, approval, rejection, change request, or escalation |
| Idempotency | Repeating a request/message does not repeat the material operation |
| RLS | PostgreSQL row-level security used as defense-in-depth tenant isolation |
| PHI/ePHI | Protected health information; prohibited from the initial release |
| Release evidence | Tests, scans, versions, hashes, approvals, deployment IDs, and recovery proof bound to one release |

## 8. How to Execute a Plan Task

For every task:

1. Confirm the previous plan's exit gate passes.
2. Create one issue or work item containing the task's acceptance criteria.
3. Create a short-lived branch from the protected main branch.
4. Read every file listed under the task's **Files** section.
5. Write the failing test exactly as specified or update it only when the specification requires a justified correction.
6. Run the narrow test and confirm it fails for the expected reason.
7. Implement the smallest production-quality change that satisfies the test.
8. Run the narrow test and confirm it passes.
9. Run the task's broader regression command.
10. Inspect the diff for secrets, generated artifacts, unrelated edits, and unsafe logging.
11. Update documentation, [`IMPLEMENTATION_LOG.md`](IMPLEMENTATION_LOG.md), and the implementation status record named by the plan.
12. Commit only the task's files with the plan's commit message.
13. Open a pull request with test output, security/privacy impact, migration impact, deployment impact, and rollback instructions.
14. Wait for required review and CI. Do not merge your own change without the repository's approved review policy.

Do not batch unrelated plan tasks into one pull request.

## 9. Test-Driven Development Rule

A passing test written after the implementation does not prove that it can detect the missing behavior. The required sequence is:

```text
write test -> run and observe expected failure -> implement -> run and pass -> run regressions
```

An acceptable expected failure is specific, such as:

```text
ModuleNotFoundError: No module named 'src.vyu.db'
```

or:

```text
AssertionError: expected cross-tenant request to return 404, received 200
```

An import error caused by a typo, missing test dependency, or wrong test path is not an acceptable red phase. Fix the test harness and rerun until it fails because the requested behavior is absent.

## 10. Safety Stop Conditions

Stop work and ask a senior engineer when:

- A change could allow PHI or patient-specific use.
- A source's license or permitted use is unclear.
- A model/provider may retain or train on customer data.
- Cross-tenant access is observed or cannot be ruled out.
- A migration could drop, rewrite, or expose customer data.
- Audit-event persistence fails for a material operation.
- A release would bypass required human review.
- A secret appears in Git history, logs, Terraform state, a Docker layer, a frontend bundle, or test output.
- A patch archive conflicts with current source.
- A test passes only when an authorization, security, or governance check is disabled.
- A production incident or restoration procedure is unclear.

Do not invent a workaround for these conditions.

## 11. Configuration Rules

- Local development may use an ignored `.env.local` file generated from an example.
- Staging and production secrets live in AWS Secrets Manager.
- Terraform receives secret ARNs, never plaintext secret values.
- Browser-visible variables start with `NEXT_PUBLIC_` only when their values are safe to expose to every user.
- Model API keys, service credentials, database passwords, signing keys, and webhook secrets are never browser variables.
- Adding a configuration variable requires schema validation, documentation, an example value, tests for missing/invalid values, and startup failure in the environment where it is mandatory.
- Production startup fails when fixture mode, local HS256 authentication, SQLite, local object paths, or placeholder secrets are enabled.

## 12. Database and Migration Rules

- Alembic is the only schema mutation mechanism.
- Application startup does not create or alter tables.
- Every migration has an upgrade path, downgrade decision, data-volume assessment, lock-duration assessment, staging rehearsal, and backup check.
- Prefer additive migrations: add nullable column, deploy compatible code, backfill, enforce constraint, then remove obsolete fields in a later release.
- Every tenant-owned table contains tenant and workspace scope and is covered by RLS tests.
- Never use a user-provided tenant ID without comparing it to the authenticated principal and active membership.
- Never put binary documents in PostgreSQL; store them in S3 and persist checksums and object versions in PostgreSQL.

## 13. API Rules

- All production routes are under `/v1`.
- Pydantic request and response models are strict and reject unknown fields where contract safety requires it.
- Long operations return `202 Accepted` and a durable resource identifier.
- Every material mutation is idempotent.
- Error responses contain stable codes and request/trace IDs but no stack trace or provider secret.
- Tenant-scoped resources return `404` when the resource is outside the caller's scope to avoid confirming its existence.
- OpenAPI changes require regenerated TypeScript types and a compatibility review.
- Removing or changing a public field requires a versioning/deprecation plan.

## 14. Worker Rules

- SQS delivery is at least once; duplicate messages are normal.
- Load authoritative state from PostgreSQL instead of trusting the whole SQS payload.
- Acquire an idempotency lease before an external or charged operation.
- Persist output before acknowledging a message.
- Extend visibility timeout while processing long steps.
- Send poison messages to a DLQ after bounded retries.
- Classify failures as retryable, blocked, or terminal.
- Record attempt count, duration, provider request ID, safe failure code, and audit correlation ID.
- Never retry validation, authorization, policy, citation, or malformed-provider-output failures as transient errors.

## 15. Frontend Rules

- Production pages never import files under `tests/mocks`.
- Cognito tokens are not stored in `localStorage`.
- Every data view has loading, empty, error, forbidden, and stale-state behavior.
- Every form uses shared runtime validation matching the generated API contract.
- Role checks in the UI improve experience but never replace API authorization.
- Evidence citations are keyboard accessible and lead to exact source/chunk details.
- Governance warnings and review state cannot be hidden by presentation preferences.
- Component tests cover behavior; Playwright covers critical user journeys.
- Accessibility checks are part of browser CI.

## 16. Definition of Done for One Pull Request

A pull request is done only when:

- The requested behavior and non-goals are explicit.
- A failing test was observed before implementation.
- Narrow and regression tests pass.
- Static analysis, lint, type checks, and security checks pass.
- No unrelated changes or generated artifacts are included.
- API, schema, configuration, runbook, and architecture docs are updated when affected.
- Migration, deployment, rollback, privacy, security, and observability impacts are documented.
- New logs and metrics are safe and useful.
- Acceptance criteria are demonstrated with command output or deployed evidence.
- Required reviewers approve.

## 17. Status Tracking

Create `docs/production/IMPLEMENTATION_STATUS.md` during Plan 1. Maintain `docs/production/IMPLEMENTATION_LOG.md` as the running history of merged work, decisions, CI fixes, and verification commands.

`IMPLEMENTATION_STATUS.md` must contain one row per plan with:

- Status: `not_started`, `in_progress`, `blocked`, `staging_verified`, or `complete`.
- Owner.
- Issue/PR link.
- Entry-gate evidence.
- Exit-gate evidence.
- Last verified Git SHA.
- Last verified date.
- Known blockers.

`complete` means the plan's exit gate has executable evidence. It does not mean files exist or unit tests pass.

Update `IMPLEMENTATION_LOG.md` in the same pull request whenever behavior, schema, CI, or operational steps change. Use the log's update rule template for each task or merged PR.

## 18. When VYU May Be Called Production

Do not use the word “production” as a synonym for “implemented.” VYU may be called production only after all gates in the architecture specification pass, including:

- Clean-clone reproducibility.
- Isolated AWS deployment.
- End-to-end authenticated research and review workflow.
- Tenant-isolation evidence.
- Retrieval, citation, safety, and governance evaluation.
- Security scans and expert review.
- Monitoring and on-call ownership.
- Backup restoration and rollback exercises.
- Controlled-pilot approval bound to the exact release.
- Enforced non-PHI, non-patient-specific product boundary.

