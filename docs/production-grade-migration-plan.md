# Production-Grade Migration Plan

> This document is an engineering roadmap, not legal, clinical, regulatory, or compliance advice. Before production use in healthcare settings, Vyu needs review by qualified legal, clinical safety, privacy, security, and regulatory experts.

## Goal

Move Vyu from a deterministic local proof of concept into a production-grade governed healthcare research platform that can use live literature sources, scalable retrieval infrastructure, controlled AI/model integrations, auditable evidence governance, privacy controls, human review workflows, and operational monitoring.

The current POC proves the shape of the workflow:

```text
source intake -> corpus -> connector -> retrieval -> grounded answer -> governance -> reports -> evaluation
```

Production migration should preserve that shape, but replace synthetic/local pieces with controlled, validated, monitored, and compliant production systems.

## Reference Frameworks

Use these as planning anchors:

- HHS HIPAA Security Rule summary: https://www.hhs.gov/hipaa/for-professionals/security/laws-regulations/index.html
- NIST Cybersecurity Framework 2.0: https://www.nist.gov/cyberframework
- NIST Secure Software Development Framework: https://csrc.nist.gov/Projects/ssdf
- NIST AI Risk Management Framework: https://www.nist.gov/itl/ai-risk-management-framework
- FDA Clinical Decision Support Software guidance: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software
- FDA Good Machine Learning Practice guiding principles: https://www.fda.gov/medical-devices/software-medical-device-samd/good-machine-learning-practice-medical-device-development-guiding-principles
- OWASP Top 10 for Large Language Model Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/

## Current State to Production Target

| Current limitation | Production target |
| --- | --- |
| Synthetic, small corpus | Live literature connectors, licensed corpus ingestion, scalable document storage, reproducible indexing |
| Deterministic local workflow | Production workflow engine with state, retries, queues, concurrency, auditability, and human review |
| No live PubMed/PMC/model/LLM calls | Connector gateway, model gateway, retrieval indexes, rate limits, key management, vendor governance |
| Simplified evidence grading | Formal evidence profile model, clinical methodology review, GRADE/RoB-style extensions where appropriate |
| PubMed connector tested only with mocked transport | Staged live connector validation, replay tests, contract tests, rate-limit and failure-mode testing |
| No production hardening | Security, privacy, observability, incident response, backup/recovery, deployment automation, compliance evidence |

## Implementation Progress

The following production-foundation items have been implemented in the repository:

