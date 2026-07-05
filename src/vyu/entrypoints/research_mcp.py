from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Callable, Mapping

from src.vyu.authz import Action, AuthorizationPolicy, Principal, ResourceScope
from src.vyu.connectors import SourceConnector
from src.vyu.connectors.runtime import ConnectorRuntime
from src.vyu.research_mcp import (
    GovernedResearchMCP,
    ProductionReplayStore,
    ProductionToolCallAuditSink,
    ResearchScope,
    ResearchSearchPlanner,
    ResearchToolRegistry,
)
from src.vyu.sources import SourceRegistry
from src.vyu.storage import ProductionScope, ProductionStorage


@dataclass(frozen=True)
class ResearchMcpExecutePayload:
    principal: Principal
    run_id: str
    tenant_id: str
    workspace_id: str
    question: str
    intended_use: str = "literature_search"
    source_ids: tuple[str, ...] = ()
    max_results_per_step: int = 5
    max_steps: int = 8
    replay: bool = False


@dataclass(frozen=True)
class ResearchMcpExecuteApiRequest:
    request_id: str
    payload: ResearchMcpExecutePayload


@dataclass(frozen=True)
class ResearchMcpExecuteApiResponse:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True)
class ResearchMcpExecuteWorkerJob:
    job_id: str
    payload: ResearchMcpExecutePayload


@dataclass(frozen=True)
class ResearchMcpExecuteWorkerResult:
    job_id: str
    status: str
    body: dict[str, object]

    def to_json(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "body": dict(self.body),
        }


def handle_research_mcp_execute_api(
    request: ResearchMcpExecuteApiRequest,
    storage: ProductionStorage,
    source_registry: SourceRegistry,
    tool_registry: ResearchToolRegistry,
    connectors: Mapping[str, SourceConnector],
    policy: AuthorizationPolicy | None = None,
    connector_runtime: ConnectorRuntime | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    created_at: str | None = None,
) -> ResearchMcpExecuteApiResponse:
    try:
        body = _execute(
            payload=request.payload,
            storage=storage,
            source_registry=source_registry,
            tool_registry=tool_registry,
            connectors=connectors,
            policy=policy,
            connector_runtime=connector_runtime,
            audit_event_id_factory=audit_event_id_factory,
            created_at=created_at,
        )
    except PermissionError as exc:
        return ResearchMcpExecuteApiResponse(
            status_code=403,
            body={
                "request_id": request.request_id,
                "run_id": request.payload.run_id,
                "tenant_id": request.payload.tenant_id,
                "workspace_id": request.payload.workspace_id,
                "status": "blocked",
                "reason": "research_mcp_not_authorized",
                "message": str(exc),
            },
        )
    except Exception as exc:  # noqa: BLE001 - framework-neutral boundary returns safe errors.
        return ResearchMcpExecuteApiResponse(
            status_code=500,
            body={
                "request_id": request.request_id,
                "run_id": request.payload.run_id,
                "tenant_id": request.payload.tenant_id,
                "workspace_id": request.payload.workspace_id,
                "status": "failed",
                "reason": "research_mcp_execution_failed",
                "message": str(exc),
            },
        )
    body["request_id"] = request.request_id
    return ResearchMcpExecuteApiResponse(status_code=200, body=body)


def run_research_mcp_execute_worker_job(
    job: ResearchMcpExecuteWorkerJob,
    storage: ProductionStorage,
    source_registry: SourceRegistry,
    tool_registry: ResearchToolRegistry,
    connectors: Mapping[str, SourceConnector],
    policy: AuthorizationPolicy | None = None,
    connector_runtime: ConnectorRuntime | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    created_at: str | None = None,
) -> ResearchMcpExecuteWorkerResult:
    response = handle_research_mcp_execute_api(
        ResearchMcpExecuteApiRequest(request_id=job.job_id, payload=job.payload),
        storage=storage,
        source_registry=source_registry,
        tool_registry=tool_registry,
        connectors=connectors,
        policy=policy,
        connector_runtime=connector_runtime,
        audit_event_id_factory=audit_event_id_factory,
        created_at=created_at,
    )
    return ResearchMcpExecuteWorkerResult(
        job_id=job.job_id,
        status="completed" if response.status_code == 200 else "blocked" if response.status_code == 403 else "failed",
        body=response.body,
    )


def _execute(
    payload: ResearchMcpExecutePayload,
    storage: ProductionStorage,
    source_registry: SourceRegistry,
    tool_registry: ResearchToolRegistry,
    connectors: Mapping[str, SourceConnector],
    policy: AuthorizationPolicy | None,
    connector_runtime: ConnectorRuntime | None,
    audit_event_id_factory: Callable[[str, str], str] | None,
    created_at: str | None,
) -> dict[str, object]:
    scope = ProductionScope(tenant_id=payload.tenant_id, workspace_id=payload.workspace_id)
    (policy or AuthorizationPolicy()).require(
        payload.principal,
        Action.RUN_RESEARCH,
        ResourceScope(tenant_id=payload.tenant_id, workspace_id=payload.workspace_id),
    )
    created = created_at or datetime.now(timezone.utc).isoformat()
    research_scope = ResearchScope(
        tenant_id=payload.tenant_id,
        workspace_id=payload.workspace_id,
        user_id=payload.principal.user_id,
    )
    plan = ResearchSearchPlanner(
        tool_registry=tool_registry,
        source_registry=source_registry,
    ).plan(
        question=payload.question,
        run_id=payload.run_id,
        scope=research_scope,
        intended_use=payload.intended_use,
        source_ids=set(payload.source_ids) if payload.source_ids else None,
        max_results_per_step=payload.max_results_per_step,
        max_steps=payload.max_steps,
    )
    storage.record_research_mcp_plan(
        plan,
        audit_event_id=(
            audit_event_id_factory(payload.run_id, "research_mcp_plan_recorded")
            if audit_event_id_factory is not None
            else f"{plan.plan_id}-recorded-{uuid.uuid4().hex}"
        ),
        audit_created_at=created,
    )
    runtime = GovernedResearchMCP(
        tool_registry=tool_registry,
        source_registry=source_registry,
        audit_sink=ProductionToolCallAuditSink(storage),
        replay_store=ProductionReplayStore(storage, scope),
        connector_runtime=connector_runtime,
    )
    execution = runtime.execute_plan(
        plan,
        connectors=connectors,
        replay=payload.replay,
    )
    result_document_ids = sorted(
        {
            document.document_id
            for result in execution.results
            for document in result.documents
        }
    )
    return {
        "run_id": payload.run_id,
        "tenant_id": payload.tenant_id,
        "workspace_id": payload.workspace_id,
        "status": "completed",
        "reason": "research_mcp_executed",
        "plan": plan.to_json(),
        "result_count": sum(result.document_count for result in execution.results),
        "result_document_ids": result_document_ids,
        "audit_records": [record.to_json() for record in execution.audit_records],
    }
