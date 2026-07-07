# Model Provider Capability Matrix

Last updated: 2026-07-08  
Approval state: engineering adapters present; **no provider is production-approved until locked synthesis evaluation passes in staging.**

VYU enables a provider only when contract tests pass and the same locked synthesis evaluation used for release gates succeeds for the configured model snapshot. An API key that authenticates is not approval.

## Summary

| Provider | Adapter | Generation | Embeddings | Structured output | Staging approval | Production approval |
| --- | --- | --- | --- | --- | --- | --- |
| OpenAI | `openai` | Responses API | Embeddings API | Strict JSON schema | pending evaluation | disabled |
| Azure OpenAI | `azure_openai` | Responses API (Azure) | Embeddings API (Azure) | Strict JSON schema | pending evaluation | disabled |
| Anthropic | `anthropic` | Messages API | not supported | JSON schema via `output_config` | pending evaluation | disabled |
| Google | `google` | Gemini `generate_content` | `embed_content` | `response_json_schema` | pending evaluation | disabled |

## Capability details

| Provider | Region pinning | Data retention / training (operator review) | BAA / DPA status | Model snapshot pinning | Request ID capture | Rate-limit header | Timeout propagation | Approved use cases |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OpenAI | operator-selected deployment region | requires signed enterprise terms review | pending legal review | `VYU_GENERATION_MODEL` / `VYU_EMBEDDING_MODEL` | `response.id` | `retry-after` | SDK request timeout | grounded synthesis only |
| Azure OpenAI | Azure resource region | Microsoft customer agreement + Azure OpenAI terms | pending legal review | deployment name + model snapshot env vars | `response.id` | `retry-after` | SDK request timeout | grounded synthesis only |
| Anthropic | operator-selected API region if available | requires Anthropic enterprise terms review | pending legal review | configured model ID only | `message.id` | `retry-after` | SDK request timeout | grounded synthesis only |
| Google | Google Cloud / Gemini region policy | requires Google Cloud enterprise terms review | pending legal review | configured model ID only | `response_id` | `retry-after` when present | SDK request timeout | grounded synthesis only |

## Gateway contract mapping

| Provider signal | Gateway mapping |
| --- | --- |
| Structured JSON object | `ModelResponse.output`, `schema_valid=true` |
| Refusal / safety block | `GatewayPolicyBlocked` |
| Incomplete / max tokens | `GatewayMalformedResponse` |
| Invalid request / schema rejection | `GatewayValidationError` (no retry) |
| Authentication failure | `GatewayAuthenticationError` (no retry) |
| Rate limit | `GatewayRateLimited` with bounded retry |
| Timeout / connection / 5xx | `GatewayTimeout` or `GatewayUnavailable` with bounded retry |

## Fallback policy

Fallback is permitted only between explicitly approved model policies with compatible output schema and quality. VYU records the primary failure and any fallback call. Fallback is never allowed after safety, policy, PHI, or citation validation failure.

## Promotion checklist

A provider row moves from `pending evaluation` to `approved` only when all items below are recorded for the exact model snapshot, prompt version, schema, index, policy, Git SHA, and image digest:

1. Provider contract tests pass in CI without live calls.
2. Staging synthesis evaluation passes for the locked configuration.
3. Legal/privacy review records region, retention, training, and BAA/DPA status.
4. Operator records Secrets Manager ARN rotation drill and ECS redeploy evidence.

## References

- `src/vyu/model_gateway/adapters/`
- `config/model_gateway.local.example.env`
- `docs/production/runbooks/deployment.md`