| Area | Implemented artifact | Status |
| --- | --- | --- |
| Intended use | `docs/production/intended-use.md` | Draft production policy baseline |
| Source governance | `docs/production/source-registry-schema.md` | Draft schema for approved production sources |
| Security architecture | `docs/production/security-architecture.md` | Draft control baseline |
| Threat model | `docs/production/threat-model.md` | Initial threat model |
| Runtime configuration | `src/vyu/config/runtime.py` | Environment-scoped connector and NCBI settings |
| Connector runtime | `src/vyu/connectors/runtime.py` | Retry, rate-limit, and runtime result wrapper |
| Connector source gate | `src/vyu/connectors/source_gate.py` | Wraps transports with source approval and intended-use enforcement |
| PubMed live foundation | `src/vyu/connectors/pubmed_live.py` | HTTP transport, replay transport, gated live test |
| Connector health foundation | `src/vyu/connectors/health.py` | Health records and staged PubMed replay/live validation records |
| Source registry | `src/vyu/sources/registry.py` | Production source records, JSON persistence, approval gate |
| Research Intelligence MCP contracts | `src/vyu/research_mcp/contracts.py` | Tenant/workspace scope, research tool, search plan, tool-call audit, replay, and execution records |
| Research tool registry | `src/vyu/research_mcp/registry.py` and `config/research_tool_registry.example.json` | Approved-tool registry with source, action, intended-use, and scope enforcement |
| Research MCP planner/runtime | `src/vyu/research_mcp/planner.py` and `src/vyu/research_mcp/runtime.py` | Deterministic query decomposition, approved-tool planning, governed connector execution, request/result hashes, and replay support |
| Research MCP API/worker adapters | `src/vyu/entrypoints/research_mcp.py` | Framework-neutral adapters that authorize, plan, execute, persist, audit, and replay governed research MCP runs |
| Research source connector shells | `src/vyu/connectors/research_sources.py` | Deterministic non-network shells for Semantic Scholar, ClinicalTrials, guideline, and internal-document connector boundaries |
| Authorization foundation | `src/vyu/authz/` | Tenant/workspace role rules for production-shaped access checks |
| Production-operated tenant governance | `src/vyu/authz/tenant_governance.py` | Provider-neutral tenant, workspace, membership grant, service-account, API-key, entitlement, email-domain, expiry, break-glass, admin lifecycle, and audit-backed access checks integrated with deployment composition |
| Privacy foundation | `src/vyu/privacy/` | Data classification, PHI/ePHI fail-closed gate, and approval checks |
| Privacy workflow adapters | `src/vyu/entrypoints/privacy_approval.py` | Framework-neutral API and worker adapters that call the PHI/ePHI gate and persist decisions |
| Model safety foundation | `src/vyu/safety/` | Prompt-injection signals and citation-policy export gate |
| Human review foundation | `src/vyu/review/` | Review tasks, reviewer decisions, and export gate decisions |
| Reviewer queue service | `src/vyu/review/queue.py` | Loads scoped persisted review queues, filters by status, and records authorized reviewer decisions |
| Reviewer queue entry adapters | `src/vyu/entrypoints/review_queue.py` | Framework-neutral API and worker adapters for queue listing and reviewer decisions |
| Reviewer queue route runtime | `src/vyu/entrypoints/review_queue_routes.py` | Framework-neutral HTTP-shaped route runtime for reviewer queue list and decision routes |
| Report export route runtime | `src/vyu/entrypoints/report_export_routes.py` | Framework-neutral HTTP-shaped route runtime for report export requests and local phase-output artifact loading |
| Service route runtime | `src/vyu/entrypoints/service_routes.py` | Framework-neutral top-level route runtime for request IDs, audit correlation, identity headers, health checks, envelopes, and route dispatch |
| Authentication identity mapping | `src/vyu/authn/` | Maps trusted deployed identity claims into Vyu user, tenant, workspace, and role headers without choosing an auth provider or web framework |
| Deployment HTTP adapter | `src/vyu/deployment/http_adapter.py` | Validates HS256 bearer JWTs, preserves request/audit IDs, passes trusted claims into the service runtime, and fails closed before dispatch |
| AWS enterprise IdP validation | `src/vyu/deployment/idp.py` | Validates AWS-friendly OIDC/JWKS RS256 enterprise IdP JWTs for Cognito or federated OIDC deployments before identity mapping and tenant governance |
| API service shell | `src/vyu/deployment/api_service.py` | Converts FastAPI/Flask/serverless request shapes into deployment requests and returns framework-neutral or API Gateway-style responses |
| Serverless handler | `src/vyu/deployment/serverless_handler.py` | Callable API Gateway-style packaging boundary that wraps the API service shell and returns stable JSON errors for malformed events |
| Deployment composition | `src/vyu/deployment/composition.py` | Local factory that composes storage, route runtimes, identity mapping, deployment adapter, API shell, and serverless handler from explicit config |
| Deployment smoke test | `src/vyu/deployment/smoke.py` and `scripts/smoke_test_deployment.py` | Local composed-runtime smoke test for health, authenticated review queue access, and fail-closed bad-token behavior |
| Deployment operator config | `src/vyu/deployment/operator_config.py` and `scripts/validate_deployment_config.py` | Non-secret `.env` template parser and validator for local deployment composition and smoke testing |
| Deployment app entrypoint | `apps/serverless/handler.py` and `src/vyu/deployment/app_entrypoint.py` | Dependency-free serverless-style app entrypoint that consumes `VYU_DEPLOYMENT_ENV_FILE`, builds the local runtime, and fails closed on invalid config |
| Deployment package manifest | `deploy/serverless/package.manifest.json` and `scripts/validate_deployment_package.py` | Local package metadata contract and validator for handler import path, config pointer, include/exclude paths, and validation commands |
| Deployment package planner | `src/vyu/deployment/package_plan.py` and `scripts/plan_deployment_package.py` | Deterministic package inventory planner with file sizes, SHA-256 digests, and manifest exclude enforcement |
| Deployment archive builder | `src/vyu/deployment/package_archive.py` and `scripts/build_deployment_archive.py` | Deterministic zip builder that consumes the package plan and verifies archive entries and hashes against the inventory |
| Deployment package evidence | `src/vyu/deployment/package_evidence.py` and `scripts/write_deployment_package_evidence.py` | Local integrity/provenance evidence for a built deployment archive and inventory |
| Deployment release package checklist | `src/vyu/deployment/release_package.py` and `scripts/check_deployment_release_package.py` | Release checklist that binds archive, inventory, package evidence, and required validation-command coverage |
| Deployment command transcript | `src/vyu/deployment/command_transcript.py` and `scripts/write_deployment_command_transcript.py` | Local command-result transcript records with output excerpts, return codes, artifact hashes, and operator purpose |
| Deployment transcript bundle | `src/vyu/deployment/transcript_bundle.py` and `scripts/check_deployment_transcript_bundle.py` | Transcript bundle checker that verifies required manifest commands have passing transcript evidence in order |
| Deployment release evidence summary | `src/vyu/deployment/release_evidence.py` and `scripts/build_deployment_release_evidence.py` | Summary that cross-checks package evidence, release checklist, and transcript bundle before release review |
| Deployment release review gate | `src/vyu/deployment/release_review.py` and `scripts/review_deployment_release_evidence.py` | Local approve/block decision record bound to release evidence summary hashes |
| Deployment release handoff bundle | `src/vyu/deployment/release_handoff.py` and `scripts/build_deployment_release_handoff.py` | Final local handoff bundle that binds release summary and approved review decision for operator transfer |
| Deployment release handoff archive | `src/vyu/deployment/release_handoff_archive.py` and `scripts/build_deployment_release_handoff_archive.py` | Deterministic local handoff evidence inventory and optional zip archive that verify referenced release artifacts and recorded hashes |
| Deployment release-channel preparation | `src/vyu/deployment/release_channel.py` and `scripts/prepare_deployment_release_channel.py` | Local release-channel provenance manifest that binds handoff inventory, optional handoff archive, package metadata, artifact hashes, and operator next actions |
| Deployment release-channel acceptance | `src/vyu/deployment/release_channel_acceptance.py` and `scripts/accept_deployment_release_channel.py` | Local operator approve/block record bound to the release-channel preparation SHA-256 and package metadata |
| Deployment release-channel publication manifest | `src/vyu/deployment/release_channel_publication.py` and `scripts/prepare_deployment_release_channel_publication.py` | Local no-op publication-readiness manifest that consumes the accepted release-channel record and verifies approve decision, absence of blocking reasons, accepted preparation hashes, package metadata, operator metadata, checklist steps, and local-only limits |
| Deployment release-channel evidence index | `src/vyu/deployment/release_channel_evidence.py` and `scripts/build_deployment_release_channel_evidence.py` | Local release-channel evidence index that consumes the publication manifest and records required hashes for publication, acceptance, preparation, handoff inventory/archive, release evidence summary, review decision, and package evidence |
| Deployment release-channel evidence export summary | `src/vyu/deployment/release_channel_export.py` and `scripts/build_deployment_release_channel_export_summary.py` | Local operator review/export checklist that consumes the evidence index and records evidence-index SHA-256, required evidence counts, evidence hashes, package/operator metadata, publication steps, and local-only limits |
| Deployment release-channel target-readiness note | `src/vyu/deployment/release_channel_target.py` and `scripts/build_deployment_release_channel_target_readiness.py` | Local target-selection readiness note that consumes the export summary and records export-summary SHA-256, evidence-index hash binding, candidate target-family placeholders, no-provider-selection guarantees, and environment handoff checklist items |
| Deployment release-channel target decision record | `src/vyu/deployment/release_channel_target_decision.py` and `scripts/decide_deployment_release_channel_target.py` | Local abstract target-family decision record that consumes target readiness, binds it by SHA-256, records choose/block/defer operator rationale, and preserves no-provider/no-configuration guarantees |
| Deployment release-channel provider-planning preflight | `src/vyu/deployment/release_channel_provider_preflight.py` and `scripts/build_deployment_release_channel_provider_preflight.py` | Local provider-agnostic planning preflight that consumes the target decision, binds it by SHA-256, records abstract planning requirements, and preserves no-provider/no-configuration guarantees |
| Deployment release-channel provider-planning decision record | `src/vyu/deployment/release_channel_provider_decision.py` and `scripts/decide_deployment_release_channel_provider.py` | Local provider-planning decision record that consumes the provider preflight, binds it by SHA-256, records proceed/block/defer operator rationale, and preserves no-provider/no-configuration guarantees |
| Frontend application foundation | `apps/web` and `docs/production/frontend-application-foundation.md` | Next.js App Router workspace scaffold with app shell, dashboard route, typed fixture/API boundary, and route placeholders for governed evidence workflows |
| Reviewer queue operator inspection | `scripts/inspect_review_queue.py` | Authorized CLI inspection of scoped review queues using the same entry adapter as deployed routes |
| Reviewer decision operator command | `scripts/record_review_decision.py` | Authorized CLI approve/reject decisions using the same decision adapter as deployed routes |
| Report export foundation | `src/vyu/reports/export.py` | Composes authorization, review, prompt-injection, and citation-policy gates before rendering reports |
| Report export entry adapters | `src/vyu/entrypoints/report_export.py` | Framework-neutral API and worker adapters that call the report export gate |
| Report export operator command | `scripts/export_report_from_store.py` | Loads persisted phase artifacts and review tasks before calling the report export adapter |
| Safety and report-export decision audit events | `src/vyu/reports/export.py` | Optional production audit events for prompt-injection, citation-policy, and final report-export decisions |
| Review persistence | `src/vyu/storage/production.py` | SQLite review task storage, review decision audit events, and backup/restore support |
| Phase-output review task creation | `scripts/run_phase_outputs.py --sqlite-db ...` | Creates pending scoped review tasks and `review_task_created` audit events when governance requires human review |
| Connector health persistence | `src/vyu/storage/production.py` | SQLite connector health and staged validation records, audit events, readiness checks, and backup/restore support |
| Privacy approval persistence | `src/vyu/storage/production.py` | SQLite PHI/ePHI gate decision records, audit events, scoped inspection, and backup/restore support |
| Readiness result persistence | `src/vyu/storage/production.py` | SQLite production-readiness check result records, audit events, scoped inspection, and backup/restore support |
| Evidence memory and retrieval control plane | `src/vyu/retrieval/production.py`, `src/vyu/memory/production.py`, `src/vyu/storage/production.py` | Production-shaped evidence object records, retrieval index version records, retrieval run records, durable scoped research memory, audit events, backup/restore support, scoped inspection, readiness checks, and observability summaries |
| Evidence grading and methodology control plane | `src/vyu/evidence/methodology.py`, `src/vyu/evidence/external.py`, `src/vyu/storage/production.py` | Versioned methodology rulesets, document-level methodology assessments, run-level evidence grading summaries, reviewer-adjustable ratings, external grading API/webhook request and response records, audit events, backup/restore support, scoped inspection, readiness checks, and observability summaries |
| Governance Box and Trust Score control plane | `src/vyu/governance/production.py`, `src/vyu/governance/external.py`, `src/vyu/storage/production.py` | Production Trust Score records, Governance Box records, reviewer Trust Score overrides, external governance API/webhook request and response records, audit events, backup/restore support, scoped inspection, readiness checks, and observability summaries |
| Manifest source metadata | `scripts/run_phase_outputs.py --source-registry ...` | Requires approved local sources and embeds source records in artifact manifest |
| Artifact traceability | `src/vyu/artifacts/manifest.py` | Run artifact manifest with source/index metadata |
| Run summary | `outputs/run_summary.json` | Compact machine-readable run summary for operators and CI gates |
| Evaluation evidence | `src/vyu/evaluation/registry.py` | JSONL evaluation run registry |
| Relational storage foundation | `src/vyu/storage/production.py` and `--sqlite-db` | SQLite persistence for artifact manifests and evaluation runs |
| Storage schema tracking | `src/vyu/storage/production.py` | Production SQLite schema version metadata and readiness check |
| Migration history | `src/vyu/storage/production.py` | Baseline migration ledger exported in backups and checked by readiness |
| Audit event storage | `src/vyu/storage/production.py` | Append-only production audit events with run/type queries |
| Tenant/workspace scope checks | `src/vyu/storage/production.py` | Scoped manifest and audit reads enforce tenant/workspace isolation |
| Operator inspection | `scripts/inspect_production_store.py` | Scoped JSON export for manifests, evaluation runs, review tasks, review decisions, connector health, staged validation, privacy approvals, readiness results, and audit events |
| Evidence memory/retrieval inspection | `scripts/inspect_production_store.py` | Extends scoped inspection with evidence objects, retrieval indexes, retrieval runs, and production research memory records |
| Governance Box/Trust Score inspection | `scripts/inspect_production_store.py` | Extends scoped inspection with production Trust Score, Governance Box, reviewer override, and external governance request/response records |
| Evidence grading/methodology inspection | `scripts/inspect_production_store.py` | Extends scoped inspection with evidence methodology runs and assessments, reviewer methodology ratings, and external grading request/response records |
| Readiness checks | `scripts/check_production_readiness.py` | Verifies manifest, source, checksum, summary, evaluation, audit, approved review, report-export audit, connector, and scope invariants, then persists scoped readiness results |
| Evidence memory/retrieval readiness checks | `scripts/check_production_readiness.py` | Extends readiness with evidence object, retrieval index, retrieval run, and production research memory invariants |
| Evidence grading/methodology readiness checks | `scripts/check_production_readiness.py` | Extends readiness with methodology assessment, methodology run, reviewer rating, and external grading connector invariants |
| Governance Box/Trust Score readiness checks | `scripts/check_production_readiness.py` | Extends readiness with production Trust Score, Governance Box, and external governance connector invariants |
| Observability snapshot | `scripts/summarize_production_observability.py` | Scoped JSON summary of readiness, review, connector, evidence-memory/retrieval, report-export, and audit-event state |
| Evidence grading/methodology observability | `scripts/summarize_production_observability.py` | Extends observability with evidence methodology and external grading connector state |
| Governance Box/Trust Score observability | `scripts/summarize_production_observability.py` | Extends observability with governance decision, export status, Trust Score, reviewer override, and external governance connector state |
| Incident/recovery drill | `scripts/run_incident_recovery_drill.py` | Local drill evidence for attention-state detection, backup export, restore, scoped inspection, and restored observability |
| Compliance evidence bundle | `scripts/build_compliance_evidence_bundle.py` | Local JSON package for policy, source, readiness, review, export, observability, backup, drill, and scoped-inspection evidence |
| Evidence grading/methodology compliance evidence | `scripts/build_compliance_evidence_bundle.py` | Adds evidence methodology and external grading connector counts to the local compliance bundle |
| Governance Box/Trust Score compliance evidence | `scripts/build_compliance_evidence_bundle.py` | Adds production Trust Score, Governance Box, reviewer override, and external governance connector counts to the local compliance bundle |
| Compliance attestations | `scripts/record_compliance_attestation.py` | Local JSONL approver decisions bound to compliance bundle hashes |
| Pilot release decision | `scripts/build_pilot_release_decision.py` | Local go/no-go JSON summary for bundle readiness and required approver attestations |
| Backup and restore foundation | `scripts/backup_production_store.py` | JSON backup export and restore for production SQLite records |
| Operator runbook | `docs/production/operator-runbook.md` | Repeatable generate, inspect, readiness, test, and failure-triage workflow |
| Forbidden-use policy | `docs/production/forbidden-uses.md` | Standalone export and release blocks for disallowed production use |
| Regulatory position | `docs/production/regulatory-position.md` | Initial pilot positioning and review triggers |
| Product claim inventory | `docs/production/product-claim-inventory.md` | Approved and restricted production claims |
| Regulatory checklist | `docs/production/regulatory-review-checklist.md` | Required review evidence and approvers before pilot changes |

