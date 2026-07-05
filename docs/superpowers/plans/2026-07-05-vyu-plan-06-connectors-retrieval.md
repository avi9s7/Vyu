# VYU Governed Connectors and Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute approved live evidence searches and provide reproducible tenant-scoped hybrid retrieval with persisted traces and measurable quality.

**Architecture:** Source and tool policy are database-versioned. Existing Research MCP planning, source gates, audit, replay, and PubMed normalization are adapted behind production repositories and worker handlers. PostgreSQL full-text search and pgvector provide the first lexical/vector indexes; reciprocal-rank fusion combines results. Every query records the exact policy, connector, corpus, chunk, embedding, and index versions.

**Tech Stack:** PostgreSQL 17, pgvector, SQLAlchemy, SQS workers, PubMed E-utilities, HTTPX, provider-neutral embedding gateway, BM25/full-text ranking, vector cosine distance, RRF, pytest.

---

## Entry Gate

- Plans 1-4 complete.
- Plan 5 `ready` chunks exist for tenant documents.
- PubMed intended use, NCBI contact email, rate policy, and terms review are approved.
- At least one embedding provider is configured in staging; Plan 7 may replace the temporary adapter through the same contract.

## Task 1: Persist Versioned Source and Tool Policy

**Files:** policy models/repositories, migration `0005_source_retrieval.py`, import command, tests

- [ ] Add `source_policy_versions`, `sources`, `research_tool_versions`, and `research_tools`. Preserve approval status, allowed/forbidden uses, license/terms reference, PHI status, rate policy, retention, owner, effective times, approver, and immutable version hash.

- [ ] Policy activation is an append-only version change. Existing research runs continue to reference their original policy version. Emergency quarantine blocks new calls immediately and records actor/reason/audit event.

- [ ] Import `config/source_registry.example.json` and `config/research_tool_registry.example.json` in dry-run/apply mode. PubMed may be active; Semantic Scholar, ClinicalTrials.gov, guidelines, and internal sources remain disabled until their own approval evidence exists.

- [ ] Tests prove unapproved/expired/quarantined/wrong-use/wrong-tenant tools cannot produce a plan or call transport.

## Task 2: Harden the Connector Runtime

**Files:** `src/vyu/connectors/http.py`, runtime, PubMed adapter, tests

- [ ] Replace `urllib` direct use with an injected HTTPX client configured with connect/read/write/pool timeouts, bounded response bytes, TLS verification, approved host allowlist, safe redirect policy, and user-agent/tool/email.

- [ ] Retry only connection reset, timeout, `429`, and approved `5xx`; honor `Retry-After`; exponential backoff with jitter; cap attempts and elapsed time.

- [ ] Per-source distributed rate limiting uses PostgreSQL advisory/lease records or approved shared mechanism; process-local `StaticRateLimiter` remains test-only.

- [ ] Connector audit stores normalized request hash, response hash, status, count, latency, attempts, provider request/correlation ID, and safe error code. It does not store API keys or full query text in general logs.

- [ ] Replay fixtures contain sanitized provider payloads, request hash, response hash, recorded date, schema version, license note, and expected normalization. Replay never calls the network.

- [ ] Tests cover timeout, `429`, `Retry-After`, non-retryable `400`, redirect to unapproved host, oversized response, invalid JSON, duplicate documents, no email/tool, and replay hash mismatch.

## Task 3: Complete Production PubMed Search and Fetch

**Files:** PubMed search/fetch adapter, normalization contracts, replay fixtures, staged probe

- [ ] Implement search with term, date range, result limit, pagination token, and stable sort. Implement metadata/abstract fetch by PMID in bounded batches.

- [ ] Normalize PMID, DOI, title, abstract, journal, publication date, authors, publication types, language, correction/retraction links, and source timestamps. Preserve raw-response hash and normalized-record hash.

- [ ] Treat PubMed metadata as source metadata, not permission to download or retain arbitrary full text.

- [ ] Add correction/retraction lookup and block or warn according to policy. A retracted record cannot silently support a positive answer.

- [ ] Scheduled staging probe runs a fixed harmless query, validates nonzero normalized results, records latency/schema/freshness, and alarms on repeated failure. It is separate from offline CI.

- [ ] Tests use replay by default; live probe requires explicit staging environment and approved credentials/contact configuration.

## Task 4: Integrate Research MCP with the Deployed Worker

**Files:** research worker handler, composition, API/event tests

- [ ] Register `research.execute` handler in the generic worker dispatcher. It loads the persisted run, principal snapshot, intended use, source scope, and source/tool policy versions.

- [ ] Adapt existing `ResearchSearchPlanner` and `GovernedResearchMCP` to repository protocols. Remove direct SQLite construction and local JSON registry reads from production composition.

- [ ] Persist plan before transport. Persist every tool call and replay. Job cancellation is checked before each step and after each provider response.

- [ ] Update `research_run_events` with `planning`, `searching`, source completion, source block/failure, and normalized document counts.

- [ ] Tests prove authorization occurs before planning, source approval before transport, duplicate job delivery reuses completed tool calls, replay avoids transport, and partial upstream failure produces explicit run state.

## Task 5: Define Embedding and Index Contracts

**Files:** `src/vyu/retrieval/embeddings.py`, index models/repository, migration/tests

- [ ] Define `EmbeddingProvider.embed(texts, model, dimensions) -> EmbeddingBatch` with input hashes, provider/model/version, dimensions, usage, latency, and provider request ID.

