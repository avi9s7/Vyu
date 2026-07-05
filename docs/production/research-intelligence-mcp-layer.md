# Research Intelligence MCP Layer

## Purpose

The Research Intelligence MCP layer is Vyu's governed research-acquisition boundary. It plans searches, selects approved research tools, executes only approved source-backed connectors, records tool-call audit entries, and captures deterministic result hashes for replay.

This layer is intentionally not a free-form browsing agent. It must only use:

- approved production source registry records,
- approved research tool registry records,
- tenant/workspace-scoped access policies,
- bounded deterministic search plans,
- hashable request/result payloads, and
- replayable tool-call evidence.

## Implemented Components

| Component | Artifact |
| --- | --- |
| Source approval and scope policy | `src/vyu/sources/registry.py` |
| Research tool registry | `src/vyu/research_mcp/registry.py` |
| Query decomposition and search planning | `src/vyu/research_mcp/planner.py` |
| Governed MCP runtime | `src/vyu/research_mcp/runtime.py` |
| Tool-call audit and replay stores | `src/vyu/research_mcp/audit.py` |
| Durable production plan/call/replay storage | `src/vyu/storage/production.py` |
| API and worker execution adapters | `src/vyu/entrypoints/research_mcp.py` |
| Non-network connector shells | `src/vyu/connectors/research_sources.py` |
| Canonical request/result hashing | `src/vyu/research_mcp/hashing.py` |
| Example tool registry | `config/research_tool_registry.example.json` |

## Execution Flow

```text
Research question
  -> deterministic query decomposition
  -> approved tool and source selection
  -> tenant/workspace source-policy check
  -> connector search call
  -> result normalization
  -> request hash and result hash
  -> durable production tool-call audit record
  -> durable replay record for deterministic validation
```

## Source Policy

A source must be approved before use. Scoped policies may use these compact labels:

- `all` or `all_approved_workspaces`
- `tenant:<tenant_id>`
- `workspace:<workspace_id>`
- `workspace:<tenant_id>/<workspace_id>`
- `tenant:<tenant_id>:workspace:<workspace_id>`

Unknown scoped policy labels fail closed when tenant/workspace context is provided.

## Research Tool Policy

A research tool is approved only when all of these pass:

1. the tool exists in `ResearchToolRegistry`,
2. the tool approval flag is true,
3. the requested action is in `allowed_actions`,
4. the intended use is in `allowed_uses`,
5. the tenant/workspace is allowed by the tool scope, and
6. the referenced source is approved for the same use and scope.

## Replay Support

`JsonlReplayStore` remains available for local fixtures. Production execution should use `ProductionReplayStore`, which stores the canonical request hash, result hash, request payload, normalized connector result, run ID, plan ID, source, tool, user, tenant, and workspace in `ProductionStorage`. A runtime call with `replay=True` reuses the recorded result when the request hash matches and recomputes the result hash before accepting the replay.

## Production Operation

The production-operated path uses `handle_research_mcp_execute_api` or `run_research_mcp_execute_worker_job`. These adapters require `RUN_RESEARCH` authorization, create a scoped search plan, persist the plan, execute only approved tools and sources, persist each tool call, persist replay records, and return serializable execution metadata. Failed connector calls, missing connectors, replay hash mismatches, and connector/source mismatches are audited before the runtime raises or returns a blocked/failed boundary response.

`ProductionStorage` schema version 9 adds scoped tables for:

- `research_mcp_plans`
- `research_mcp_tool_calls`
- `research_mcp_replay_records`

These records are included in production backup/restore counts and can be listed only through tenant/workspace-scoped accessors.

## Tests

```bash
python -m unittest tests.test_research_mcp_registry
python -m unittest tests.test_research_mcp_planner
python -m unittest tests.test_research_mcp_runtime
python -m unittest tests.test_research_mcp_entrypoints
python -m unittest tests.test_research_source_connectors
python -m unittest tests.test_production_storage.ProductionStorageTests.test_records_research_mcp_plan_tool_call_and_replay_with_scope
python -m unittest discover
```