Normal local test and artifact workflows remain offline. Live PubMed validation is opt-in through `VYU_RUN_LIVE_PUBMED_TESTS=1` and requires NCBI runtime settings.


## Workstream 5: Evidence Memory and Retrieval Layer

### Implemented Production Slice

This slice turns the earlier local retrieval and in-memory research-memory POC into a production control-plane boundary that can later be backed by AWS RDS PostgreSQL, S3, and pgvector/Qdrant without changing the Vyu domain contracts.

Implemented capabilities:

- Durable evidence object records for approved documents and evidence packs, including tenant/workspace scope, object URI, source ID, checksum, content type, size, retention policy, and metadata.
- Retrieval index version records for BM25, semantic, hybrid, pgvector, or Qdrant-style indexes, including corpus version, source IDs, object URI, checksum, document count, passage count, embedding model, lexical config, semantic config, and created timestamp.
- Retrieval run records for every production retrieval execution, including tenant/workspace/user/topic scope, query, retrieval mode, index versions, metadata filter, retriever versions, top-k, retrieved document IDs, passage IDs, score trace, latency, and evaluation suite.
- Durable production research memory records scoped by tenant, workspace, user, and topic, with source permissions, access labels, retention policy, retrieved/included/excluded evidence identifiers, report IDs, model/policy versions, citation graph, and follow-up decision.
- A production-shaped hybrid retrieval service that combines BM25 and deterministic semantic placeholder retrieval with RRF while preserving a stable run record contract for future pgvector/Qdrant/MedCPT integration.
- Scoped storage, audit events, backup/restore, operator inspection, readiness checks, observability summaries, compliance evidence counts, and phase-output artifacts for evidence memory and retrieval records.