- [ ] Add `retrieval_indexes`, `chunk_embeddings`, `retrieval_runs`, `retrieval_hits`, and `retrieval_exclusions`. Index manifest includes tenant/workspace, source/document versions, chunker, embedding model/dimensions, build Git SHA, policy version, status, counts, checksum, and evaluation result.

- [ ] Use pgvector column dimension fixed by the approved embedding model. Changing dimensions creates a new table/index generation or compatible migration; never mix dimensions.

- [ ] An embedding cache key is `(text_sha256, provider, model, dimensions)`. Cross-tenant reuse is disabled initially even when text hashes match.

- [ ] Index states are `building`, `validating`, `active`, `failed`, `retired`. Only one active index per tenant/workspace/use case. Activation is transactional after evaluation passes.

## Task 6: Build Deterministic Index Jobs

**Files:** index builder worker, commands, tests

- [ ] Snapshot exact eligible `ready` document versions at job creation. Later uploads do not change the running build.

- [ ] Batch embedding requests by provider limits, bound concurrency, retry transient failures, and persist batches idempotently.

- [ ] Build GIN full-text index and pgvector HNSW index with configuration recorded in the manifest. Run `ANALYZE` before validation.

- [ ] Repeating the same manifest input produces the same manifest checksum and reuses embeddings; it does not create a second active index.

- [ ] Failure leaves previous active index untouched and records safe diagnostics. Activation and retirement happen in one transaction.

- [ ] Tests cover duplicate delivery, provider partial failure, dimension mismatch, cancelled build, document changed after snapshot, activation race, and rollback to previous active index.

## Task 7: Implement Hybrid Retrieval and Trace Persistence

**Files:** lexical/vector/fusion services, repository, tests

- [ ] Lexical query uses PostgreSQL `websearch_to_tsquery`/approved configuration and `ts_rank_cd`. Vector query embeds the normalized query once and uses cosine distance against the active exact-dimension index.

- [ ] Apply source, date, evidence type, language, retraction, document status, access label, tenant, and workspace filters before final selection.

- [ ] Retrieve configurable pools (initially lexical 50, vector 50), fuse with RRF `k=60`, deduplicate by chunk, then return top 20. Values are policy configuration and recorded on the run.

- [ ] Persist query hash, raw/fused scores, rank positions, filters, index version, included hits, excluded hits and reason, latency by stage, and exact citation IDs.

- [ ] No result returns a typed empty retrieval with abstention reason, not a fabricated answer context.

- [ ] Tests use locked fixtures to prove ranking, filters, RRF math, retraction exclusion, wrong-tenant invisibility, exact trace reconstruction, and deterministic repeated retrieval.

## Task 8: Create Retrieval APIs

**Files:** research evidence/status routes, admin index routes, OpenAPI/client/tests

- [ ] `GET /v1/research/searches/{id}/evidence` returns paginated included evidence and safe exclusion summary; source text access requires authorization and exact ready version.

- [ ] `GET /v1/research/searches/{id}/events` exposes progress without provider payloads.

- [ ] Admin routes list/build/validate/activate/retire indexes using idempotent background jobs and required reason/permission.

- [ ] Evidence response includes citation ID, document/version, title, source, location, excerpt, ranks/scores, quality flags, correction/retraction state, and retrieval/index IDs.

- [ ] Cross-tenant, retired index, building index, missing evidence, and unauthorized source tests pass; regenerate OpenAPI and TypeScript client.

## Task 9: Establish Quality Evaluation and Release Thresholds

**Files:** evaluation dataset schema/registry, retrieval evaluation runner/report, CI/staging workflow

- [ ] Preserve the synthetic golden set and add an approved non-PHI expert-adjudicated pilot set with dataset version, license, owner, split, adjudicators, and checksum.

- [ ] Measure Recall@5/10/20, MRR@10, nDCG@10, citation-source precision, retraction exclusion, source-policy violations, empty-result correctness, latency, and cost.

- [ ] Prevent tuning on the held-out release split. Dataset and threshold changes require evidence-owner approval and a new version.

- [ ] CI runs fast synthetic evaluation. Staging runs full locked evaluation for every embedding/index/retrieval change. Activation fails when any approved threshold regresses beyond tolerance.

- [ ] Report per-question failures and included/excluded evidence, not aggregate scores only.

## Task 10: Staging Validation and Operations

- [ ] Run live PubMed probe and a real public-literature research job.
- [ ] Verify policy/version/audit/connector/replay/retrieval lineage end to end.
- [ ] Force PubMed timeout/429 and embedding-provider timeout; verify bounded retry, visible state, alarms, and no duplicate charge after redelivery.
- [ ] Rebuild same index twice and verify manifest/embedding reuse.
- [ ] Attempt cross-tenant search/evidence/index access and verify denial.
- [ ] Exercise index failure and previous-index continuity.
- [ ] Record benchmark report, source approval, live probe, dashboard, alarm, and rollback evidence; then mark Plan 6 complete.

## Exit Gate

- PubMed is the only mandatory live source and passes replay plus staged live validation.
- Disabled sources cannot plan or call transport.
- Research MCP runs through deployed worker and PostgreSQL repositories.
- Hybrid retrieval uses active versioned indexes and exact tenant scope.
- Every result/absence is reconstructable from persisted traces.
- Synthetic and approved pilot retrieval gates pass.
- Source, index, embedding, and retrieval failures are visible and recoverable without losing the previous active index.

## Handoff

Plan 7 consumes only persisted retrieval hits from a completed retrieval run. It must not perform free-form web browsing, query disabled tools, or embed/retrieve independently of this service.

