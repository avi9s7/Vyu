# Vyu POC Project Overview and Usage

## What This Project Does

This repository is a deterministic proof of concept for Vyu, a governed healthcare research workflow. It demonstrates how a biomedical question can move through controlled source intake, synthetic corpus loading, retrieval, grounded answer generation, evidence governance, guided follow-up research, and workflow evaluation.

The project does not call live LLMs, download external models, or use real patient data. The biomedical records are fictional and use the synthetic VX-101 migraine-prevention topic. The goal is to prove the internal contracts, audit trail, citation structure, and governance workflow before adding production integrations.

## High-Level Flow

```text
Upstream intake and licence review
  -> synthetic biomedical corpus
  -> source connectors
  -> retrieval and evaluation
  -> grounded answer with citations
  -> evidence and governance audit
  -> guided deep-dive and reports
  -> workflow comparison and adoption report
```

## Project Phases

| Phase | Purpose | Main Output |
| --- | --- | --- |
| Phase 0 | Review upstream repositories, licences, and reuse policy | `UPSTREAM_LOCK.json`, `docs/phase0/license-inventory.md` |
| Phase 1 | Generate and load the local synthetic biomedical corpus | `data/dummy_articles/`, `data/golden_questions/`, `data/dummy_pdfs/` |
| Phase 2 | Search and fetch records through source-neutral connectors | `outputs/phase2/` |
| Phase 3 | Run BM25 retrieval and golden-question metrics | `outputs/phase3/` |
| Phase 4 | Build evidence context and grounded answers with citation validation | `outputs/phase4/` |
| Phase 5 | Produce trust score, governance box, and audit record | `outputs/phase5/` |
| Phase 6 | Run guided deep-dive workflow and render reports | `outputs/phase6/` |
| Phase 7 | Export research trajectory and compare workflow quality/cost/auditability | `outputs/phase7/` |

## Important Directories

| Path | Meaning |
| --- | --- |
| `src/vyu/` | Core Python package for contracts, ingestion, connectors, retrieval, generation, governance, memory, reporting, and evaluation |
| `scripts/` | Executable project scripts |
| `apps/web/` | Next.js App Router frontend workspace for the governed evidence UI |
| `tests/` | Unit tests for every implemented phase |
| `data/` | Generated synthetic corpus and golden-question inputs |
| `outputs/` | Persisted Phase 2-7 run artifacts |
| `docs/phase0/` | Licence, provenance, and upstream reuse documentation |
| `docs/superpowers/plans/` | Implementation plans used while building phases |
| `logs/` | Pipeline and test run logs |

## Production-Grade Foundation Implemented So Far

The project now includes the first production-readiness foundations from `docs/production-grade-migration-plan.md`:

