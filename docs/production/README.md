# Production Migration Remaining Work

This README summarizes what is still left to do before Vyu can be treated as a production-grade governed healthcare research platform.

The current repository has a strong local production-shaped foundation: source governance, Research Intelligence MCP planning/audit/replay foundations, scoped SQLite storage, audit events, review persistence, reviewer queue adapters, reviewer queue and report-export route runtimes, a top-level service route runtime, production-operated tenant governance, service-account/API-key access, authentication identity mapping, a deployment HTTP adapter with HS256 local bearer-token validation and AWS-friendly OIDC/JWKS enterprise IdP validation, an API service shell, a serverless deployment handler, a local deployment composition factory, deployment smoke/config/app-entrypoint wiring, deterministic deployment package manifest/plan/archive tooling, local deployment package evidence, release-package checklist, command transcript, transcript bundle, release evidence summary, release review gate, release handoff bundle, deterministic release handoff archive/inventory evidence, local release-channel preparation, local release-channel acceptance record, a local release-channel publication manifest, a local release-channel evidence index, a local release-channel evidence export summary, a local release-channel target-readiness note, a local release-channel target decision record, a local release-channel provider-planning preflight, a local release-channel provider-planning decision record, privacy and safety gates, durable evidence-memory/retrieval records, production evidence-grading methodology records, production Trust Score and Governance Box records, external grading/governance connector records, readiness checks, observability, incident/recovery drills, backup/restore, compliance evidence bundles, local approver attestations, and local pilot release-decision evidence.

That foundation is still not a deployed healthcare production system. The remaining work is mostly about replacing local deterministic seams with deployed services, validated production integrations, real operational controls, and expert approvals.

## Current Next Engineering Slice

The current repository increment adds the frontend application foundation under `apps/web`: a Next.js App Router scaffold, reusable shell primitives, a typed fixture-backed dashboard route, API client boundaries, and placeholders for the governed evidence workflow pages.

The next concrete frontend increment should turn `/search/new` into a validated React Hook Form + Zod workflow and add the typed `POST /v1/research/searches` API boundary. The next backend/deployment increment remains a local provider-plan draft checklist, followed by deployed-service selection once the release-channel evidence chain is ready for provider planning.

## Major Work Still Left

### 1. Deployment Surface

- Select the first deployment target and API framework.
- Wire existing route runtimes and deployment HTTP adapter into a real web service.
- Run the checked-in Cognito Terraform stack in a real AWS account, wire its outputs into the deployed service, and add provider-run integration evidence.
- Add framework-level request validation, rate limits, TLS/CORS/CSRF controls, and request-size limits.
- Add deployed worker queue/runtime for long-running workflows.

### 2. Production Persistence

- Move beyond local SQLite into production database and object storage choices.
- Add durable tables or storage objects for compliance attestations and pilot release decisions.
- Add production migrations, migration checks, and rollback procedures.
- Add retention, deletion, export, and tenant-scoped data lifecycle jobs.
- Add immutable or append-only audit storage appropriate for compliance review.

### 3. Live Source and Corpus Integration

- Complete staged live validation for PubMed and add broader source connectors such as PMC, ClinicalTrials.gov, and preprint sources.
- Add connector replay fixtures and contract tests for each source.
- Add source freshness monitoring, source quarantine, duplicate detection, retraction/correction handling, and terms-of-use enforcement.
- Replace synthetic-only corpus flows with approved production corpus and index manifests.

### 4. Retrieval and Indexing

- Introduce production lexical/vector indexes with reproducible build manifests.
- Add benchmark datasets beyond the current synthetic golden questions.
- Track retrieval quality gates such as Recall@K, MRR, nDCG, citation precision, retraction exclusion, and evidence freshness.
- Add retrieval failure taxonomy and reviewer-visible retrieval explanations.

### 5. Model Gateway and LLM Controls

- Add a model gateway instead of direct model-provider calls.
- Version prompts, model IDs, tools, settings, and safety policies.
- Add structured output validation for claims, citations, abstentions, uncertainty, and warnings.
- Add model fallback and fail-closed behavior.
- Run prompt-injection, retrieval-poisoning, unsupported-claim, and privacy-leakage tests.

### 6. Evidence Governance v2

- Move the implemented deterministic methodology, Trust Score, and Governance Box records through clinical/evidence-review validation.
- Replace placeholder external grading/governance endpoints with selected provider integrations and signed webhook infrastructure.
- Add reviewer-facing methodology and Trust Score override UX, escalation states, and sign-off workflows.
- Expand rulesets beyond the synthetic VX-101 corpus into specialty-specific, expert-reviewed evidence rules.

### 7. Human Review UX

- Build reviewer UI for evidence inspection, citation validation, source-quality review, comments, sign-off, overrides, and escalation.
- Add notifications and queue-age monitoring.
- Add user-facing review status, evidence visibility, uncertainty, and scope-boundary messaging.
- Ensure high-risk output export cannot bypass review.
- Replace the current frontend route placeholders with API-backed review, source-inspection, governance, report, and evidence-library workflows.

### 8. Security and Privacy Controls

