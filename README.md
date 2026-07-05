# Vyu POC

This repository is the implementation workspace for the Vyu proof of concept described in `VYU_POC_README.md`.

For a high-level explanation of what the project does and how to run it, see `docs/project-overview-and-usage.md`.

Implementation progress is tracked in `docs/implementation-roadmap.md`. Update that roadmap at the end of every completed phase before reporting completion.

Production-grade migration status is tracked in `docs/production-grade-migration-plan.md`. Current production foundations include source governance, scoped SQLite storage, audit events, review persistence, reviewer queue service boundaries, reviewer queue API/worker adapters, a framework-neutral reviewer queue route runtime, a framework-neutral report-export route runtime, a framework-neutral service route runtime, production-operated tenant governance, service-account/API-key access, authentication identity mapping, a deployment HTTP adapter with HS256 local bearer-token validation and AWS-friendly OIDC/JWKS enterprise IdP validation, Cognito Terraform provisioning, an API service shell, a serverless deployment handler, a local deployment composition factory, deployment smoke/config/app-entrypoint wiring, deterministic deployment package manifest/plan/archive tooling, local deployment package evidence, release-package checklist, command transcript, transcript bundle, release evidence summary, release review, release handoff evidence, deterministic release handoff archive/inventory evidence, local release-channel preparation, local release-channel acceptance record, a local release-channel publication manifest, a local release-channel evidence index, a local release-channel evidence export summary, a local release-channel target-readiness note, a local release-channel target decision record, a local release-channel provider-planning preflight, a local release-channel provider-planning decision record, connector-health persistence, privacy approval persistence, privacy approval API/worker adapters, readiness-result persistence, durable evidence-memory/retrieval control-plane records, production hybrid retrieval run records, evidence object/index manifests, production evidence-grading methodology records, reviewer-adjustable methodology ratings, external evidence-grading API/webhook connector records, production Trust Score and Governance Box records, reviewer Trust Score override records, external governance API/webhook connector records, durable Research Intelligence MCP plan/tool-call/replay persistence with API/worker execution adapters, safety and report-export decision audit events, report-export API/worker adapters, readiness checks that require approved review state and allowed report-export audit evidence, a local observability snapshot, incident/recovery drill evidence, a local compliance evidence bundle, local approver attestation records, a local pilot release-decision summary, backup/restore, a PHI/ePHI privacy gate, and a Next.js frontend workspace foundation under `apps/web`.

## Phase 0 Status

Phase 0 establishes upstream intake and licence controls before any source reuse.

Created artifacts:

- `upstreams.yaml` defines the reviewed upstream repositories, local clone paths, declared licences, intended usage, and reuse policy.
- `UPSTREAM_LOCK.json` records clone status, pinned commits, licence files, licence hashes, dependency manifests, and copied/adapted file status.
- `UPSTREAM_COMMITS.txt` provides a human-readable commit pin list.
- `docs/phase0/license-inventory.md` summarizes licence and dependency intake.
- `docs/phase0/model-corpus-license-inventory.md` records that no model, embedding, corpus, or external dataset assets are approved or downloaded in Phase 0.
- `docs/phase0/approved-reuse.md` defines what reuse is and is not approved at this phase.
- `docs/phase0/google-pubmedrag-interpretation.md` records the working interpretation of "Google PubMedRAG".

The `upstreams/` directory is intentionally ignored by Git. It contains read-only clones used for review and pinning, not Vyu source code.

## Verify Phase 0

```bash
python -m unittest discover
python scripts/phase0_intake.py --manifest upstreams.yaml --root . --output UPSTREAM_LOCK.json --markdown docs/phase0/license-inventory.md
```

## Phase 1 Status

Phase 1 adds a local synthetic biomedical corpus and Vyu-owned contracts. All records are fictional, use the synthetic VX-101 migraine-prevention topic, and contain no patient records or PHI.

Created artifacts:

- `src/vyu/contracts/` defines document, passage, evidence profile, citation, golden question, and loaded corpus contracts.
- `scripts/generate_phase1_corpus.py` deterministically generates the dummy corpus.
- `src/vyu/ingestion/dummy_corpus.py` loads and validates generated JSONL files.
- `src/vyu/storage/schema.sql` defines the local SQLite schema for Phase 1 entities.
- `data/dummy_articles/` contains synthetic documents, passages, evidence ground truth, and retraction ground truth.
- `data/dummy_pdfs/` contains minimal fictional PDFs for table and figure-caption extraction tests in later phases.
- `data/golden_questions/` contains the 15 required golden questions and expected retrieval/evidence metadata.

## Verify Phase 1

```bash
python scripts/generate_phase1_corpus.py --root .
python -m unittest discover
```

## Phase 2 Status

Phase 2 adds the connector layer. Connectors return Vyu-owned contracts and emit local audit events for search and fetch operations.

Created artifacts:

- `src/vyu/connectors/contracts.py` defines source-neutral connector request, result, and audit contracts.
- `src/vyu/connectors/dummy.py` provides a local connector over the synthetic Phase 1 corpus.
- `src/vyu/connectors/pubmed.py` provides a PubMed connector with injectable transport for mocked E-utilities tests.
- `src/vyu/connectors/audit.py` writes append-only JSONL connector audit events.

The PubMed connector is testable without network access. Live PubMed calls are intentionally deferred until external connector configuration, rate limiting, retries, and policy handling are added.

## Verify Phase 2

```bash
python -m unittest tests.test_phase2_connector_contracts
python -m unittest tests.test_phase2_dummy_connector
python -m unittest tests.test_phase2_pubmed_connector
python -m unittest discover
```

## Phase 3 Status

Phase 3 adds a local retrieval baseline over the synthetic corpus.

Created artifacts:

- `src/vyu/retrieval/contracts.py` defines retrieval queries, metadata filters, scores, hits, and trace records.
- `src/vyu/retrieval/bm25.py` implements BM25 lexical retrieval over passages with document-level aggregation.
- `src/vyu/retrieval/dense.py` implements a deterministic term-vector dense placeholder.
- `src/vyu/retrieval/rrf.py` implements reciprocal-rank fusion.
- `src/vyu/retrieval/evaluation.py` computes Recall@K, MRR@K, and nDCG@K over golden questions.
- `src/vyu/retrieval/production.py` defines production-shaped evidence object records, retrieval index version records, retrieval run records, and a hybrid BM25 + semantic placeholder + RRF runtime boundary.

Real MedCPT/FAISS integration is intentionally deferred. This phase creates the retriever boundary and evaluation harness without downloading models, embeddings, or corpora. The production retrieval boundary is ready to be backed by RDS PostgreSQL metadata, S3 evidence packs, and pgvector/Qdrant indexes when provider credentials are supplied.

## Verify Phase 3

```bash
python -m unittest tests.test_phase3_retrieval_bm25
python -m unittest tests.test_phase3_retrieval_fusion_filters
python -m unittest tests.test_phase3_retrieval_evaluation
python -m unittest discover
```

## Phase 4 Status

Phase 4 adds deterministic grounded answer generation over retrieved evidence.

Created artifacts:

- `src/vyu/generation/contracts.py` defines evidence context, evidence item, answer claim, grounded answer, and citation validation contracts.
- `src/vyu/generation/context.py` builds structured evidence contexts from retrieval hits and assigns stable passage-level citation IDs.
- `src/vyu/generation/answer.py` generates deterministic cited answers, abstains when no non-retracted evidence is available, and validates citation identifiers.

This phase does not call an LLM. The generated answer is a deterministic POC output intended to prove claim/citation structure, citation validation, and abstention behavior.

## Verify Phase 4

```bash
python -m unittest tests.test_phase4_context_builder
python -m unittest tests.test_phase4_grounded_answer
python -m unittest discover
```

## Phase 5 Status

Phase 5 adds deterministic evidence and governance outputs around generated answers.

Created artifacts:

- `src/vyu/evidence/profiles.py` builds Automated Evidence Profiles from the synthetic evidence ground truth.
- `src/vyu/evidence/contradictions.py` detects simple conflicting primary-outcome signals in synthetic evidence.
- `src/vyu/governance/trust.py` calculates an explainable Trust Score with component breakdown.
- `src/vyu/governance/box.py` builds a Governance Box with source, evidence, policy, model, conflict, and human-review metadata.
- `src/vyu/governance/audit.py` exports answer, evidence, score, and governance records as JSON-serializable audit data.
- `src/vyu/governance/production.py` defines production Trust Score policies, durable Trust Score records, durable Governance Box records, deterministic review/export decisions, safety warnings, and reviewer Trust Score override records.
- `src/vyu/governance/external.py` defines a provider-neutral external governance connector with minimized API payloads, idempotency keys, request/response hashes, signed webhook verification, and conversion of external EvideXa-like governance responses back into Vyu records.

This phase remains rule-based and deterministic. It does not perform formal GRADE, Cochrane RoB 2, ROBINS-I, AMSTAR 2, QUADAS-2, or clinical validation. Production Governance Box and Trust Score records are now persisted through `src/vyu/storage/production.py` and included in readiness checks, scoped inspection, observability, compliance evidence, backup/restore, and phase-output artifacts. External governance providers remain optional until endpoint, auth, webhook, and signing-secret configuration is supplied.

## Verify Phase 5

```bash
python -m unittest tests.test_phase5_evidence_profiles
python -m unittest tests.test_phase5_governance
python -m unittest tests.test_production_evidence_grading_methodology
python -m unittest tests.test_production_governance_box_trust_score
python -m unittest discover
```

## Phase 6 Status

Phase 6 adds deterministic guided deep-dive, project-scoped research memory, follow-up decisions, and output templates.

Created artifacts:

- `src/vyu/memory/store.py` stores research memory scoped by tenant, workspace, user, and topic.
- `src/vyu/memory/store.py` also classifies follow-up questions into reuse, new-search, reassess, or new-output decisions.
- `src/vyu/memory/production.py` defines durable production research-memory records with tenant/workspace/user/topic scope, source permissions, access labels, retention policy, retrieved/included/excluded evidence identifiers, model/policy versions, report identifiers, and follow-up decisions.
- `src/vyu/workflow/deep_dive.py` decomposes questions into PICO-like fields, detects simple coverage gaps, and runs a maximum two-round guided retrieval workflow.
- `src/vyu/reports/templates.py` renders evidence brief, research report, and policy output text from answer and governance objects.

This phase remains deterministic and local. In-memory memory remains available for POC workflows, while production control-plane memory is persisted through `src/vyu/storage/production.py` and exported in backups, scoped inspection, readiness, observability, and compliance evidence.

## Verify Phase 6

```bash
python -m unittest tests.test_phase6_memory
python -m unittest tests.test_phase6_deep_dive
python -m unittest tests.test_phase6_outputs
python -m unittest discover
```

## Phase 7 Status

Phase 7 adds a transparent RAG-Gym-style evaluation layer over the deterministic workflows.

Created artifacts:

- `src/vyu/evaluation/trajectories.py` exports guided deep-dive runs as JSON-serializable research trajectories.
- `src/vyu/evaluation/comparison.py` compares fixed one-shot retrieval with guided deep-dive retrieval using deterministic quality, cost, latency, and auditability metrics.
- `src/vyu/evaluation/report.py` renders an adoption report for workflow tradeoff review.
- `tests/test_phase7_trajectories.py` covers trajectory export.
- `tests/test_phase7_comparison_report.py` covers comparison metrics and report rendering.

This phase does not train agents, run SFT/DPO/RL, load reward models, or import RAG-Gym source. It provides a local evaluation boundary for later benchmark-backed adoption decisions.

## Verify Phase 7

```bash
python -m unittest tests.test_phase7_trajectories
python -m unittest tests.test_phase7_comparison_report
python -m unittest discover
```

## Persist Phase 2-7 Outputs

Phase 2-7 workflows can be materialized as local artifacts:

```bash
python scripts/run_phase_outputs.py --root . --output-dir outputs
```

This writes connector, retrieval, production retrieval run, evidence object/index manifest, production research memory, evidence methodology, external evidence-grading request/response, grounded answer, governance, deep-dive, report, trajectory, and workflow-comparison artifacts under `outputs/phase2` through `outputs/phase7`.
