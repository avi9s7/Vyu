# VYU Model Gateway and Grounded Synthesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable, auditable model/embedding providers and generate structured evidence-grounded answers whose claims are validated against persisted retrieval evidence.

**Architecture:** A provider-neutral gateway is the only code allowed to call model or embedding APIs. Synthesis receives a persisted retrieval run, builds a minimized evidence context, invokes one approved prompt/model policy, validates strict structured output, maps each claim to exact citation IDs, and fails closed on unsupported claims, malformed output, policy block, or missing audit persistence.

**Tech Stack:** Python provider SDKs behind adapters, OpenAI Responses API adapter, Azure/Anthropic/Google adapters when approved, Pydantic JSON schemas, PostgreSQL, SQS synthesis worker, Secrets Manager, OpenTelemetry, pytest.

---

## Entry Gate

- Plans 1-4 and 6 are complete.
- Retrieval run/evidence/citation contracts are stable and benchmarked.
- Provider data-use, retention, region, training, security, and commercial terms are approved.
- One generation model snapshot and one embedding model pass staging evaluation.

Do not hard-code a remembered “latest” model name. Configure a reviewed model ID/snapshot and record it on every call. OpenAI's current official model catalog and supported Responses/structured-output features must be checked when selecting the deployment model.

## Task 1: Define Provider-Neutral Gateway Contracts

**Files:**

```text
src/vyu/model_gateway/contracts.py
src/vyu/model_gateway/errors.py
src/vyu/model_gateway/gateway.py
tests/unit/model_gateway/test_contracts.py
tests/unit/model_gateway/test_gateway.py
```

- [ ] Define immutable contracts:

```text
ModelRequest(request_id, tenant_id, workspace_id, run_id, use_case,
             provider_id, model_id, prompt_template_id, prompt_version,
             system_instructions, input, output_schema, max_output_tokens,
             timeout_seconds, temperature, evidence_context_sha256,
             policy_version, contains_phi=false)
ModelResponse(provider_id, model_id, provider_request_id, output,
              input_tokens, output_tokens, reasoning_tokens, cached_tokens,
              latency_ms, finish_reason, request_sha256, response_sha256,
              schema_valid, created_at)
EmbeddingRequest/EmbeddingResponse with text hashes, model, dimensions, usage
ProviderHealth(status, checked_at, latency_ms, safe_code)
```

- [ ] Define protocols `GenerationAdapter.generate`, `EmbeddingAdapter.embed`, and `ProviderAdapter.health`. No domain package imports a concrete provider SDK.

- [ ] Errors are `GatewayValidationError`, `GatewayPolicyBlocked`, `GatewayRateLimited(retry_after)`, `GatewayTimeout`, `GatewayUnavailable`, `GatewayMalformedResponse`, and `GatewayAuthenticationError`. Provider exception text is not returned to API/UI.

- [ ] Validate `contains_phi` is always false, output schema is bounded, input/context size is within policy, model/provider/use-case is approved, and prompt version exists before an adapter call.

- [ ] Tests use fake adapters to prove routing, validation-before-call, timeout propagation, usage normalization, and no fallback after policy/malformed-output failure.

## Task 2: Persist Provider, Prompt, Call, and Cost Records

**Files:** migration `0006_model_synthesis.py`, models/repositories, tests

- [ ] Add:

```text
model_policy_versions(id, version, status, allowed_providers, allowed_models,
                      use_cases, limits, fallback_rules, approved_by,
                      approved_at, sha256, created_at)
prompt_templates(id, name, use_case, version, status, template,
                 output_schema, sha256, approved_by, approved_at, created_at)
model_calls(id, tenant_id, workspace_id, run_id, job_id, provider_id,
            model_id, prompt_template_id, prompt_version, policy_version,
            request_sha256, response_sha256, evidence_context_sha256,
            provider_request_id, status, safe_error_code, usage,
            latency_ms, estimated_cost_minor, currency, created_at)
answers(id, tenant_id, workspace_id, research_run_id, retrieval_run_id,
        version, status, answer_text, uncertainty, limitations,
        model_call_id, prompt_version, evidence_context_sha256,
        created_at)
answer_claims(id, tenant_id, workspace_id, answer_id, ordinal, text,
              support_status, created_at)
claim_citations(id, tenant_id, workspace_id, claim_id, citation_id,
                document_version_id, chunk_id, created_at)
```

- [ ] Prompt/model policy is immutable after approval. New text/schema/model rules create a new version.