### Production Substitutions Still Required

The current code intentionally keeps execution local and deterministic. To deploy this layer as a fully managed SaaS capability, replace the local placeholders as follows:

| Placeholder | Production replacement |
| --- | --- |
| SQLite control-plane storage | RDS PostgreSQL schema/migrations |
| `s3://vyu-evidence-placeholder/...` | Real S3 bucket with KMS encryption, lifecycle policy, tenant-prefix isolation, and access logging |
| `s3://vyu-index-placeholder/...` | Real S3 index snapshot location or managed vector-store snapshot reference |
| `pgvector_placeholder` semantic backend | RDS PostgreSQL + pgvector, Qdrant, or another approved vector service |
| Deterministic dense-keyword retriever | Approved biomedical embedding model such as MedCPT or another licensed embedding provider |
| Local audit events | Hash-chained audit ledger and centralized observability pipeline |

No PHI/ePHI is enabled in this slice. The initial pilot posture remains public/synthetic literature only unless privacy, legal, security, and customer approvals are added.

## Production Principles

1. **Human review remains central.** Vyu should support healthcare professionals and researchers, not silently automate clinical decisions.
2. **Every material claim must be traceable.** Answers must link to evidence, retrieval path, source metadata, model configuration, and validation checks.
3. **No unreviewed PHI handling.** Treat PHI/ePHI support as a gated production workstream with privacy, security, legal, and customer controls.
4. **Model behavior must be bounded.** Use retrieval-grounded generation, policy checks, citations, abstention, prompt-injection defenses, and output validation.
5. **Production starts with intended-use control.** Regulatory obligations depend heavily on what the product claims to do and who uses it.
6. **Audit artifacts are product features.** Governance records, provenance, and evaluation results should be first-class outputs, not debug logs.

## Target Architecture

```text
Client/UI
  -> API gateway
  -> application service
  -> workflow orchestrator
      -> connector gateway
      -> retrieval service
      -> model gateway
      -> governance service
      -> human review queue
  -> persistence layer
      -> relational database
      -> object/document storage
      -> vector/lexical indexes
      -> append-only audit/event store
  -> observability and security controls
```

### Core Components

| Component | Responsibility |
| --- | --- |
| API gateway | Authentication, authorization, tenant routing, request limits, request validation |
| Application service | User/workspace/project APIs, saved research sessions, report export |
| Workflow orchestrator | Multi-step research runs, retry policy, state transitions, worker queues |
| Connector gateway | PubMed/PMC/ClinicalTrials/preprint/source connectors behind consistent contracts |
| Retrieval service | BM25, dense retrieval, hybrid retrieval, fusion, reranking, index versioning |
| Model gateway | LLM provider abstraction, prompt templates, model policy, cost controls, safety filters |
| Governance service | Trust score, evidence profiles, human review triggers, policy enforcement |
| Audit/event store | Immutable logs of search, retrieval, generation, governance, review, and export events |
| Human review queue | Clinician/researcher review tasks, decisions, overrides, comments, sign-off |
| Admin console | Connector status, model configuration, policy controls, incidents, metrics |