- Complete provider-run AWS IdP infrastructure evidence for Cognito/federated SAML/OIDC, MFA, least-privilege roles, and break-glass procedures.
- Add encryption in transit and at rest, plus field-level controls for high-risk data if PHI/ePHI enters scope.
- Add production DLP/privacy scanning and formal PHI/ePHI handling approvals.
- Add vulnerability management: dependency scanning, SAST, secret scanning, container scanning, SBOM, and penetration testing.
- Add incident response, breach response, and access-review procedures.

### 9. Operations and Reliability

- Containerize services and define environment separation for local, CI, dev, staging, and production.
- Add infrastructure as code and CI/CD gates.
- Add monitoring for API latency, workflow completion, connector failures, source freshness, retrieval quality, model cost/failures, review queue age, and audit-log health.
- Define RTO/RPO targets and run deployed recovery drills.
- Add release management, rollback, feature flags, and changelog/versioning.

### 10. Validation and Clinical Safety

- Create expert-reviewed validation datasets.
- Add release gates for retrieval quality, answer faithfulness, citation correctness, governance triggers, safety tests, and red-team tests.
- Define adverse-output taxonomy and triage workflow.
- Run controlled pilot validation with expert users before broad availability.
- Add post-release monitoring and periodic revalidation.

### 11. Commercial and Customer Readiness

- Prepare customer-facing documentation for intended use, limitations, evidence methodology, security controls, data handling, and audit exports.
- Prepare vendor/security review evidence, privacy policy, DPA, and BAA readiness if applicable.
- Define support workflows for incidents, evidence disputes, source corrections, model complaints, onboarding, and offboarding.

## Non-Negotiable Before Healthcare Pilot

- Intended-use and forbidden-use policy approved.
- Regulatory review completed.
- Privacy review completed.
- Security threat model reviewed.
- Tenant isolation enforced in deployed services.
- Authentication and authorization deployed.
- Encryption in transit and at rest deployed.
- Audit logs captured for every material action.
- Human review required for high-risk outputs.
- Source provenance and license tracking complete.
- Retrieval and citation quality validated.
- Incident response and rollback tested.
- User-facing limitations documented.

## Useful References

- Full roadmap: `docs/production-grade-migration-plan.md`
- Operator flow: `docs/production/operator-runbook.md`
- Current project usage: `docs/project-overview-and-usage.md`
- Threat model: `docs/production/threat-model.md`
- Research Intelligence MCP layer: `docs/production/research-intelligence-mcp-layer.md`
- Reviewer queue route runtime: `docs/production/reviewer-queue-route-runtime.md`
- Report-export route runtime: `docs/production/report-export-route-runtime.md`
- Service route runtime: `docs/production/service-route-runtime.md`
- Frontend application foundation: `docs/production/frontend-application-foundation.md`
- Tenant governance registry: `docs/production/tenant-governance.md`
- Authentication identity mapping: `docs/production/identity-mapping.md`
- Deployment HTTP adapter: `docs/production/deployment-http-adapter.md`
- API service shell: `docs/production/api-service-shell.md`
- Serverless handler: `docs/production/serverless-handler.md`
- Deployment composition: `docs/production/deployment-composition.md`
- Deployment smoke test: `docs/production/deployment-smoke-test.md`
- Deployment operator config: `docs/production/deployment-operator-config.md`
- AWS enterprise IdP integration: `docs/production/aws-enterprise-idp.md`
- AWS Cognito Terraform stack: `deploy/aws/cognito/README.md`
- Deployment app entrypoint: `docs/production/deployment-app-entrypoint.md`
- Deployment package manifest: `docs/production/deployment-package-manifest.md`
- Deployment package plan: `docs/production/deployment-package-plan.md`
- Deployment package archive: `docs/production/deployment-package-archive.md`
- Deployment package evidence: `docs/production/deployment-package-evidence.md`
- Deployment release package checklist: `docs/production/deployment-release-package-checklist.md`
- Deployment command transcript: `docs/production/deployment-command-transcript.md`
- Deployment transcript bundle: `docs/production/deployment-transcript-bundle.md`
- Deployment release evidence summary: `docs/production/deployment-release-evidence-summary.md`
- Deployment release review gate: `docs/production/deployment-release-review-gate.md`
- Deployment release handoff bundle: `docs/production/deployment-release-handoff-bundle.md`
- Deployment release handoff archive: `docs/production/deployment-release-handoff-archive.md`
- Deployment release-channel preparation: `docs/production/deployment-release-channel-preparation.md`
- Deployment release-channel acceptance: `docs/production/deployment-release-channel-acceptance.md`
- Deployment release-channel publication manifest: `docs/production/deployment-release-channel-publication.md`
- Deployment release-channel evidence index: `docs/production/deployment-release-channel-evidence-index.md`
- Deployment release-channel evidence export summary: `docs/production/deployment-release-channel-export-summary.md`
- Deployment release-channel target-readiness note: `docs/production/deployment-release-channel-target-readiness.md`
- Deployment release-channel target decision record: `docs/production/deployment-release-channel-target-decision.md`
- Deployment release-channel provider-planning preflight: `docs/production/deployment-release-channel-provider-preflight.md`
- Deployment release-channel provider-planning decision record: `docs/production/deployment-release-channel-provider-decision.md`
- Compliance evidence bundle: `docs/production/compliance-evidence-bundle.md`
- Pilot release decision: `docs/production/pilot-release-decision.md`