- Environment-scoped runtime settings in `src/vyu/config/`.
- Connector retry and rate-limit runtime policy in `src/vyu/connectors/runtime.py`.
- Connector source approval gate in `src/vyu/connectors/source_gate.py`.
- PubMed HTTP and replay transports in `src/vyu/connectors/pubmed_live.py`.
- Connector health checks and staged PubMed validation records in `src/vyu/connectors/health.py`.
- Production source registry records and approval checks in `src/vyu/sources/`.
- Tenant/workspace authorization policy in `src/vyu/authz/`.
- Tenant governance registry in `src/vyu/authz/tenant_governance.py`.
- Privacy data-flow policy and PHI/ePHI gate in `src/vyu/privacy/`.
- Framework-neutral privacy approval API and worker adapters in `src/vyu/entrypoints/privacy_approval.py`.
- Prompt-injection scan and citation-policy gate in `src/vyu/safety/`.
- Human review task and export-gating policy in `src/vyu/review/`.
- Persisted reviewer queue service boundaries in `src/vyu/review/queue.py`.
- Framework-neutral reviewer queue API and worker adapters in `src/vyu/entrypoints/review_queue.py`.
- Framework-neutral reviewer queue route runtime in `src/vyu/entrypoints/review_queue_routes.py`.
- Framework-neutral report-export route runtime in `src/vyu/entrypoints/report_export_routes.py`.
- Framework-neutral service route runtime in `src/vyu/entrypoints/service_routes.py`.
- Authentication identity mapping in `src/vyu/authn/`.
- Deployment HTTP adapter in `src/vyu/deployment/http_adapter.py`.
- API service shell for FastAPI/Flask/serverless conversion in `src/vyu/deployment/api_service.py`.
- Serverless deployment handler boundary in `src/vyu/deployment/serverless_handler.py`.
- Local deployment composition factory in `src/vyu/deployment/composition.py`.
- Deployment smoke-test and operator-config validation in `src/vyu/deployment/smoke.py`, `src/vyu/deployment/operator_config.py`, `scripts/smoke_test_deployment.py`, and `scripts/validate_deployment_config.py`.
- Deployment app entrypoint and packaging metadata in `apps/serverless/handler.py`, `src/vyu/deployment/app_entrypoint.py`, and `deploy/serverless/package.manifest.json`.
- Deterministic deployment package plan/archive/evidence tooling in `src/vyu/deployment/package_plan.py`, `src/vyu/deployment/package_archive.py`, and `src/vyu/deployment/package_evidence.py`.
- Deployment release checklist, transcript bundle, evidence summary, review gate, and handoff bundle tooling in `src/vyu/deployment/release_package.py`, `src/vyu/deployment/command_transcript.py`, `src/vyu/deployment/transcript_bundle.py`, `src/vyu/deployment/release_evidence.py`, `src/vyu/deployment/release_review.py`, and `src/vyu/deployment/release_handoff.py`.
- Deployment release handoff archive/inventory in `src/vyu/deployment/release_handoff_archive.py` and `scripts/build_deployment_release_handoff_archive.py`.
- Deployment release-channel preparation in `src/vyu/deployment/release_channel.py` and `scripts/prepare_deployment_release_channel.py`.
- Deployment release-channel acceptance in `src/vyu/deployment/release_channel_acceptance.py` and `scripts/accept_deployment_release_channel.py`.
- Deployment release-channel publication manifest in `src/vyu/deployment/release_channel_publication.py` and `scripts/prepare_deployment_release_channel_publication.py`.
- Deployment release-channel evidence index in `src/vyu/deployment/release_channel_evidence.py` and `scripts/build_deployment_release_channel_evidence.py`.
- Deployment release-channel evidence export summary in `src/vyu/deployment/release_channel_export.py` and `scripts/build_deployment_release_channel_export_summary.py`.
- Deployment release-channel target-readiness note in `src/vyu/deployment/release_channel_target.py` and `scripts/build_deployment_release_channel_target_readiness.py`.
- Deployment release-channel target decision record in `src/vyu/deployment/release_channel_target_decision.py` and `scripts/decide_deployment_release_channel_target.py`.
- Deployment release-channel provider-planning preflight in `src/vyu/deployment/release_channel_provider_preflight.py` and `scripts/build_deployment_release_channel_provider_preflight.py`.
- Deployment release-channel provider-planning decision record in `src/vyu/deployment/release_channel_provider_decision.py` and `scripts/decide_deployment_release_channel_provider.py`.
- Reviewer queue inspection command in `scripts/inspect_review_queue.py`.
- Reviewer decision recording command in `scripts/record_review_decision.py`.
- Report export gate in `src/vyu/reports/export.py`.
- Framework-neutral report-export API and worker adapters in `src/vyu/entrypoints/report_export.py`.
- Storage-backed report export command in `scripts/export_report_from_store.py`.
- Artifact manifest schema in `src/vyu/artifacts/`.
- Evaluation registry in `src/vyu/evaluation/registry.py`.
- SQLite production storage adapter in `src/vyu/storage/production.py`.
- Production SQLite schema version metadata in `src/vyu/storage/production.py`.
- Production SQLite migration history in `src/vyu/storage/production.py`.
- Queryable production audit events for artifact/evaluation persistence in `src/vyu/storage/production.py`.
- Tenant/workspace scoped storage reads in `src/vyu/storage/production.py`.
- SQLite review task persistence and review decision audit events in `src/vyu/storage/production.py`.
- SQLite connector health and staged validation persistence in `src/vyu/storage/production.py`.
- SQLite privacy approval persistence and audit events in `src/vyu/storage/production.py`.
- SQLite readiness check result persistence and audit events in `src/vyu/storage/production.py`.
- Optional prompt-injection, citation-policy, and report-export decision audit events in `src/vyu/reports/export.py`.
- Production store inspection command with review task, connector readiness, privacy approval, and readiness result readback in `scripts/inspect_production_store.py`.
- Production readiness invariant checks in `scripts/check_production_readiness.py`, including approved review state and allowed report-export audit evidence.
- Production observability snapshot command in `scripts/summarize_production_observability.py`.
- Production incident/recovery drill command in `scripts/run_incident_recovery_drill.py`.
- Production compliance evidence bundle command in `scripts/build_compliance_evidence_bundle.py`.
- Production compliance attestation command in `scripts/record_compliance_attestation.py`.
- Production pilot release-decision command in `scripts/build_pilot_release_decision.py`.
- Production SQLite backup/export and restore command in `scripts/backup_production_store.py`.
- Frontend application scaffold, dashboard route, typed fixture/API boundary, app shell, and route placeholders in `apps/web/`.
- Operator runbook in `docs/production/operator-runbook.md`.
- Standalone forbidden-use, regulatory-position, product-claim, and regulatory-review checklist documents in `docs/production/`.
- Production foundation documents under `docs/production/`.

