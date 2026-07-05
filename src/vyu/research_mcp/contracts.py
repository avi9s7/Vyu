from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.vyu.connectors import ConnectorResult, SearchRequest
from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign


@dataclass(frozen=True)
class ResearchScope:
    tenant_id: str
    workspace_id: str
    user_id: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ResearchScope":
        return cls(
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            user_id=str(payload.get("user_id", "")),
        )


@dataclass(frozen=True)
class ResearchToolDefinition:
    tool_id: str
    display_name: str
    source_id: str
    connector_name: str
    approved: bool
    allowed_actions: tuple[str, ...] = ("search",)
    allowed_uses: tuple[str, ...] = ("literature_search",)
    capabilities: tuple[str, ...] = ("search",)
    max_results: int = 10
    tenant_ids: tuple[str, ...] = ()
    workspace_ids: tuple[str, ...] = ()
    policy_version: str = "research_tool_policy_v1"
    description: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "display_name": self.display_name,
            "source_id": self.source_id,
            "connector_name": self.connector_name,
            "approved": self.approved,
            "allowed_actions": list(self.allowed_actions),
            "allowed_uses": list(self.allowed_uses),
            "capabilities": list(self.capabilities),
            "max_results": self.max_results,
            "tenant_ids": list(self.tenant_ids),
            "workspace_ids": list(self.workspace_ids),
            "policy_version": self.policy_version,
            "description": self.description,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ResearchToolDefinition":
        return cls(
            tool_id=str(payload["tool_id"]),
            display_name=str(payload["display_name"]),
            source_id=str(payload["source_id"]),
            connector_name=str(payload["connector_name"]),
            approved=bool(payload.get("approved", False)),
            allowed_actions=tuple(str(action) for action in payload.get("allowed_actions", ["search"])),
            allowed_uses=tuple(str(use) for use in payload.get("allowed_uses", ["literature_search"])),
            capabilities=tuple(str(capability) for capability in payload.get("capabilities", ["search"])),
            max_results=int(payload.get("max_results", 10)),
            tenant_ids=tuple(str(tenant_id) for tenant_id in payload.get("tenant_ids", [])),
            workspace_ids=tuple(str(workspace_id) for workspace_id in payload.get("workspace_ids", [])),
            policy_version=str(payload.get("policy_version", "research_tool_policy_v1")),
            description=str(payload.get("description", "")),
        )

    def allows_scope(self, scope: ResearchScope) -> bool:
        tenant_allowed = not self.tenant_ids or scope.tenant_id in self.tenant_ids
        workspace_allowed = not self.workspace_ids or scope.workspace_id in self.workspace_ids
        return tenant_allowed and workspace_allowed