## Workstream 1: Product Scope, Intended Use, and Regulatory Strategy

### Purpose

Define exactly what Vyu is allowed to do in production before building live healthcare workflows. This controls FDA, HIPAA, clinical safety, and liability assumptions.

### Decisions Required

- Is Vyu a research assistant, clinical decision support tool, payer-policy tool, or internal evidence-review system?
- Is the user a clinician, researcher, policy analyst, patient, or internal reviewer?
- Does Vyu handle patient-specific information?
- Does Vyu recommend diagnosis, prevention, or treatment, or only summarize literature?
- Can the user independently review the basis for every recommendation?

### Plan

1. Write an intended-use statement and forbidden-use policy.
2. Classify each feature as:
   - literature search
   - evidence summarization
   - clinical decision support
   - policy decision support
   - patient-specific recommendation
3. Map features against FDA CDS guidance and identify whether any feature may become device software.
4. Define legal review gates before patient-specific or treatment-recommendation features.
5. Define claims that marketing, UI, API docs, and reports are allowed to make.

### Deliverables

- `docs/production/intended-use.md`
- `docs/production/regulatory-position.md`
- `docs/production/forbidden-uses.md`
- Product claim inventory
- Regulatory review checklist

### Exit Criteria

- Written approval from product, legal/regulatory, clinical safety, and security/privacy owners.
- All production features map to an intended-use category.
- Any clinical or patient-specific feature has a named regulatory review path.

## Workstream 2: Data Governance and Source Licensing

### Purpose

Replace synthetic data with legally approved, provenance-tracked, versioned sources.

### Plan

1. Extend `upstreams.yaml` into a production source registry.
2. Track every source with:
   - source owner
   - license/terms
   - allowed use
   - retention rules
   - attribution requirements
   - update cadence
   - API keys and rate-limit policies
   - PHI/PII status
3. Create ingestion manifests for every corpus/index build.
4. Add source versioning for document snapshots and index snapshots.
5. Add source quarantine for retracted, corrected, duplicated, or suspicious records.

### Production Data Classes

| Data class | Examples | Required controls |
| --- | --- | --- |
| Public literature | PubMed abstracts, PMC metadata | Source terms, attribution, update logs |
| Licensed content | Full-text journals, subscription datasets | License enforcement, access policy, audit |
| Customer documents | Uploaded PDFs, internal evidence reviews | Tenant isolation, retention, deletion |
| Patient data | PHI/ePHI, notes, claims, encounters | HIPAA/privacy review, encryption, minimum necessary access |
| Model artifacts | embeddings, prompts, eval datasets | versioning, access control, provenance |

### Deliverables

- Production source registry
- Data classification policy
- Corpus/index manifest schema
- Retention and deletion policy
- Data provenance report

### Exit Criteria

- Source registry code exists with duplicate-source detection, JSON persistence, and approval checks.
- Connector source gate exists to block live/source-backed transport calls unless the source is approved for the intended use.
- Artifact generation can load a source registry, require approved local sources, and persist source records in `outputs/artifact_manifest.json`.
- No source enters production without license and usage classification.
- Every generated answer can be traced back to source versions and index versions.
- PHI/ePHI is blocked until privacy/security controls are approved.

## Workstream 3: Live Connectors

### Purpose

Turn mocked/local connectors into production services with real API behavior, retries, replay tests, and rate-limit handling.

### Initial Connector Scope

1. PubMed E-utilities.
2. PMC metadata/full-text where permitted.
3. ClinicalTrials.gov.
4. bioRxiv/medRxiv.
5. Customer-uploaded PDFs.

### Plan

1. Keep the current connector contract pattern.
2. Add connector configuration:
   - base URL
   - credentials
   - rate limits
   - retry policy
   - timeout policy
   - circuit breaker thresholds
3. Add live integration tests gated behind environment variables.
4. Add response recording/replay tests to prevent network-dependent unit tests.
5. Add connector health checks and source freshness metrics.
6. Add source-specific normalization into Vyu document/passages/evidence contracts.

### Deliverables

- `src/vyu/connectors/pubmed_live.py`
- `src/vyu/connectors/pmc.py`
- `src/vyu/connectors/clinical_trials.py`
- Connector replay fixtures
- Connector health dashboard
- Connector audit event schema v2

### Exit Criteria

- PubMed HTTP and replay transport foundation exists.
- Live connector tests pass in staging.
- Unit tests remain offline and deterministic.
- Connector audit logs capture search, fetch, retries, errors, and source metadata.
- Rate-limit and outage behavior is tested.

## Workstream 4: Production Storage and Indexing

### Purpose

Replace local JSONL-only storage with production storage that supports search, indexing, versioning, tenancy, and auditability.

### Plan

1. Introduce a relational database for tenants, users, projects, documents, evidence profiles, answers, reviews, and audit metadata.
2. Introduce object storage for raw source payloads, PDFs, extracted text, reports, and exported bundles.
3. Introduce retrieval indexes:
   - BM25/lexical index
   - vector index
   - optional hybrid/reranking layer
4. Make every index build reproducible from a corpus manifest.
5. Add migrations, backup/restore, and disaster recovery tests.
6. Add tenant/workspace scoping to every persisted record.

### Deliverables

- Production database schema
- Object storage layout
- Index manifest schema
- Index build jobs
- Backup and restore runbook
- Data retention jobs

### Exit Criteria

- SQLite production storage adapter exists for artifact manifests and evaluation runs.
- SQLite production storage records a schema version and readiness fails if it is not current.
- SQLite production storage records migration history and readiness fails if the current schema version is missing from that history.
- SQLite production audit event storage exists for artifact/evaluation persistence and phase-output completion events.
- Tenant/workspace scoped storage reads exist for artifact manifests and audit events.
- Operator inspection command exists for scoped production SQLite readback, including review tasks, review decisions, connector health, staged connector validation records, privacy approvals, readiness check results, and audit events.
- Production readiness command exists for local invariant checks after pilot-style review approval and report-export audit evidence.
- Production readiness fails unless a scoped review task is approved and an allowed `report_export_decision_recorded` audit event exists for the run.
- Production observability snapshot command exists for scoped readiness, review, connector, report-export, and audit-event summaries.
- Production incident/recovery drill command exists for attention-state detection, backup export, restore, scoped inspection, and restored observability evidence.
- Production compliance evidence bundle command exists for local pilot-review evidence packaging.
- Production readiness check results are persisted for scoped operator inspection and backup/restore evidence.
- Production SQLite backup export and restore commands exist for local recovery drills.
- Operator runbook exists for repeatable local production-shaped runs and failure triage.
- A complete environment can be rebuilt from manifests and storage backups.
- Queries cannot cross tenant/workspace boundaries.
- Every artifact has source, version, tenant, and retention metadata.

