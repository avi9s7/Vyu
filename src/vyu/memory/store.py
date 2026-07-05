from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class FollowUpDecision(StrEnum):
    REUSE_EXISTING_EVIDENCE = "REUSE_EXISTING_EVIDENCE"
    SEARCH_NEW_EVIDENCE = "SEARCH_NEW_EVIDENCE"
    REASSESS_EXISTING_EVIDENCE = "REASSESS_EXISTING_EVIDENCE"
    GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE = "GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE"


@dataclass(frozen=True)
class ResearchMemoryRecord:
    tenant_id: str
    workspace_id: str
    user_id: str
    topic: str
    question: str
    retrieved_document_ids: list[str]
    generated_output_ids: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_labels: tuple[str, ...] = ()

    def scope_key(self) -> tuple[str, str, str, str]:
        return (self.tenant_id, self.workspace_id, self.user_id, self.topic)


class InMemoryResearchMemoryStore:
    def __init__(self) -> None:
        self._records: list[ResearchMemoryRecord] = []

    def save(self, record: ResearchMemoryRecord) -> None:
        self._records.append(record)

    def list_for_scope(
        self,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        topic: str,
    ) -> list[ResearchMemoryRecord]:
        key = (tenant_id, workspace_id, user_id, topic)
        return [record for record in self._records if record.scope_key() == key]

    def latest_for_scope(
        self,
        tenant_id: str,
        workspace_id: str,
        user_id: str,
        topic: str,
    ) -> ResearchMemoryRecord | None:
        scoped = self.list_for_scope(tenant_id, workspace_id, user_id, topic)
        return scoped[-1] if scoped else None


def classify_follow_up(
    question: str,
    memory_store: InMemoryResearchMemoryStore,
    tenant_id: str | None = None,
    workspace_id: str | None = None,
    user_id: str | None = None,
    topic: str | None = None,
) -> FollowUpDecision:
    text = question.lower()
    if any(marker in text for marker in ["new", "latest", "preprint", "search", "check whether"]):
        return FollowUpDecision.SEARCH_NEW_EVIDENCE
    if any(marker in text for marker in ["reassess", "review again", "rerun", "re-evaluate"]):
        return FollowUpDecision.REASSESS_EXISTING_EVIDENCE
    if any(marker in text for marker in ["based on that", "that evidence", "same evidence", "summarize"]):
        return FollowUpDecision.REUSE_EXISTING_EVIDENCE
    if all(value is not None for value in [tenant_id, workspace_id, user_id, topic]):
        latest = memory_store.latest_for_scope(tenant_id, workspace_id, user_id, topic)
        if latest is not None:
            return FollowUpDecision.GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE
    return FollowUpDecision.SEARCH_NEW_EVIDENCE