@dataclass(frozen=True)
class QueryDecomposition:
    original_question: str
    subqueries: tuple[str, ...]
    detected_acronyms: tuple[str, ...] = ()
    rationale: str = "deterministic_keyword_and_acronym_decomposition"

    def to_json(self) -> dict[str, Any]:
        return {
            "original_question": self.original_question,
            "subqueries": list(self.subqueries),
            "detected_acronyms": list(self.detected_acronyms),
            "rationale": self.rationale,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "QueryDecomposition":
        return cls(
            original_question=str(payload["original_question"]),
            subqueries=tuple(str(query) for query in payload.get("subqueries", [])),
            detected_acronyms=tuple(str(acronym) for acronym in payload.get("detected_acronyms", [])),
            rationale=str(payload.get("rationale", "deterministic_keyword_and_acronym_decomposition")),
        )


@dataclass(frozen=True)
class SearchPlanStep:
    step_id: str
    tool_id: str
    source_id: str
    connector_name: str
    action: str
    query: str
    limit: int
    filters: dict[str, str] = field(default_factory=dict)
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool_id": self.tool_id,
            "source_id": self.source_id,
            "connector_name": self.connector_name,
            "action": self.action,
            "query": self.query,
            "limit": self.limit,
            "filters": dict(self.filters),
            "reason": self.reason,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SearchPlanStep":
        return cls(
            step_id=str(payload["step_id"]),
            tool_id=str(payload["tool_id"]),
            source_id=str(payload["source_id"]),
            connector_name=str(payload["connector_name"]),
            action=str(payload["action"]),
            query=str(payload["query"]),
            limit=int(payload["limit"]),
            filters={str(key): str(value) for key, value in payload.get("filters", {}).items()},
            reason=str(payload.get("reason", "")),
        )


@dataclass(frozen=True)
class SearchPlan:
    plan_id: str
    run_id: str
    scope: ResearchScope
    intended_use: str
    question: str
    decomposition: QueryDecomposition
    steps: tuple[SearchPlanStep, ...]
    policy_version: str = "research_intelligence_mcp_policy_v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "run_id": self.run_id,
            "scope": self.scope.to_json(),
            "intended_use": self.intended_use,
            "question": self.question,
            "decomposition": self.decomposition.to_json(),
            "steps": [step.to_json() for step in self.steps],
            "policy_version": self.policy_version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SearchPlan":
        return cls(
            plan_id=str(payload["plan_id"]),
            run_id=str(payload["run_id"]),
            scope=ResearchScope.from_json(dict(payload["scope"])),
            intended_use=str(payload["intended_use"]),
            question=str(payload["question"]),
            decomposition=QueryDecomposition.from_json(dict(payload["decomposition"])),
            steps=tuple(SearchPlanStep.from_json(dict(step)) for step in payload.get("steps", [])),
            policy_version=str(payload.get("policy_version", "research_intelligence_mcp_policy_v1")),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class ToolCallReplayRecord:
    request_hash: str
    result_hash: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "request_payload": dict(self.request_payload),
            "result_payload": dict(self.result_payload),
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ToolCallReplayRecord":
        return cls(
            request_hash=str(payload["request_hash"]),
            result_hash=str(payload["result_hash"]),
            request_payload=dict(payload.get("request_payload", {})),
            result_payload=dict(payload.get("result_payload", {})),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class ToolCallAuditRecord:
    call_id: str
    run_id: str
    plan_id: str
    tenant_id: str
    workspace_id: str
    user_id: str
    tool_id: str
    source_id: str
    connector_name: str
    action: str
    query: str
    request_hash: str
    result_hash: str
    result_count: int
    result_document_ids: tuple[str, ...]
    status: str
    replayed: bool = False
    message: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    policy_version: str = "research_intelligence_mcp_policy_v1"

    def to_json(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "tool_id": self.tool_id,
            "source_id": self.source_id,
            "connector_name": self.connector_name,
            "action": self.action,
            "query": self.query,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
            "result_count": self.result_count,
            "result_document_ids": list(self.result_document_ids),
            "status": self.status,
            "replayed": self.replayed,
            "message": self.message,
            "created_at": self.created_at,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ToolCallAuditRecord":
        return cls(
            call_id=str(payload["call_id"]),
            run_id=str(payload["run_id"]),
            plan_id=str(payload["plan_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            user_id=str(payload.get("user_id", "")),
            tool_id=str(payload["tool_id"]),
            source_id=str(payload["source_id"]),
            connector_name=str(payload["connector_name"]),
            action=str(payload["action"]),
            query=str(payload["query"]),
            request_hash=str(payload["request_hash"]),
            result_hash=str(payload["result_hash"]),
            result_count=int(payload["result_count"]),
            result_document_ids=tuple(str(identifier) for identifier in payload.get("result_document_ids", [])),
            status=str(payload["status"]),
            replayed=bool(payload.get("replayed", False)),
            message=str(payload.get("message", "")),
            created_at=str(payload["created_at"]),
            policy_version=str(payload.get("policy_version", "research_intelligence_mcp_policy_v1")),
        )


@dataclass(frozen=True)
class SearchPlanExecution:
    plan: SearchPlan
    results: tuple[ConnectorResult, ...]
    audit_records: tuple[ToolCallAuditRecord, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_json(),
            "results": [connector_result_to_json(result) for result in self.results],
            "audit_records": [record.to_json() for record in self.audit_records],
        }


def connector_result_to_json(result: ConnectorResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "request": search_request_to_json(result.request),
        "documents": [document_to_json(document) for document in result.documents],
        "passages": [passage_to_json(passage) for passage in result.passages],
    }


def connector_result_from_json(payload: dict[str, Any]) -> ConnectorResult:
    return ConnectorResult(
        source=str(payload["source"]),
        request=search_request_from_json(dict(payload["request"])),
        documents=[document_from_json(document) for document in payload.get("documents", [])],
        passages=[passage_from_json(passage) for passage in payload.get("passages", [])],
    )


def search_request_to_json(request: SearchRequest) -> dict[str, Any]:
    return {
        "query": request.query,
        "limit": request.limit,
        "filters": dict(request.filters),
    }


def search_request_from_json(payload: dict[str, Any]) -> SearchRequest:
    return SearchRequest(
        query=str(payload["query"]),
        limit=int(payload.get("limit", 10)),
        filters={str(key): str(value) for key, value in payload.get("filters", {}).items()},
    )


def document_to_json(document: DocumentRecord) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "title": document.title,
        "year": document.year,
        "study_design": str(document.study_design),
        "source_type": document.source_type,
        "publication_status": document.publication_status,
        "abstract": document.abstract,
        "authors": list(document.authors),
        "journal": document.journal,
        "doi": document.doi,
        "pmid": document.pmid,
        "is_preprint": document.is_preprint,
        "is_retracted": document.is_retracted,
        "funding": document.funding,
        "conflicts": document.conflicts,
        "population": document.population,
        "intervention": document.intervention,
        "comparator": document.comparator,
        "outcomes": list(document.outcomes),
    }


def document_from_json(payload: dict[str, Any]) -> DocumentRecord:
    return DocumentRecord(
        document_id=str(payload["document_id"]),
        title=str(payload["title"]),
        year=int(payload["year"]),
        study_design=StudyDesign(str(payload["study_design"])),
        source_type=str(payload["source_type"]),
        publication_status=str(payload["publication_status"]),
        abstract=str(payload.get("abstract", "")),
        authors=tuple(str(author) for author in payload.get("authors", [])),
        journal=str(payload.get("journal", "Vyu Synthetic Biomedical Corpus")),
        doi=payload.get("doi"),
        pmid=payload.get("pmid"),
        is_preprint=bool(payload.get("is_preprint", False)),
        is_retracted=bool(payload.get("is_retracted", False)),
        funding=payload.get("funding"),
        conflicts=payload.get("conflicts"),
        population=payload.get("population"),
        intervention=payload.get("intervention"),
        comparator=payload.get("comparator"),
        outcomes=tuple(str(outcome) for outcome in payload.get("outcomes", [])),
    )


def passage_to_json(passage: PassageRecord) -> dict[str, Any]:
    return {
        "passage_id": passage.passage_id,
        "document_id": passage.document_id,
        "section": passage.section,
        "text": passage.text,
        "page": passage.page,
        "table_id": passage.table_id,
    }


def passage_from_json(payload: dict[str, Any]) -> PassageRecord:
    return PassageRecord(
        passage_id=str(payload["passage_id"]),
        document_id=str(payload["document_id"]),
        section=str(payload["section"]),
        text=str(payload["text"]),
        page=payload.get("page"),
        table_id=payload.get("table_id"),
    )