The live PubMed transport is available for staging/integration use, but normal local tests and artifact runs remain offline and deterministic.

An example approved source registry is available at `config/source_registry.example.json`. Production/live transports can be wrapped with `SourceApprovalTransport` so source access fails closed unless the registry marks the source as approved for the intended use.

The phase-output runner can also load that registry and embed approved source records in `outputs/artifact_manifest.json`.

It can additionally persist the generated artifact manifest and evaluation run to SQLite for local production-shaped storage.
When SQLite persistence is enabled, the runner also records audit events for artifact manifest persistence, evaluation run persistence, and phase-output completion.
When the generated governance box requires human review, SQLite persistence also creates a pending review task and `review_task_created` audit event for the run.
Stored manifests and audit events can be read through tenant/workspace scoped methods to enforce the production isolation model.
Review tasks and reviewer decisions can also be persisted in SQLite, included in scoped inspection output, and included in backup/restore payloads.
Reviewer queue service helpers can load scoped queues, filter by status, and record authorized decisions against persisted review tasks.
API-shaped and worker-shaped reviewer queue adapters call the same queue service without adding a web framework or queue dependency.
The framework-neutral reviewer queue route runtime maps HTTP-shaped list and decision route requests into the same reviewer queue API adapter without choosing a web framework.
The framework-neutral report-export route runtime maps HTTP-shaped export requests into the same report-export API adapter and loads current local Phase 4/5 artifacts through a swappable artifact-store protocol.
The framework-neutral service route runtime adds health checks, request IDs, audit-correlation IDs, identity-header validation, service envelopes, and dispatch to reviewer queue and report-export route runtimes.
The authentication identity mapper converts trusted deployed claims into Vyu user, tenant, workspace, and role headers without choosing an identity provider or web framework. When configured with the production-operated tenant governance, it also verifies active tenant/workspace records and membership grants before emitting service headers.
The deployment HTTP adapter validates HS256 bearer tokens, passes trusted claims into the service runtime, and fails closed before route dispatch.
The API service shell converts FastAPI/Flask/serverless request shapes into deployment requests and returns framework-neutral or API Gateway-style responses without importing a framework.
The serverless deployment handler wraps that shell in a callable API Gateway-style handler and returns stable JSON error envelopes for malformed serverless events.
The local deployment composition factory builds the storage, route runtime, identity mapper, deployment adapter, API shell, and serverless handler graph from explicit local config.
The local reviewer queue inspection command exercises the same list adapter for operator readback before deployed routes exist.
The local reviewer decision command records approve/reject decisions through the same decision adapter and persists `review_decision_recorded` audit events.
Connector health and staged PubMed replay validation records are also persisted in SQLite for scoped inspection, readiness checks, and backup/restore payloads.
Privacy approval records for PHI/ePHI gate decisions can also be persisted in SQLite, included in scoped inspection output, and included in backup/restore payloads.
Production readiness check results can also be persisted in SQLite, included in scoped inspection output, and included in backup/restore payloads. A pilot-ready run must include an approved scoped review task and an allowed `report_export_decision_recorded` audit event.
Report export can optionally persist prompt-injection, citation-policy, and final allow/block export decisions as production audit events when called with a production storage adapter.
API-shaped and worker-shaped privacy approval adapters call the same PHI/ePHI gate and can persist scoped privacy approval records without adding a web framework or queue dependency.
API-shaped and worker-shaped report export adapters call the same export gate without adding a web framework or queue dependency.
The local report export command loads persisted phase artifacts and the persisted review task before calling that same report export adapter.
The local observability snapshot command summarizes readiness, review, connector, report-export, and audit-event state for a scoped run.
The local incident/recovery drill command captures primary attention state, exports a backup, restores it into a fresh SQLite store, validates scoped restored inspection, and summarizes restored observability.
The local compliance evidence bundle command packages policy document hashes, source approval, readiness, review, report-export, observability, backup, drill, and scoped-inspection evidence into one JSON artifact for pilot-review intake.
The local compliance attestation command records approver decisions against compliance bundle hashes in `outputs/compliance_attestations.jsonl`.
The local pilot release-decision command combines compliance bundle readiness with required approver attestations and writes `outputs/pilot_release_decision.json`.
The local deployment release-channel preparation command writes `outputs/deployment_release_channel_preparation.json` and blocks unless the handoff archive inventory is ready, inventory checks passed, artifact hash-match flags remain true, and the optional archive hash matches the inventory. The local release-channel acceptance command writes `outputs/deployment_release_channel_acceptance.json` and blocks unless the preparation manifest is ready, bound by SHA-256, has passing checks, includes required inventory/archive hash evidence, and records operator approval metadata. The local release-channel publication manifest command writes `outputs/deployment_release_channel_publication_manifest.json` and blocks unless the acceptance record is accepted, approval-bound, free of blocking reasons, and still carries the accepted preparation/package/hash metadata. The local release-channel evidence index command writes `outputs/deployment_release_channel_evidence_index.json` and blocks unless the publication manifest is ready and all required release-channel evidence hashes are present. The local release-channel evidence export summary command writes `outputs/deployment_release_channel_export_summary.json` and blocks unless the evidence index is ready, all index checks passed, required evidence counts are complete, package/operator metadata is present, and review checklist items are recorded. The local release-channel target-readiness command writes `outputs/deployment_release_channel_target_readiness.json` and blocks unless the export summary is ready, evidence-index hash binding is intact, required evidence counts are complete, no target provider is selected, and handoff checklist items are recorded. The local release-channel target decision command writes `outputs/deployment_release_channel_target_decision.json` and blocks unless the target-readiness note is ready, all readiness checks passed, the chosen abstract target family is listed, no provider is selected, no provider configuration is recorded, and operator decision metadata is present. The local release-channel provider-planning preflight command writes `outputs/deployment_release_channel_provider_preflight.json` and blocks unless the target decision is selected, decision value is choose, the selected target family is still in the candidate list, no provider is selected, no provider configuration is recorded, and planning requirements are recorded. The local release-channel provider-planning decision command writes `outputs/deployment_release_channel_provider_decision.json` and blocks unless the provider preflight is ready, all preflight checks passed, no provider or provider configuration is recorded, operator metadata is present, and a proceed decision includes only an abstract provider-planning track.