## Workstream 5: Retrieval and Evidence Quality

### Purpose

Move from simple BM25 retrieval over a toy corpus to clinically useful, measurable retrieval over real biomedical sources.

### Plan

1. Keep BM25 as the transparent baseline.
2. Add dense retrieval with biomedical embedding models after license and model-card review.
3. Add reciprocal-rank fusion and optional reranking.
4. Build benchmark sets from:
   - synthetic golden questions
   - curated biomedical QA sets
   - internally reviewed evidence questions
   - clinician-authored challenge questions
5. Track recall, MRR, nDCG, citation precision, retraction exclusion, preprint handling, and latency.
6. Add retrieval failure labels:
   - no evidence found
   - stale index
   - relevant source excluded
   - source quality conflict
   - retracted evidence retrieved
7. Add retrieval explainability output.

### Deliverables

- Retrieval benchmark registry
- Hybrid retrieval service
- Index version comparison reports
- Retrieval quality dashboard
- Retrieval failure taxonomy

### Exit Criteria

- Retrieval quality is measured before and after every index/model change.
- Regression thresholds block deployment.
- Human reviewers can inspect why a source was retrieved.

## Workstream 6: Model and LLM Integration

### Purpose

Introduce LLM-based synthesis without losing determinism, citation grounding, safety, and auditability.

### Plan

1. Add a model gateway rather than direct provider calls from business logic.
2. Version prompts, system instructions, tools, model IDs, temperature, and safety settings.
3. Require structured output schemas for answers, claims, citations, abstentions, and warnings.
4. Validate outputs before persistence:
   - citations exist
   - claims cite supporting passages
   - no unsupported material claims
   - no hidden clinical recommendation when the intended use forbids it
   - no PHI leakage
5. Add prompt-injection and retrieval-poisoning tests.
6. Add model fallback and fail-closed behavior.
7. Preserve deterministic rule-based output as a baseline comparator.

### Safety Requirements

- The model cannot invent citations.
- The model cannot cite retracted evidence without warning.
- The model must abstain when evidence is insufficient.
- The model must disclose uncertainty and conflicts.
- The model must route high-risk outputs to human review.
- The model must not receive PHI unless PHI handling is explicitly approved.

### Deliverables

- Model gateway service
- Prompt registry
- Structured answer schema
- Model evaluation suite
- AI safety test suite
- Model change review process

### Exit Criteria

- Model output passes citation validation and policy validation.
- Prompt/model changes require evaluation evidence.
- Security testing covers prompt injection, sensitive disclosure, overreliance, and excessive agency risks.

## Workstream 7: Evidence Governance and Clinical Methodology

### Purpose

Evolve the simplified Trust Score and Governance Box into a clinically credible evidence-governance layer while preserving clear boundaries between automated evidence profiles, human methodology review, and any external evidence-grading provider.

### Plan

1. Keep current evidence profiles as the base object model.
2. Add formal evidence dimensions:
   - study design
   - sample size
   - population match
   - outcome relevance
   - risk of bias
   - conflict of interest
   - funding source
   - peer-review status
   - retraction/correction status
   - consistency across studies
   - directness/applicability
   - recency
3. Create a methodology review board with clinicians, evidence reviewers, and regulatory advisors.
4. Define which parts are automated and which require human review.
5. Add reviewer sign-off and override reasons.
6. Add governance versioning so scores can be reproduced after policy changes.
7. Preserve a provider-neutral external evidence-grading connector boundary so AIdDea-like services can receive minimized grading inputs through an API and return results through synchronous responses or signed webhooks.

### Deliverables

- Evidence methodology specification
- Versioned methodology ruleset and scoring records
- External evidence-grading API/webhook connector contract
- Reviewer-adjustable evidence-rating records
- Production Trust Score v2 model with reproducible component records
- Production Governance Box v2 schema with audit ID, review/export status, safety warnings, unsupported-claim flags, recency/source-quality summaries, and policy versions
- External governance API/webhook connector boundary for EvideXa-like governance services
- Reviewer Trust Score override records
- Human review queue
- Reviewer decision audit log
- Conflict and uncertainty report

### Exit Criteria

- Every trust score is explainable from component values.
- Human review requirements are deterministic and documented.
- Methodology changes are versioned and regression-tested.
- External grading providers are optional, scoped, auditable, signed, and data-minimized before live use.
- External governance providers are optional, scoped, auditable, signed, and data-minimized before live use.

### Current Implementation Status

Implemented production foundations for this workstream include durable Trust Score records, durable Governance Box records, reviewer Trust Score override records, external governance request/response records, and storage schema version 8. The local governance engine remains deterministic and explainable, while `src/vyu/governance/external.py` provides a provider-neutral API/webhook boundary for an EvideXa-like governance system. Live external use still requires endpoint URL, authentication secret reference, webhook URL, and webhook signing secret configuration.

## Workstream 8: Security, Privacy, and Compliance Controls

### Purpose

Move from local files to production controls aligned with healthcare privacy, secure software development, and incident response expectations.

### Plan

1. Build a security program around NIST CSF functions:
   - Govern
   - Identify
   - Protect
   - Detect
   - Respond
   - Recover
2. Add HIPAA-readiness controls if Vyu handles ePHI or operates as a business associate.
3. Adopt secure development practices aligned with NIST SSDF.
4. Add identity and access management:
   - SSO/SAML/OIDC
   - MFA
   - RBAC/ABAC
   - least privilege
   - break-glass access
5. Add encryption:
   - TLS everywhere
   - encryption at rest
   - field-level encryption for high-risk data
   - managed KMS
6. Add audit logging:
   - user access
   - source access
   - model calls
   - generated outputs
   - exports
   - review decisions
   - admin changes
