# Vyu POC Implementation Roadmap

> Updated: 2026-06-13  
> Rule: update this roadmap at the end of every completed phase before reporting phase completion.

## Status Summary

| Phase | Status | Current Result |
|---|---|---|
| Phase 0 - Repository and Licence Intake | Complete | Upstreams cloned read-only, commits pinned, licence/dependency inventory captured, reuse policy documented. |
| Phase 1 - Dummy Corpus and Domain Contracts | Complete | Synthetic VX-101 corpus, PDFs, golden questions, Vyu contracts, loader, and SQLite schema implemented. |
| Phase 2 - Connector Layer | Complete | Shared connector contracts, dummy connector, mocked PubMed connector, and JSONL audit logging implemented. |
| Phase 3 - Retrieval Baseline | Complete | BM25, deterministic dense placeholder, RRF, metadata filters, traces, golden-question evaluation, and production retrieval control-plane contracts implemented. |
| Phase 4 - Grounded Answer Generation | Complete | Structured evidence context, deterministic grounded answer schema, claim citations, citation validation, and abstention implemented. |
| Phase 5 - Evidence and Governance | Complete | Automated Evidence Profile rules, production methodology scoring, external grading connector boundary, reviewer-adjustable ratings, contradiction detection, Trust Score, Governance Box, and JSON audit export implemented. |
| Phase 6 - Guided Deep-Dive and Research Memory | Complete | PICO decomposition, two-round guided retrieval, scoped memory, durable production research memory records, follow-up decisions, evidence brief, research report, and policy output templates implemented. |
| Phase 7 - RAG-Gym-Style Evaluation | Complete | Trajectory export, fixed-vs-guided comparison, and adoption report implemented. |

## Phase 0 - Repository and Licence Intake

Status: Complete

Implemented:

- Initialized the Vyu POC workspace as a Git repository.
- Added `upstreams.yaml` with upstream URLs, local paths, declared licences, intended usage, and reuse policies.
- Cloned upstream repositories into ignored `upstreams/` as read-only review material.
- Generated `UPSTREAM_LOCK.json` with pinned commit SHAs, licence-file hashes, dependency manifest paths, and copied/adapted file status.
- Added `UPSTREAM_COMMITS.txt` with human-readable commit pins.
- Added Phase 0 documentation:
  - `docs/phase0/license-inventory.md`
  - `docs/phase0/model-corpus-license-inventory.md`
  - `docs/phase0/approved-reuse.md`
  - `docs/phase0/google-pubmedrag-interpretation.md`
- Added `scripts/phase0_intake.py` for repeatable inventory generation.
- Added tests in `tests/test_phase0_intake.py`.

Verification:

```text
python -m unittest discover
```

Current notes:

- No upstream source has been copied into Vyu.
- Google BioCompass and Google PubMed MCP are recorded as Apache-2.0.
- Zaoqu-Liu/PubMedRAG remains GPL-3.0 and reference-only.
- RAG-Gym and HamsiniGupta/PubMedRAG remain unverified and reference-only.

## Phase 1 - Dummy Corpus and Domain Contracts

Status: Complete

Implemented:

- Added Vyu-owned contract dataclasses in `src/vyu/contracts/`.
- Added deterministic synthetic corpus generator in `scripts/generate_phase1_corpus.py`.
- Generated the local fictional VX-101 corpus under `data/`.
- Added 30 synthetic biomedical documents and 60 passages.
- Added 15 golden questions and expected retrieval/evidence metadata.
- Added two minimal synthetic PDFs for later PDF/table/figure-caption pipeline tests.
- Added `src/vyu/ingestion/dummy_corpus.py` to load and validate corpus links.
- Added `src/vyu/storage/schema.sql` and schema loader for Phase 1 relational tables.
- Added tests:
  - `tests/test_phase1_contracts.py`
  - `tests/test_phase1_corpus_generation.py`
  - `tests/test_phase1_loader.py`
  - `tests/test_phase1_schema.py`

Verification:

```text
python scripts/generate_phase1_corpus.py --root .
python -m unittest discover
```

Current corpus inspection:

```text
30 documents
60 passages
15 golden questions
2 retracted documents
```

## Phase 2 - Connector Layer

Status: Complete

Implemented:

- Added shared connector contracts in `src/vyu/connectors/contracts.py`.
- Added append-only JSONL audit sink in `src/vyu/connectors/audit.py`.
- Added `DummyConnector` over the loaded Phase 1 corpus in `src/vyu/connectors/dummy.py`.
- Added `PubMedConnector` in `src/vyu/connectors/pubmed.py`.
- Made PubMed transport injectable so tests stay offline and deterministic.
- Added audit events for connector search and fetch operations.
- Added tests:
  - `tests/test_phase2_connector_contracts.py`
  - `tests/test_phase2_dummy_connector.py`
  - `tests/test_phase2_pubmed_connector.py`

Verification:

```text
python -m unittest discover
```

Current notes:

- The PubMed connector maps mocked E-utilities-style search and summary responses into Vyu `DocumentRecord` and `PassageRecord` contracts.
- Live PubMed behavior is intentionally deferred until retry, timeout, rate-limit, and policy handling are added.

## Phase 3 - Retrieval Baseline

Status: Complete

Implemented:

- Added retrieval contracts in `src/vyu/retrieval/contracts.py`.
- Added BM25 lexical retrieval in `src/vyu/retrieval/bm25.py`.
- Added deterministic term-vector dense placeholder in `src/vyu/retrieval/dense.py`.
- Added metadata filtering through `MetadataFilter`.
- Added reciprocal-rank fusion in `src/vyu/retrieval/rrf.py`.
- Added retrieval traces with original rank, post-filter rank, and final rank.
- Added golden-question evaluation in `src/vyu/retrieval/evaluation.py`.
- Added production retrieval control-plane contracts in `src/vyu/retrieval/production.py` for evidence object records, retrieval index versions, retrieval run score traces, and a hybrid BM25 + semantic placeholder + RRF runtime boundary.
- Added tests:
  - `tests/test_phase3_retrieval_bm25.py`
  - `tests/test_phase3_retrieval_fusion_filters.py`
  - `tests/test_phase3_retrieval_evaluation.py`

Verification:

```text
python -m unittest discover
```

Current limitations:

- Real MedCPT model loading is not implemented.
- FAISS indexing is not implemented.
- Dense retrieval is a deterministic standard-library placeholder so the POC remains dependency-free.
- Approved retrieval thresholds are not treated as production claims until Phase 3 is run against the finalized evaluation matrix.

Exit condition:

The local retriever boundary, metadata filters, fusion logic, traces, and golden-question metric harness are implemented and test-covered.

## Phase 4 - Grounded Answer Generation

Status: Complete

Implemented:

- Added generation contracts in `src/vyu/generation/contracts.py`.
- Added structured evidence context builder in `src/vyu/generation/context.py`.
- Added stable passage-level citation IDs such as `CIT-001`.
- Added deterministic grounded answer generation in `src/vyu/generation/answer.py`.
- Added `AnswerClaim` records with claim-level citation IDs.
- Added citation identifier validation against the evidence context.
- Added abstention when no non-retracted evidence is available.
- Added tests:
  - `tests/test_phase4_context_builder.py`
  - `tests/test_phase4_grounded_answer.py`

Verification:

```text
python -m unittest discover
```

Current limitations:

- No LLM or provider gateway is called.
- Claim extraction is deterministic and contract-focused rather than model-generated.
- Citation validation checks identifier validity and material-claim citation coverage; semantic entailment remains for a later phase.

Exit condition:

Grounded answer objects can be generated from retrieved evidence with stable passage citations, citation validation, and abstention behavior.

## Phase 5 - Evidence and Governance

Status: Complete

Implemented:

- Added Automated Evidence Profile builder in `src/vyu/evidence/profiles.py`.
- Added bias, applicability, retraction, preprint, low-confidence, and human-review warnings.
- Added contradiction detection in `src/vyu/evidence/contradictions.py`.
- Added production methodology scoring in `src/vyu/evidence/methodology.py` for study design, source reliability, recency, population/context match, risk-of-bias signals, limitations, contradictions, specialty/versioned rulesets, and reviewer-adjustable ratings.
- Added provider-neutral external evidence grading integration in `src/vyu/evidence/external.py` for API submission, idempotency, request/response hashes, webhook callbacks, and signature verification.
- Added persistence, audit, backup/restore, readiness, observability, inspection, and compliance evidence support for methodology runs, document-level methodology assessments, reviewer ratings, and external grading request/response records.
- Added explainable Trust Score in `src/vyu/governance/trust.py`.
- Added Governance Box in `src/vyu/governance/box.py`.
- Added JSON audit export in `src/vyu/governance/audit.py`.
- Added tests:
  - `tests/test_phase5_evidence_profiles.py`
  - `tests/test_phase5_governance.py`
  - `tests/test_production_evidence_grading_methodology.py`

Verification:

```text
python -m unittest discover
```

Current limitations:

- Local evidence profiling and methodology scoring are deterministic and based on synthetic corpus metadata.
- External evidence grading is represented by a provider-neutral API/webhook boundary and replay transport; real AIdDea-like endpoint URLs, credentials, and legal/vendor controls must be supplied before live use.
- Contradiction detection uses explicit synthetic wording rather than natural-language inference.
- Trust Score is a POC heuristic, not a clinically validated score.
- Formal GRADE, Cochrane RoB 2, ROBINS-I, AMSTAR 2, QUADAS-2, and clinical validation remain out of scope unless separately reviewed and approved.

Exit condition:

Generated answers can be accompanied by evidence profile signals, production methodology assessment records, external grading request/response trace placeholders, reviewer-adjustable ratings, conflict warnings, Trust Score, Governance Box metadata, and a JSON-serializable audit record.

## Phase 6 - Guided Deep-Dive and Research Memory

Status: Complete

Implemented:

- Added scoped research memory in `src/vyu/memory/store.py`.
- Added tenant/workspace/user/topic isolation for memory lookup.
- Added follow-up decision classification:
  - `REUSE_EXISTING_EVIDENCE`
  - `SEARCH_NEW_EVIDENCE`
  - `REASSESS_EXISTING_EVIDENCE`
  - `GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE`
- Added PICO-like decomposition in `src/vyu/workflow/deep_dive.py`.
- Added simple coverage-gap detection.
- Added maximum two-round guided retrieval workflow.
- Added evidence brief, research report, and policy output templates in `src/vyu/reports/templates.py`.
- Added tests:
  - `tests/test_phase6_memory.py`
  - `tests/test_phase6_deep_dive.py`
  - `tests/test_phase6_outputs.py`

Verification:

```text
python -m unittest discover
```

Current limitations:

- Research memory is in-memory only.
- PICO decomposition is deterministic keyword logic.
- Coverage-gap detection is rule-based.
- Guided deep-dive is a transparent fixed workflow, not an agentic planner.

Exit condition:

Follow-up questions can be classified and scoped memory can be reused without crossing tenant, workspace, user, or topic boundaries. A two-round guided retrieval flow and deterministic output templates are available.

### Production memory/retrieval hardening update

- Added `src/vyu/memory/production.py` for durable scoped research-memory records.
- Added production storage, audit, backup/restore, readiness, observability, and inspection support for evidence objects, retrieval indexes, retrieval runs, and research memory.

## Phase 7 - RAG-Gym-Style Evaluation

Status: Complete

Implemented:

- Added evaluation exports in `src/vyu/evaluation/__init__.py`.
- Added JSON-serializable trajectory contracts in `src/vyu/evaluation/trajectories.py`.
- Added guided deep-dive trajectory export with per-round query, retrieved document IDs, coverage gap, and observation records.
- Added deterministic fixed one-shot versus guided deep-dive workflow comparison in `src/vyu/evaluation/comparison.py`.
- Added quality, estimated cost units, estimated latency units, auditability, and trajectory-count metrics.
- Added adoption report rendering in `src/vyu/evaluation/report.py`.
- Added tests:
  - `tests/test_phase7_trajectories.py`
  - `tests/test_phase7_comparison_report.py`

Verification:

```text
python -m unittest tests.test_phase7_trajectories
python -m unittest tests.test_phase7_comparison_report
python -m unittest discover
```

Current limitations:

- This is a RAG-Gym-style transparent evaluation harness, not a RAG-Gym source integration.
- No agent training, SFT, DPO, reward model, or reinforcement learning workflow is implemented.
- Metrics are deterministic POC heuristics over the synthetic corpus and matching golden questions.
- Adoption decisions still require real benchmark evidence before replacing deterministic workflows.
- No upstream source, model assets, or external data were introduced.

Exit condition:

Fixed and guided retrieval workflows can be exported and compared through a transparent audit trail. Agentic retrieval remains gated behind demonstrated quality improvement without reduced governance transparency.


## Production Roadmap Layer 3 - Source Governance and Research Intelligence MCP

Status: Complete for the local production-foundation slice

Implemented:

- Extended `src/vyu/sources/registry.py` with source/policy version fields and scoped tenant/workspace access-policy checks.
- Added `src/vyu/research_mcp/contracts.py` for research scope, tool definitions, query decompositions, search plans, tool-call audit records, replay records, and execution records.
- Added `src/vyu/research_mcp/registry.py` for approved research tool registration with source, action, intended-use, and tenant/workspace enforcement.
- Added `src/vyu/research_mcp/planner.py` for deterministic query decomposition, exact acronym query expansion, and bounded approved-tool search planning.
- Added `src/vyu/research_mcp/runtime.py` for governed connector execution with request hashes, result hashes, audit records, and replay support.
- Added `src/vyu/research_mcp/audit.py` and `src/vyu/research_mcp/hashing.py` for JSONL audit/replay stores and canonical hashing.
- Added `src/vyu/connectors/research_sources.py` with deterministic non-network connector shells for Semantic Scholar, ClinicalTrials, guideline, and internal-document sources.
- Added `config/research_tool_registry.example.json` with approved PubMed search and blocked placeholders for Semantic Scholar, ClinicalTrials, guideline, and internal-document tools.
- Added production documentation in `docs/production/research-intelligence-mcp-layer.md`.
- Added tests:
  - `tests/test_research_mcp_registry.py`
  - `tests/test_research_mcp_planner.py`
  - `tests/test_research_mcp_runtime.py`
  - `tests/test_research_source_connectors.py`

Verification:

```text
python -m unittest tests.test_research_mcp_registry
python -m unittest tests.test_research_mcp_planner
python -m unittest tests.test_research_mcp_runtime
python -m unittest tests.test_research_source_connectors
python -m unittest discover
```

Observed result:

```text
Ran 189 tests in 27.998s
OK (skipped=1)
```

Current limitations:

- Semantic Scholar, ClinicalTrials.gov, guideline, and internal-document connectors are declared as planned tool entries but remain blocked until source terms, connector configuration, replay fixtures, and staged validations are approved.
- Tool-call audit/replay persistence is JSONL for this local slice; deployed production can later route these records into the append-only audit/event store.
- Query decomposition is deterministic and conservative, not an autonomous browsing agent.
- No external source, model, corpus, or upstream code was introduced.

Exit condition:

Vyu can plan and execute MCP-style research acquisition through approved tools and approved tenant-scoped sources only, while producing reproducible request/result hashes and replayable tool-call audit records.

## Update Checklist For Future Phases

After each phase:

- Update the status summary table.
- Add implemented files and behaviors.
- Add verification commands and observed results.
- Record deferred work and known limitations.
- Confirm whether upstream source, model assets, or external data were introduced.
- Keep `README.md` phase status aligned with this roadmap.
