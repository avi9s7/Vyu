from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.vyu.memory.store import FollowUpDecision


@dataclass(frozen=True)
class ProductionResearchMemoryRecord:
    """Durable, tenant-scoped research memory control-plane record.

    This record intentionally stores identifiers and governance metadata, not raw
    evidence text. Raw documents/evidence packs should live behind approved
    object-storage records and source permissions.
    """

    memory_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    user_id: str
    topic: str
    question: str
    generated_search_queries: tuple[str, ...] = ()
    retrieved_document_ids: tuple[str, ...] = ()
    included_document_ids: tuple[str, ...] = ()
    excluded_documents: tuple[dict[str, Any], ...] = ()
    evidence_assessment_ids: tuple[str, ...] = ()
    user_annotations: tuple[dict[str, Any], ...] = ()
    generated_report_ids: tuple[str, ...] = ()
    model_versions: dict[str, str] = field(default_factory=dict)
    policy_versions: dict[str, str] = field(default_factory=dict)
    citation_graph: tuple[dict[str, Any], ...] = ()
    follow_up_decision: FollowUpDecision = FollowUpDecision.SEARCH_NEW_EVIDENCE
    source_permissions: tuple[str, ...] = ()
    access_labels: tuple[str, ...] = ()
    retention_policy_id: str = "default_research_memory_retention"
    retrieval_run_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def scope_key(self) -> tuple[str, str, str, str]:
        return (self.tenant_id, self.workspace_id, self.user_id, self.topic)

    def is_visible_to(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        topic: str | None = None,
        allowed_source_permissions: set[str] | None = None,
        access_labels: set[str] | None = None,
    ) -> bool:
        if self.tenant_id != tenant_id:
            return False
        if self.workspace_id != workspace_id:
            return False
        if self.user_id != user_id:
            return False
        if topic is not None and self.topic != topic:
            return False
        if allowed_source_permissions is not None:
            if not set(self.source_permissions).issubset(allowed_source_permissions):
                return False
        if access_labels is not None:
            if not set(self.access_labels).issubset(access_labels):
                return False
        return True

    def to_json(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "topic": self.topic,
            "question": self.question,
            "generated_search_queries": list(self.generated_search_queries),
            "retrieved_document_ids": list(self.retrieved_document_ids),
            "included_document_ids": list(self.included_document_ids),
            "excluded_documents": [dict(item) for item in self.excluded_documents],
            "evidence_assessment_ids": list(self.evidence_assessment_ids),
            "user_annotations": [dict(item) for item in self.user_annotations],
            "generated_report_ids": list(self.generated_report_ids),
            "model_versions": dict(self.model_versions),
            "policy_versions": dict(self.policy_versions),
            "citation_graph": [dict(item) for item in self.citation_graph],
            "follow_up_decision": self.follow_up_decision.value,
            "source_permissions": list(self.source_permissions),
            "access_labels": list(self.access_labels),
            "retention_policy_id": self.retention_policy_id,
            "retrieval_run_id": self.retrieval_run_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionResearchMemoryRecord":
        return cls(
            memory_id=str(payload["memory_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            user_id=str(payload["user_id"]),
            topic=str(payload["topic"]),
            question=str(payload["question"]),
            generated_search_queries=tuple(
                str(item) for item in payload.get("generated_search_queries", [])
            ),
            retrieved_document_ids=tuple(
                str(item) for item in payload.get("retrieved_document_ids", [])
            ),
            included_document_ids=tuple(
                str(item) for item in payload.get("included_document_ids", [])
            ),
            excluded_documents=tuple(
                dict(item) for item in payload.get("excluded_documents", [])
            ),
            evidence_assessment_ids=tuple(
                str(item) for item in payload.get("evidence_assessment_ids", [])
            ),
            user_annotations=tuple(
                dict(item) for item in payload.get("user_annotations", [])
            ),
            generated_report_ids=tuple(
                str(item) for item in payload.get("generated_report_ids", [])
            ),
            model_versions={
                str(key): str(value)
                for key, value in payload.get("model_versions", {}).items()
            },
            policy_versions={
                str(key): str(value)
                for key, value in payload.get("policy_versions", {}).items()
            },
            citation_graph=tuple(dict(item) for item in payload.get("citation_graph", [])),
            follow_up_decision=FollowUpDecision(
                str(
                    payload.get(
                        "follow_up_decision",
                        FollowUpDecision.SEARCH_NEW_EVIDENCE.value,
                    )
                )
            ),
            source_permissions=tuple(
                str(item) for item in payload.get("source_permissions", [])
            ),
            access_labels=tuple(str(item) for item in payload.get("access_labels", [])),
            retention_policy_id=str(
                payload.get("retention_policy_id", "default_research_memory_retention")
            ),
            retrieval_run_id=(
                str(payload["retrieval_run_id"])
                if payload.get("retrieval_run_id") is not None
                else None
            ),
            created_at=str(payload["created_at"]),
        )


def classify_production_follow_up(
    question: str,
    prior_memory: ProductionResearchMemoryRecord | None,
) -> FollowUpDecision:
    text = question.lower()
    if any(marker in text for marker in ["new", "latest", "preprint", "search", "check whether"]):
        return FollowUpDecision.SEARCH_NEW_EVIDENCE
    if any(marker in text for marker in ["reassess", "review again", "rerun", "re-evaluate"]):
        return FollowUpDecision.REASSESS_EXISTING_EVIDENCE
    if any(marker in text for marker in ["based on that", "that evidence", "same evidence", "summarize"]):
        return FollowUpDecision.REUSE_EXISTING_EVIDENCE
    if prior_memory is not None:
        return FollowUpDecision.GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE
    return FollowUpDecision.SEARCH_NEW_EVIDENCE