7. Add vulnerability management:
   - dependency scanning
   - SAST
   - secret scanning
   - container scanning
   - SBOM generation
   - penetration testing
8. Add privacy operations:
   - data inventory
   - minimum necessary access
   - retention/deletion workflows
   - data processing agreements
   - business associate agreement readiness
   - breach response procedures

### Deliverables

- Threat model
- Security architecture document
- Data protection impact assessment
- HIPAA readiness checklist
- Incident response runbook
- Access control matrix
- Audit log retention policy
- SBOM and vulnerability management process

### Exit Criteria

- No production environment exists without IAM, encryption, audit logs, backup, and incident response.
- Security tests run in CI/CD.
- Privacy review approves all data classes handled in production.

## Workstream 9: Human Review and User Experience

### Purpose

Make expert review a built-in workflow, not an afterthought.

### Plan

1. Create review queues for:
   - low confidence
   - conflicting evidence
   - retracted evidence
   - preprints
   - patient-specific context
   - policy-impacting outputs
   - model uncertainty
2. Add reviewer UI for:
   - evidence inspection
   - citation validation
   - source quality review
   - trust score component review
   - comments and sign-off
   - override and escalation
3. Add report export with review state.
4. Add user-facing warnings and scope boundaries.
5. Prevent high-risk report export until required review is complete.

### Deliverables

- Human review data model
- Reviewer queue
- Review UI/API
- Sign-off workflow
- Export gating rules

### Exit Criteria

- High-risk outputs cannot bypass review.
- Reviewer decisions are auditable.
- End users can see evidence, uncertainty, and review status.

## Workstream 10: Validation, Evaluation, and Clinical Safety

### Purpose

Prove quality and safety before production use and keep proving it after release.

### Plan

1. Create an evaluation hierarchy:
   - unit tests
   - contract tests
   - connector replay tests
   - retrieval benchmarks
   - answer faithfulness tests
   - citation correctness tests
   - governance trigger tests
   - red-team tests
   - human expert review studies
2. Define gold-standard datasets with clinician/evidence-reviewer adjudication.
3. Track model and retrieval changes against locked benchmark sets.
4. Add adverse-output taxonomy:
   - unsupported claim
   - wrong citation
   - missing warning
   - unsafe recommendation
   - overconfident summary
   - privacy leak
   - outdated evidence
5. Add release gates with thresholds.
6. Add post-release monitoring and periodic revalidation.

### Deliverables

- Validation plan
- Clinical safety plan
- Evaluation dataset registry
- Release-gate dashboard
- Red-team report
- Post-release monitoring plan

### Exit Criteria

- Production release is blocked unless quality, safety, and security thresholds pass.
- Every production model/index/policy version has an evaluation report.
- Safety incidents have triage, rollback, and correction procedures.

## Workstream 11: Operations and Reliability

### Purpose

Operate Vyu as a reliable service with observability, recovery, and change control.

### Plan

1. Containerize services.
2. Add environment separation:
   - local
   - CI
   - dev
   - staging
   - production
3. Add infrastructure as code.
4. Add CI/CD gates:
   - tests
   - type checks
   - linting
   - security scans
   - migration checks
   - artifact signing
5. Add monitoring:
   - API latency
   - connector errors
   - source freshness
   - retrieval quality
   - model cost
   - model failures
   - review queue age
   - audit log health
6. Add backup/recovery and disaster recovery drills.
7. Add release management:
   - semantic versions
   - changelog
   - rollback
   - feature flags
   - migration plans

### Deliverables

- Deployment architecture
- CI/CD pipeline
- Observability dashboard
- Runbooks
- Backup and restore tests
- On-call and incident process

### Exit Criteria

- Staging mirrors production controls.
- Rollback is tested.
- Recovery time and recovery point objectives are defined and tested.

## Workstream 12: Commercial and Customer Readiness

### Purpose

Prepare the non-code requirements needed for production customers.

### Plan

1. Create customer-facing documentation:
   - intended use
   - limitations
   - evidence methodology
   - data handling
   - security controls
   - audit exports
2. Prepare vendor/security review package:
   - architecture diagram
   - SOC 2 roadmap or report
   - penetration test summary
   - privacy policy
   - data processing agreement
   - BAA readiness if applicable
3. Create support process:
   - incidents
   - evidence disputes
   - citation corrections
   - source update requests
   - model output complaints
4. Define customer onboarding and offboarding.

### Deliverables

- Customer trust package
- Security questionnaire answers
- Admin/user documentation
- Support runbooks
- Onboarding/offboarding process

### Exit Criteria

- Pilot customers can understand allowed use, limitations, data handling, and escalation paths.
- Support can handle safety, privacy, and evidence-quality issues.

## Suggested Migration Timeline

| Stage | Duration | Goal | Exit Gate |
| --- | ---: | --- | --- |
| Stage 0 | 2-4 weeks | Product, intended-use, regulatory, privacy, and architecture decisions | Approved production charter |
| Stage 1 | 4-8 weeks | Production data model, source registry, live connector foundation | Staging connector runs and replay tests |
| Stage 2 | 6-10 weeks | Scalable storage, indexing, retrieval benchmarks | Reproducible index builds and retrieval gates |
| Stage 3 | 6-10 weeks | Model gateway, grounded generation, AI safety tests | Model evaluation report and safety gates |
| Stage 4 | 6-12 weeks | Governance v2 and human review | Review workflow blocks high-risk outputs |
| Stage 5 | 6-12 weeks | Security, privacy, observability, CI/CD, backup/recovery | Staging production-readiness review |
| Stage 6 | 8-16 weeks | Controlled pilot with expert users | Pilot validation and incident-free operating window |
| Stage 7 | ongoing | General availability and post-release monitoring | Continuous quality/security/compliance evidence |

Timelines assume a small focused team and should be adjusted after scope, regulatory classification, and deployment target are finalized.

## Production Readiness Gates

### Gate A: Architecture and Scope

- Intended-use statement approved.
- Production architecture approved.
- Data classes and source licenses approved.
- Regulatory path documented.
- Threat model drafted.

### Gate B: Staging Readiness

- Live connectors work in staging.
- Corpus and index builds are reproducible.
- Authentication and tenant isolation are implemented.
- Audit logs are queryable and retained.
- Offline and live tests are separated.

### Gate C: AI and Evidence Readiness

