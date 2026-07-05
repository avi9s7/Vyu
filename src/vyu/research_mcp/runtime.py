from __future__ import annotations

from typing import Mapping

from src.vyu.connectors import ConnectorResult, SearchRequest, SourceConnector
from src.vyu.connectors.runtime import ConnectorRuntime
from src.vyu.research_mcp.audit import JsonlReplayStore, JsonlToolCallAuditSink
from src.vyu.research_mcp.contracts import (
    SearchPlan,
    SearchPlanExecution,
    ToolCallAuditRecord,
    ToolCallReplayRecord,
    connector_result_from_json,
    connector_result_to_json,
)
from src.vyu.research_mcp.hashing import stable_hash, short_hash
from src.vyu.research_mcp.registry import ResearchToolRegistry
from src.vyu.sources import SourceRegistry


class GovernedResearchMCP:
    def __init__(
        self,
        tool_registry: ResearchToolRegistry,
        source_registry: SourceRegistry,
        audit_sink: JsonlToolCallAuditSink | None = None,
        replay_store: JsonlReplayStore | None = None,
        connector_runtime: ConnectorRuntime | None = None,
    ):
        self.tool_registry = tool_registry
        self.source_registry = source_registry
        self.audit_sink = audit_sink
        self.replay_store = replay_store
        self.connector_runtime = connector_runtime

    def execute_plan(
        self,
        plan: SearchPlan,
        connectors: Mapping[str, SourceConnector],
        replay: bool = False,
    ) -> SearchPlanExecution:
        results: list[ConnectorResult] = []
        audit_records: list[ToolCallAuditRecord] = []

        for index, step in enumerate(plan.steps, start=1):
            tool = self.tool_registry.require_approved(
                step.tool_id,
                source_registry=self.source_registry,
                scope=plan.scope,
                intended_use=plan.intended_use,
                action=step.action,
            )
            if tool.connector_name != step.connector_name or tool.source_id != step.source_id:
                raise PermissionError(f"Plan step {step.step_id!r} does not match approved tool definition.")

            request = SearchRequest(query=step.query, limit=step.limit, filters=dict(step.filters))
            request_payload = {
                "plan_id": plan.plan_id,
                "run_id": plan.run_id,
                "scope": plan.scope.to_json(),
                "tool_id": step.tool_id,
                "source_id": step.source_id,
                "connector_name": step.connector_name,
                "action": step.action,
                "request": {
                    "query": request.query,
                    "limit": request.limit,
                    "filters": dict(request.filters),
                },
                "policy_version": plan.policy_version,
            }
            request_hash = stable_hash(request_payload)

            result: ConnectorResult
            replayed = False
            replay_record = self.replay_store.get(request_hash) if replay and self.replay_store is not None else None
            if replay_record is not None:
                result = connector_result_from_json(replay_record.result_payload)
                recalculated_hash = stable_hash(connector_result_to_json(result))
                if recalculated_hash != replay_record.result_hash:
                    record = self._audit_record(
                        index=index,
                        plan=plan,
                        step=step,
                        request_hash=request_hash,
                        result_hash=recalculated_hash,
                        result_count=0,
                        result_document_ids=(),
                        status="failed",
                        replayed=True,
                        message="replay_result_hash_mismatch",
                    )
                    self._append_audit(record)
                    audit_records.append(record)
                    raise ValueError("Replay record result hash does not match its stored result payload.")
                result_hash = replay_record.result_hash
                replayed = True
            else:
                try:
                    connector = connectors[step.connector_name]
                except KeyError as exc:
                    record = self._audit_record(
                        index=index,
                        plan=plan,
                        step=step,
                        request_hash=request_hash,
                        result_hash=stable_hash({"error": "missing_connector"}),
                        result_count=0,
                        result_document_ids=(),
                        status="blocked",
                        message=f"missing_connector:{step.connector_name}",
                    )
                    self._append_audit(record)
                    audit_records.append(record)
                    raise KeyError(f"No connector registered for research tool connector {step.connector_name!r}.") from exc
                if connector.source != step.source_id:
                    record = self._audit_record(
                        index=index,
                        plan=plan,
                        step=step,
                        request_hash=request_hash,
                        result_hash=stable_hash({"error": "connector_source_mismatch"}),
                        result_count=0,
                        result_document_ids=(),
                        status="blocked",
                        message=f"connector_source_mismatch:{connector.source}:{step.source_id}",
                    )
                    self._append_audit(record)
                    audit_records.append(record)
                    raise PermissionError(
                        f"Connector {step.connector_name!r} is bound to source {connector.source!r}, "
                        f"but plan step requires source {step.source_id!r}."
                    )
                try:
                    if self.connector_runtime is None:
                        result = connector.search(request)
                    else:
                        result = self.connector_runtime.run(
                            source=step.source_id,
                            action=step.action,
                            operation=lambda: connector.search(request),
                        ).value
                except Exception as exc:
                    record = self._audit_record(
                        index=index,
                        plan=plan,
                        step=step,
                        request_hash=request_hash,
                        result_hash=stable_hash({"error": type(exc).__name__, "message": str(exc)}),
                        result_count=0,
                        result_document_ids=(),
                        status="failed",
                        message=str(exc),
                    )
                    self._append_audit(record)
                    audit_records.append(record)
                    raise
                result_payload = connector_result_to_json(result)
                result_hash = stable_hash(result_payload)
                if self.replay_store is not None:
                    self.replay_store.append(
                        ToolCallReplayRecord(
                            request_hash=request_hash,
                            result_hash=result_hash,
                            request_payload=request_payload,
                            result_payload=result_payload,
                        )
                    )

            record = self._audit_record(
                index=index,
                plan=plan,
                step=step,
                request_hash=request_hash,
                result_hash=result_hash,
                result_count=result.document_count,
                result_document_ids=tuple(document.document_id for document in result.documents),
                status="ok",
                replayed=replayed,
            )
            self._append_audit(record)
            results.append(result)
            audit_records.append(record)

        return SearchPlanExecution(
            plan=plan,
            results=tuple(results),
            audit_records=tuple(audit_records),
        )

    def _audit_record(
        self,
        index: int,
        plan: SearchPlan,
        step,
        request_hash: str,
        result_hash: str,
        result_count: int,
        result_document_ids: tuple[str, ...],
        status: str,
        replayed: bool = False,
        message: str = "",
    ) -> ToolCallAuditRecord:
        return ToolCallAuditRecord(
            call_id=f"mcp-call-{index:02d}-{short_hash({'request': request_hash, 'result': result_hash, 'status': status, 'replayed': replayed}, 10)}",
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            tenant_id=plan.scope.tenant_id,
            workspace_id=plan.scope.workspace_id,
            user_id=plan.scope.user_id,
            tool_id=step.tool_id,
            source_id=step.source_id,
            connector_name=step.connector_name,
            action=step.action,
            query=step.query,
            request_hash=request_hash,
            result_hash=result_hash,
            result_count=result_count,
            result_document_ids=result_document_ids,
            status=status,
            replayed=replayed,
            message=message,
            policy_version=plan.policy_version,
        )

    def _append_audit(self, record: ToolCallAuditRecord) -> None:
        if self.audit_sink is not None:
            self.audit_sink.append(record)