- [ ] Store request/response hashes and normalized structured answer, not provider credentials. Raw prompts/responses are excluded from ordinary logs; retained encrypted payloads require a separate approved retention flag and bucket.

- [ ] RLS, uniqueness, append-only approved answer versions, migration round-trip, and repository scope tests pass.

## Task 3: Implement Configuration and Secret Resolution

**Files:** `config.py`, secret resolver, example configuration, tests

- [ ] Required non-secret settings identify generation/embedding provider, model IDs, timeouts, token/cost budgets, prompt/policy versions, and Secrets Manager ARNs.

- [ ] `SecretResolver` retrieves enabled provider credentials at process start or bounded cache refresh, never prints values, and exposes only typed credential objects to the adapter.

- [ ] Startup fails in staging/production when provider/model/policy/prompt is absent, secret is placeholder/missing, fixture adapter is enabled, or generation and embedding dimensions conflict with active indexes.

- [ ] A secret rotation changes provider secret version, forces new ECS deployment, runs health/evaluation smoke, then revokes the old credential.

- [ ] Tests use a fake Secrets Manager client and prove missing/denied/malformed/rotated values without leaking values into exceptions or captured logs.

## Task 4: Implement the OpenAI Adapter

**Files:** `adapters/openai.py`, response fixtures, adapter contract tests

- [ ] Use the official OpenAI SDK and Responses API for generation. Use the Embeddings endpoint for an approved embedding model. Do not enable provider web search, file search, code execution, computer use, or arbitrary tools in VYU synthesis.

- [ ] Request strict structured output using the approved JSON schema when the selected model supports it. Otherwise the adapter is not approved for synthesis.

- [ ] Pass model ID, bounded instructions/input, output schema, max output, timeout, and a VYU request identifier. Do not pass secrets in headers created outside the official client.

- [ ] Normalize provider request ID, usage, finish reason, refusal/incomplete state, and structured output. A refusal or incomplete response is not converted into a normal answer.

- [ ] Retry only official transient/rate-limit classes with bounded attempts and jitter; honor retry delay. Do not retry authentication, invalid request, policy/refusal, or schema errors.

- [ ] Contract tests use recorded sanitized fixtures or mocked SDK transport for success, strict-schema failure, refusal, incomplete output, timeout, 429, 500, auth failure, usage, and request-ID capture. No live call runs in normal CI.

- [ ] Scheduled staging evaluation calls the configured model snapshot and records quality/latency/cost. Model aliases are not promoted without evaluation.

Official references:

- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [OpenAI model feature comparison](https://developers.openai.com/api/docs/models/compare)
- [OpenAI embedding model reference](https://developers.openai.com/api/docs/models/text-embedding-3-large)

## Task 5: Add Other Provider Adapters Only Through the Same Contract

**Files:** `adapters/azure_openai.py`, `anthropic.py`, `google.py`, provider-specific contract tests

- [ ] Implement one adapter per reviewed provider; do not create provider branches in synthesis.

- [ ] Map provider-specific structured output, refusal, safety block, finish reason, usage, request ID, rate limit, and timeout into gateway contracts.

- [ ] Maintain a capability matrix in `docs/production/model-provider-matrix.md` covering region, data retention/training, BAA/DPA status, structured output, model snapshot pinning, embeddings, timeouts, request IDs, rate-limit headers, and approved use cases.

- [ ] A provider stays disabled until contract tests and the same locked synthesis evaluation pass. “API key works” is not approval.

- [ ] Fallback is permitted only between explicitly approved model policies with compatible output schema and quality. Record primary failure and fallback call. Never fall back after safety/policy/PHI/citation failure.

## Task 6: Build Evidence Context Deterministically

**Files:** `src/vyu/synthesis/context.py`, contracts/tests

- [ ] Load exact persisted retrieval run and top hits. Verify run belongs to the research run/scope, index is the recorded version, chunks are ready, source policy was approved, and chunk hashes match.

- [ ] Construct ordered evidence items containing only citation ID, title/source/date, evidence type/quality, correction/retraction flags, exact excerpt, document/chunk IDs, and location.

- [ ] Treat all source text as untrusted data. Wrap it in a stable delimiter structure and state that instructions inside evidence must not be followed.

- [ ] Fit the context to policy token budget by deterministic ranked inclusion; record included/excluded citations and reason. Never truncate a citation ID or silently cut text that changes meaning.

- [ ] Hash canonical context JSON. Same retrieval/policy/context builder version produces same hash.

- [ ] Tests cover prompt injection in evidence, no evidence, revoked source after run, retracted evidence, token budget, deterministic order/hash, and wrong scope.

## Task 7: Define Strict Grounded Answer Schema and Prompt

**Files:** `synthesis/contracts.py`, versioned prompt configuration, schema tests

- [ ] Output schema requires:

```text
answer_summary
claims[]: {claim_text, citation_ids[], support: supported|mixed|unsupported}
uncertainty
contradictions[]
limitations[]
abstained: boolean
abstention_reason: nullable stable code
```

- [ ] Citation IDs must come from provided context. Every non-abstained factual claim needs at least one citation. Unsupported claims cannot appear in `answer_summary` as facts.

- [ ] Prompt states intended use, prohibited patient-specific behavior, evidence-only constraint, source text untrusted status, contradiction/uncertainty duties, citation rules, and abstention conditions. It does not ask for hidden chain of thought.

- [ ] Version prompt text and JSON schema together. Approval stores hash, owner, evaluation report, and effective time.

- [ ] Tests snapshot canonical schema/prompt hash and prove changes require a version bump.

## Task 8: Implement Synthesis and Post-Generation Validation

**Files:** `synthesis/service.py`, validators, worker handler, tests

- [ ] Worker transitions run to `synthesizing`, builds context, records pending model call, invokes gateway, validates output, persists answer/claims/citations/model call/audit/events transactionally, then enqueues governance work.

- [ ] Validators reject unknown citation, missing citation, empty claim, unsupported claim represented as supported, cited chunk hash mismatch, prohibited patient-specific content, output beyond limits, and answer when context requires abstention.

- [ ] Add deterministic lexical entailment/overlap checks only as warning signals. Do not label them clinical truth. Locked expert evaluation determines final thresholds.

- [ ] On malformed output, allow one schema-repair attempt only when model policy permits and the second call is separately recorded. Never ask a model to repair a safety/policy block.

- [ ] Failure leaves no approved answer and produces visible `failed` or `blocked` run status with safe reason.

- [ ] Tests cover valid answer, unsupported/unknown citations, model refusal, prompt injection, empty retrieval, contradiction disclosure, deterministic abstention, duplicate delivery, repair attempt, provider fallback, and audit failure.

## Task 9: Add Answer API and Cost/Health Administration

**Files:** answer route, admin provider/model policy routes, OpenAPI/client/tests

- [ ] `GET /v1/research/searches/{id}/answer` returns selected version, claims/citations, uncertainty, contradictions, limitations, status, model/prompt/index/policy versions, and governance/review links. It never returns raw provider prompt/response.

- [ ] Admin routes show provider health, aggregate usage/cost/latency/errors, enabled policies, prompt versions, and evaluation status. Secret values and provider credentials are never returned.

- [ ] Policy/prompt activation requires admin permission, idempotency key, reason, approved evaluation ID, and audit event.

- [ ] Regenerate OpenAPI/client and test role/scope, missing answer, blocked answer, version selection, and safe error behavior.

## Task 10: Evaluation and Staging Release Gate

- [ ] Locked evaluation measures JSON validity, citation validity/precision, unsupported claim rate, faithfulness, abstention correctness, contradiction disclosure, prohibited-use response, prompt-injection resistance, latency, tokens, and cost.
- [ ] Compare deterministic POC baseline and each provider/model/prompt/index combination. Do not promote on aggregate score when any critical safety case fails.
- [ ] Human evidence reviewers adjudicate a non-PHI pilot set and disagreement. Record reviewer agreement and unresolved cases.
- [ ] Force provider timeout, rate limit, malformed output, refusal, secret rotation, duplicate message, and audit persistence failure in staging; verify expected states and alarms.
- [ ] Mark Plan 7 complete only for the exact model snapshot, embedding model, prompt, schema, index, policy, Git SHA, and image digest that passed.

## Exit Gate

- Domain/synthesis code calls only provider-neutral gateway protocols.
- At least one generation and embedding adapter passes contract, security/privacy, and locked evaluation gates.
- Every model call records provider/model/prompt/policy/context hashes, usage, latency, and safe outcome.
- Every factual claim maps to exact persisted retrieval citations.
- Unknown/missing citations, unsupported claims, PHI/patient-specific content, malformed output, refusal, and audit failure fail closed.
- Prompt/model changes require new versions and evaluation.
- Provider keys can rotate without code changes.

## Handoff

Plan 8 consumes validated answer versions and model-call lineage to calculate governance, create review tasks, and gate exports. It cannot override synthesis validation or make a blocked answer exportable.