## Inputs

The main local inputs are:

- `upstreams.yaml`: upstream repository manifest for Phase 0 intake.
- `data/dummy_articles/documents.jsonl`: synthetic biomedical documents.
- `data/dummy_articles/passages.jsonl`: passage-level retrieval corpus.
- `data/dummy_articles/evidence_ground_truth.jsonl`: evidence quality and governance labels.
- `data/dummy_articles/retraction_ground_truth.jsonl`: synthetic retraction labels.
- `data/golden_questions/questions.jsonl`: evaluation questions.
- `data/golden_questions/expected_documents.jsonl`: expected retrieval targets.
- `data/golden_questions/expected_citations.jsonl`: expected citation IDs.
- `data/golden_questions/expected_evidence_flags.jsonl`: expected evidence and governance flags.
- `data/dummy_pdfs/`: minimal dummy PDFs for table and figure-caption cases.

Phase 1 regenerates the `data/` inputs deterministically, so they can be recreated from code.

## Outputs

Run outputs are persisted in two groups:

### Intake and Corpus Outputs

- `UPSTREAM_LOCK.json`
- `docs/phase0/license-inventory.md`
- `data/dummy_articles/`
- `data/golden_questions/`
- `data/dummy_pdfs/`

### Phase 2-7 Workflow Outputs