- Retrieval benchmarks pass thresholds.
- Grounded generation passes citation validation.
- Prompt-injection and overreliance tests are passing.
- Governance v2 triggers human review for high-risk outputs.
- Model/prompt/index versions are fully logged.

### Gate D: Security and Privacy Readiness

- Security review completed.
- Privacy review completed.
- Incident response runbook tested.
- Backup and restore tested.
- Vulnerability scans pass policy.
- PHI/ePHI controls approved if applicable.

### Gate E: Pilot Release

- Expert reviewers trained.
- Customer documentation ready.
- Support and escalation paths ready.
- Pilot scope and success criteria approved.
- Rollback plan tested.

### Gate F: General Availability

- Pilot results reviewed.
- Safety incidents resolved.
- Performance and reliability targets met.
- Compliance evidence package complete.
- Post-release monitoring active.

## Production Metrics

### Quality Metrics

- Recall@K, MRR@K, nDCG@K.
- Citation precision.
- Unsupported claim rate.
- Abstention correctness.
- Retraction warning correctness.
- Conflict disclosure correctness.
- Reviewer agreement rate.

### Safety Metrics

- High-risk output rate.
- Human-review bypass rate.
- Unsafe recommendation rate.
- PHI leakage incidents.
- Prompt-injection success rate.
- Evidence freshness violations.

### Reliability Metrics

- API latency.
- Workflow completion time.
- Connector failure rate.
- Index freshness.
- Model timeout rate.
- Report export success.
- Audit log ingestion lag.

### Operational Metrics

- Cost per research run.
- Review queue age.
- Incident count.
- Mean time to detect.
- Mean time to recover.
- Deployment rollback frequency.

## Staffing Model

| Role | Responsibility |
| --- | --- |
| Product owner | Intended use, scope, customer needs, release gates |
| Backend engineer | APIs, workflow engine, connectors, persistence |
| ML/retrieval engineer | retrieval, embeddings, reranking, model gateway, evaluation |
| Security engineer | threat modeling, IAM, security testing, incident response |
| Privacy/compliance owner | HIPAA/privacy controls, retention, customer agreements |
| Clinical/evidence lead | methodology, human review rules, validation datasets |
| DevOps/SRE | deployment, monitoring, backup/recovery, reliability |
| Regulatory counsel/advisor | FDA/CDS/SaMD positioning and review gates |
| QA/evaluation engineer | test strategy, release gates, regression dashboards |

## First 30 Days

1. Approve intended-use statement and forbidden-use policy.
2. Decide whether PHI/ePHI is in scope for the first production pilot.
3. Select deployment target and tenant model.
4. Create production source registry schema.
5. Add staging configuration structure.
6. Build live PubMed connector behind existing connector contract.
7. Add connector replay fixture tests.
8. Define first production retrieval benchmark set.
9. Draft threat model and privacy data-flow diagram.
10. Define pilot release gates and owner assignments.

## First 90 Days

1. Production database schema and migrations.
2. Object storage and index manifest storage.
3. Live PubMed/PMC/ClinicalTrials connector staging runs.
4. Hybrid retrieval prototype with benchmark dashboard.
5. Model gateway with one approved LLM provider.
6. Structured answer schema and citation validator.
7. Governance Box v2 and human review queue design.
8. Authentication, tenant isolation, and audit log service.
9. CI/CD with unit, integration, security, and migration checks.
10. Staging pilot using public literature only.

## First 180 Days

1. Controlled expert-user pilot.
2. Human review UI and sign-off workflow.
3. Formal evidence methodology review.
4. Red-team testing for prompt injection, unsupported claims, and privacy leakage.
5. Backup/recovery and incident-response drills.
6. Customer trust package.
7. Regulatory position memo reviewed by counsel.
8. Post-release monitoring dashboards.
9. Production readiness review.
10. General availability decision.

## Recommended Next Repository Changes

The first production-foundation increments have been implemented: intended-use, source governance, Research Intelligence MCP planning/audit/replay foundations, security/threat-model docs, runtime connector settings, source approval gates, privacy/PHI gating, privacy workflow API/worker adapters, prompt-injection and citation-policy gates, prompt-injection, citation-policy, and final report-export decision audit events, report export gating, framework-neutral report-export API/worker adapters, a framework-neutral report-export route runtime, a framework-neutral service route runtime, production-operated tenant governance, service-account/API-key access, authentication identity mapping, a deployment HTTP adapter with HS256 local bearer-token validation and AWS-friendly OIDC/JWKS enterprise IdP validation, an API service shell, a serverless deployment handler, a local deployment composition factory, storage-backed report export operator command, framework-neutral reviewer queue API/worker adapters, a framework-neutral reviewer queue route runtime, reviewer queue operator inspection and route-contract docs, reviewer decision operator command, PubMed live/replay transport, artifact manifests, evaluation registry, production-shaped SQLite storage, review persistence, phase-output review task creation, reviewer queue service boundaries, review task inspection, connector health persistence, connector readiness inspection, privacy approval persistence and inspection, readiness-result persistence and inspection, durable evidence-memory/retrieval records, durable Research Intelligence MCP plan/tool-call/replay records, production evidence-grading methodology records, reviewer-adjustable methodology ratings, external evidence-grading API/webhook connector records, production Trust Score and Governance Box records, reviewer Trust Score override records, external governance API/webhook connector records, readiness checks that require approved review state and allowed report-export audit evidence, a local observability snapshot, local incident/recovery drill evidence, a local compliance evidence bundle, local approver attestation records, a local pilot release-decision summary, backup/restore, operator docs, and a Next.js frontend workspace foundation.

The next concrete frontend increment should build the validated `/search/new` workflow against a typed search-job API boundary. The next backend/deployment increment should add the provider-plan draft checklist, then deployed persistence for compliance attestation and release-decision records once the deployment surface is selected.

## Non-Negotiable Before Any Healthcare Production Pilot

- Written intended-use and forbidden-use policy.
- Regulatory review.
- Privacy review.
- Security threat model.
- Tenant isolation.
- Authentication, authorization, and tenant governance.
- Encryption in transit and at rest.
- Audit logs for every material action.
- Human review for high-risk outputs.
- Source provenance and license tracking.
- Validated retrieval and citation quality.
- Incident response and rollback process.
- Clear user-facing limitations.
