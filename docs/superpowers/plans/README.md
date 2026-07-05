# VYU Production Implementation Plans

These plans convert the approved architecture into ordered engineering work. They are intentionally separate because no junior developer should attempt the entire production migration in one branch or pull request.

Start with:

1. `docs/production/JUNIOR_DEVELOPER_HANDBOOK.md`
2. `docs/superpowers/specs/2026-07-05-vyu-production-platform-design.md`
3. The next eligible plan below

| Order | Plan | Depends on | Primary exit evidence |
| ---: | --- | --- | --- |
| 1 | [Repository baseline](2026-07-05-vyu-plan-01-repository-baseline.md) | Approved design | Clean clone, locks, real tests, CI, reviewed baseline |
| 2 | [PostgreSQL and tenancy](2026-07-05-vyu-plan-02-postgresql-tenancy.md) | Plan 1 | Alembic, RLS isolation, repositories, PostgreSQL CI |
| 3 | [FastAPI and jobs](2026-07-05-vyu-plan-03-fastapi-jobs.md) | Plans 1-2 | OpenAPI, authenticated research API, idempotent SQS worker |
| 4 | [AWS deployment](2026-07-05-vyu-plan-04-aws-deployment.md) | Plans 1-3 | Staging deployment, rollback, rotation, restore |
| 5 | [Evidence ingestion](2026-07-05-vyu-plan-05-evidence-ingestion.md) | Plans 1-4 | Safe upload-to-ready flow with blocked malware/PHI fixtures |
| 6 | [Connectors and retrieval](2026-07-05-vyu-plan-06-connectors-retrieval.md) | Plans 1-5 | Live PubMed, versioned hybrid retrieval, quality gates |
| 7 | [Model gateway and synthesis](2026-07-05-vyu-plan-07-model-synthesis.md) | Plans 1-4 and 6 | Provider adapter, grounded claims/citations, safety evaluation |
| 8 | [Governance, review, exports](2026-07-05-vyu-plan-08-governance-review-exports.md) | Plans 1-4, 6-7 | Review enforcement, PDF/DOCX, immutable governance/audit |
| 9 | [Frontend product](2026-07-05-vyu-plan-09-frontend-product.md) | Stable APIs from Plans 3, 5-8 | Complete authenticated browser journeys with no placeholders |
| 10 | [Operational pilot](2026-07-05-vyu-plan-10-operational-pilot.md) | Plans 1-9 | Security, quality, load, recovery, incident, pilot evidence |

## Dependency Rules

- Plans 1-4 are sequential platform foundations.
- Plan 5 and early Plan 6 tasks may run in parallel only after Plan 4 staging infrastructure is stable and the teams do not edit the same migrations/composition files without coordination.
- Plan 7 requires persisted retrieval contracts from Plan 6.
- Plan 8 requires validated synthesis from Plan 7.
- Plan 9 can build test fixtures earlier, but production integration waits for stable generated API contracts.
- Plan 10 evaluates the integrated immutable release; it cannot certify individual components in isolation.

## Execution Rule

Use one task, one short-lived branch, and one focused pull request at a time. Follow the red-test, implementation, passing-test, regression, documentation, evidence, and review sequence in the handbook.

Do not mark a plan complete because its document exists or its code compiles. Update `docs/production/IMPLEMENTATION_STATUS.md` only after the plan's exit gate has executable evidence bound to the merge SHA and deployed version.

## Scope Rule

All plans enforce the approved initial boundary:

- Public biomedical literature and explicitly approved non-PHI tenant documents.
- Research support only.
- No PHI/ePHI.
- No patient-specific diagnosis, treatment, triage, dosage, or prognosis.
- Human review for policy-defined high-risk results.

A request to support PHI or patient-specific clinical decision support stops this plan sequence and starts a separately approved product, privacy, regulatory, security, and validation program.