- `outputs/artifact_manifest.json`
- `outputs/run_summary.json`
- `outputs/evaluation/runs.jsonl`
- `outputs/phase2/connector_search_result.json`
- `outputs/phase2/connector_audit.jsonl`
- `outputs/phase3/retrieval_hits.json`
- `outputs/phase3/retrieval_metrics.json`
- `outputs/phase4/evidence_context.json`
- `outputs/phase4/grounded_answer.json`
- `outputs/phase4/citation_validation.json`
- `outputs/phase5/governance_audit_record.json`
- `outputs/phase6/deep_dive_result.json`
- `outputs/phase6/evidence_brief.md`
- `outputs/phase6/research_report.md`
- `outputs/phase6/policy_output.md`
- `outputs/phase7/research_trajectory.json`
- `outputs/phase7/workflow_comparison.json`
- `outputs/phase7/adoption_report.md`

## How To Use It

Run commands from the project root.

### 1. Regenerate Phase 0 Intake Outputs

```bash
python scripts/phase0_intake.py --manifest upstreams.yaml --root . --output UPSTREAM_LOCK.json --markdown docs/phase0/license-inventory.md
```

This reads `upstreams.yaml` and writes licence/provenance outputs.

### 2. Regenerate the Synthetic Corpus

```bash
python scripts/generate_phase1_corpus.py --root .
```

This rewrites the synthetic document, passage, evidence, retraction, PDF, and golden-question files under `data/`.

### 3. Persist Phase 2-7 Workflow Artifacts

```bash
python scripts/run_phase_outputs.py --root . --output-dir outputs
```

This runs a representative local workflow and writes persisted artifacts under `outputs/phase2` through `outputs/phase7`.

To require approved source records and embed them in the artifact manifest:

```bash
python scripts/run_phase_outputs.py --root . --output-dir outputs --source-registry config/source_registry.example.json
```

To also persist production-shaped records to SQLite:

```bash
python scripts/run_phase_outputs.py --root . --output-dir outputs --source-registry config/source_registry.example.json --sqlite-db outputs/production.sqlite
```

### 4. Run the Full Test Suite

```bash
python -m unittest discover
```

The suite verifies all phases and the output persistence script.

### 5. Optional Live PubMed Integration Test

Normal tests do not call PubMed. To run the gated live connector test in a configured staging-like environment:

```bash
set VYU_RUN_LIVE_PUBMED_TESTS=1
set VYU_NCBI_EMAIL=your-team-email@example.com
set VYU_NCBI_TOOL=vyu-poc
python -m unittest tests.test_pubmed_live_connector
```

Optional:

```bash
set VYU_NCBI_API_KEY=your-ncbi-api-key
```

The live transport follows NCBI E-utilities conventions for `retmode=json`, `tool`, `email`, and optional `api_key`.

### 6. Inspect Production SQLite Storage

After generating `outputs/production.sqlite`, inspect a scoped run with:

```bash
python scripts/inspect_production_store.py --sqlite-db outputs/production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command emits JSON containing the artifact manifest, evaluation runs, review tasks with decisions, connector health records, staged connector validation records, privacy approval records, readiness check results, and audit events visible to that tenant/workspace scope.
For the standard local fixture, the generated governance box requires review, so `review_tasks` includes a pending `review-local-phase-output-run` task until an authorized reviewer records a decision.

### 7. Check Production Readiness Invariants

After generating `outputs/artifact_manifest.json` and `outputs/production.sqlite`, run:

```bash
python scripts/check_production_readiness.py --sqlite-db outputs/production.sqlite --artifact-manifest outputs/artifact_manifest.json --run-summary outputs/run_summary.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command emits a JSON readiness report, persists that report in SQLite as a scoped readiness check result, and exits non-zero if any required invariant fails. Current checks cover scoped manifest access, production schema version, migration history, approved source metadata, artifact checksums, evaluation evidence, audit events, approved review state, allowed report-export audit evidence, connector health evidence, staged connector validation evidence, run summary consistency, and wrong-scope rejection.

### 8. Summarize Production Observability

After readiness has run, summarize the scoped run state with:

```bash
python scripts/summarize_production_observability.py --sqlite-db outputs/production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command emits JSON with `status`, `attention_reasons`, readiness status, review status counts, connector health/validation counts, report-export counts, and audit event type counts. It exits non-zero if the tenant/workspace scope is wrong.

### 9. Run an Incident Recovery Drill

After generating a production store, run a local recovery drill with:

```bash
python scripts/run_incident_recovery_drill.py --sqlite-db outputs/production.sqlite --backup outputs/drill_production_backup.json --restored-sqlite-db outputs/drill_restored_production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command emits JSON with primary incident attention state, backup counts, restored counts, restored scoped-inspection evidence, and restored observability. It exits non-zero if the tenant/workspace scope is wrong or restore counts do not match backup counts.

### 10. Build a Compliance Evidence Bundle

After backup and drill evidence exist, build a pilot-review bundle with:

```bash
python scripts/build_compliance_evidence_bundle.py --sqlite-db outputs/production.sqlite --artifact-manifest outputs/artifact_manifest.json --source-registry config/source_registry.example.json --backup outputs/production_backup.json --drill-json outputs/incident_recovery_drill.json --output outputs/compliance_evidence_bundle.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command emits and writes JSON with policy document hashes, source approval evidence, readiness/review/export/observability state, backup counts, incident/recovery drill status, and scoped-inspection counts. It exits non-zero if the tenant/workspace scope is wrong.

### 11. Record a Compliance Attestation

After a bundle is ready for pilot review, record local approver review evidence with:

```bash
python scripts/record_compliance_attestation.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --approver-id privacy-owner --approver-role privacy_owner --decision approve --comment "Privacy evidence reviewed for pilot intake." --attested-at 2026-06-15T00:30:00Z
```

The command appends a JSONL record with the decision, approver role, bundle status, and `bundle_sha256` for the exact bundle reviewed. Re-run the bundle command with `--attestations outputs/compliance_attestations.jsonl` to include an attestation summary in the bundle output.

### 12. Build a Pilot Release Decision

After the required local approvers have attested the bundle, build a go/no-go summary with:

```bash
python scripts/build_pilot_release_decision.py --bundle outputs/compliance_evidence_bundle.json --attestations outputs/compliance_attestations.jsonl --output outputs/pilot_release_decision.json --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace --required-approver-role privacy_owner --required-approver-role security_owner --decided-at 2026-06-15T00:50:00Z
```

The command emits `approved_for_pilot` only when the bundle is ready and every required approver role has a latest `approve` attestation. Missing or changed decisions produce `blocked` with machine-readable reasons such as `required_attestation_missing:security_owner`.

### 13. Export and Restore a Production Backup

After generating `outputs/production.sqlite`, export a JSON backup with:

```bash
python scripts/backup_production_store.py export --sqlite-db outputs/production.sqlite --backup outputs/production_backup.json
```

To verify that the store can be rebuilt, restore it into a fresh SQLite file:

```bash
python scripts/backup_production_store.py restore --backup outputs/production_backup.json --sqlite-db outputs/restored_production.sqlite
```

The backup includes production schema version metadata, migration history, artifact manifests, evaluation runs, review tasks, connector health records, staged connector validation records, privacy approval records, readiness check results, and production audit events. The restored database can be inspected with `scripts/inspect_production_store.py`.

## Typical End-to-End Local Run

```bash
python scripts/phase0_intake.py --manifest upstreams.yaml --root . --output UPSTREAM_LOCK.json --markdown docs/phase0/license-inventory.md
python scripts/generate_phase1_corpus.py --root .
python scripts/run_phase_outputs.py --root . --output-dir outputs
python -m unittest discover
```

After this, inspect:

- `docs/phase0/license-inventory.md` for upstream intake status.
- `data/dummy_articles/` and `data/golden_questions/` for corpus inputs.
- `outputs/phase4/grounded_answer.json` for the generated answer.
- `outputs/phase5/governance_audit_record.json` for trust/governance output.
- `outputs/phase6/research_report.md` for a human-readable report.
- `outputs/phase7/adoption_report.md` for workflow comparison.
- `outputs/production.sqlite` for optional queryable production-shaped storage and audit events, if generated with `--sqlite-db`.
- `outputs/production_backup.json` for optional production store backup evidence, if exported with `scripts/backup_production_store.py`.

## Current Limitations

- The corpus is synthetic and intentionally small.
- The workflow is deterministic and local.
- Live PubMed transport exists, but the default local workflow still does not call PubMed, PMC, models, embeddings, or LLMs.
- Formal clinical evidence grading frameworks are not implemented.
- The PubMed connector has mocked, replay, HTTP transport, gated live-test coverage, and persisted replay-stage validation records; broader production staging validation is still required.
- Later production work would need authentication, DLP-style PHI detection, broader live connector staging validation, scalable storage, model integration, deployed reviewer queue routes/UI, deployed privacy approval routes, frontend/backend API integration beyond fixtures, and clinical/legal validation.

For the detailed migration path from these limitations to a production-grade system, see `docs/production-grade-migration-plan.md`.

## Development Notes

- Keep new behavior behind stable contracts in `src/vyu/`.
- Prefer deterministic outputs for tests and auditability.
- Do not copy upstream source without updating the Phase 0 manifest, lockfile, attribution, and reuse documentation.
- Use `python -m unittest discover` as the project-wide verification command.

## Production Foundation Docs

- `docs/production/intended-use.md`
- `docs/production/access-control-matrix.md`
- `docs/production/connector-health-validation.md`
- `docs/production/compliance-attestations.md`
- `docs/production/compliance-evidence-bundle.md`
- `docs/production/forbidden-uses.md`
- `docs/production/frontend-application-foundation.md`
- `docs/production/human-review-workflow.md`
- `docs/production/incident-recovery-drill.md`
- `docs/production/model-safety-policy.md`
- `docs/production/observability-snapshot.md`
- `docs/production/operator-runbook.md`
- `docs/production/pilot-release-decision.md`
- `docs/production/privacy-data-flow.md`
- `docs/production/product-claim-inventory.md`
- `docs/production/README.md`
- `docs/production/deployment-http-adapter.md`
- `docs/production/api-service-shell.md`
- `docs/production/serverless-handler.md`
- `docs/production/deployment-composition.md`
- `docs/production/tenant-governance.md`
- `docs/production/identity-mapping.md`
- `docs/production/report-export-policy.md`
- `docs/production/report-export-route-runtime.md`
- `docs/production/regulatory-position.md`
- `docs/production/regulatory-review-checklist.md`
- `docs/production/reviewer-queue-api.md`
- `docs/production/reviewer-queue-route-runtime.md`
- `docs/production/service-route-runtime.md`
- `docs/production/source-registry-schema.md`
- `docs/production/security-architecture.md`
- `docs/production/threat-model.md`
