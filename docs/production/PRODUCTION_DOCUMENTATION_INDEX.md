# VYU Production Documentation Index

This index distinguishes documents that are sufficient to start engineering from documents that must be produced and verified during implementation before VYU can be operated in production.

## Documents Available Now

| Document | Purpose |
| --- | --- |
| `docs/production/JUNIOR_DEVELOPER_HANDBOOK.md` | Onboarding, terminology, safety rules, workflow, tools, and definition of done |
| `docs/production/IMPLEMENTATION_STATUS.md` | Plan-level status, exit gates, blockers |
| `docs/production/IMPLEMENTATION_LOG.md` | Running implementation history, decisions, CI fixes, verification commands |
| `docs/production/PLAN4_OPERATOR_HANDOFF.md` | Plan 4 operator resume guide: implemented work, blockers, required inputs, step-by-step AWS/GitHub/DNS setup |
| `docs/superpowers/specs/2026-07-05-vyu-production-platform-design.md` | Audited current status, approved scope, target architecture, API/data/security design, release gates |
| `docs/superpowers/plans/README.md` | Ordered plan index and dependencies |
| `docs/superpowers/plans/2026-07-05-vyu-plan-01-repository-baseline.md` | Git/repository/tooling/locks/tests/CI baseline |
| `docs/superpowers/plans/2026-07-05-vyu-plan-02-postgresql-tenancy.md` | PostgreSQL, Alembic, repositories, RLS, tenant-registry import |
| `docs/superpowers/plans/2026-07-05-vyu-plan-03-fastapi-jobs.md` | FastAPI, OpenAPI, auth, idempotency, outbox, SQS, workers |
| `docs/superpowers/plans/2026-07-05-vyu-plan-04-aws-deployment.md` | AWS Terraform, ECS, RDS, S3, SQS, Cognito, edge, CI/CD, restore |
| `docs/superpowers/plans/2026-07-05-vyu-plan-05-evidence-ingestion.md` | Upload, quarantine, malware/PHI screening, parsing, versioning, chunking |
| `docs/superpowers/plans/2026-07-05-vyu-plan-06-connectors-retrieval.md` | Source policy, PubMed, Research MCP, embeddings, indexes, retrieval evaluation |
| `docs/superpowers/plans/2026-07-05-vyu-plan-07-model-synthesis.md` | Model gateway, provider adapters, prompts, grounded answers, citation validation |
| `docs/superpowers/plans/2026-07-05-vyu-plan-08-governance-review-exports.md` | Methodology, Trust Score, Governance Box, review, PDF/DOCX, audit archive |
| `docs/superpowers/plans/2026-07-05-vyu-plan-09-frontend-product.md` | Next.js upgrade, session/auth, all product pages, accessibility, browser tests |
| `docs/superpowers/plans/2026-07-05-vyu-plan-10-operational-pilot.md` | Security, quality, load, resilience, recovery, support, trust package, pilot |

These documents are sufficient for a junior developer to identify the correct work order, boundaries, files, tests, commands, and exit evidence. They are not evidence that the software has been implemented or deployed.

## Documents and Artifacts Created During Implementation

| Produced by | Required output |
| --- | --- |
| Plan 1 | `IMPLEMENTATION_STATUS.md`, `IMPLEMENTATION_LOG.md`, dependency locks, CI workflow, clean-clone verification |
| Plan 2 | Database schema/ER documentation, migration policy, tenant-governance import/runbook, RLS evidence, `IMPLEMENTATION_LOG.md` entries |
| Plan 3 | Versioned OpenAPI, generated client contract, API error/auth/idempotency/job documentation |
| Plan 4 | Terraform environment README files, deployment/rollback/rotation/restore runbooks, architecture outputs, `PLAN4_OPERATOR_HANDOFF.md` |
| Plan 5 | Ingestion/file-format policy, quarantine/scan/reprocess/deletion runbook, parser fixture inventory |
| Plan 6 | Source approval records, connector replay inventory, index manifest schema, retrieval evaluation reports |
| Plan 7 | Model-provider capability matrix, prompt/model policy registry, model/synthesis evaluation reports |
| Plan 8 | Methodology/governance policy docs, reviewer guide, report specification, audit reconstruction procedure |
| Plan 9 | User/admin UI guide, generated TypeScript client, accessibility report, browser-test report |
| Plan 10 | Updated threat/data-flow model, security reports, SLO/on-call/incident runbooks, DR report, user/reviewer/admin/support guides, customer trust package, immutable release evidence |

## Production Documentation Gate

Production deployment is not authorized until:

1. All “Available Now” documents are reviewed and versioned with the repository.
2. Every implementation-created output exists for the exact deployed release.
3. Commands and screenshots are replaced by durable CI, AWS, test, scan, migration, and recovery evidence where possible.
4. Product, security, privacy, clinical/evidence, operations, and legal/regulatory owners approve the documents within their responsibility.
5. No document claims PHI support, clinical decision authority, certification, or regulatory status that has not been separately approved and proven.

