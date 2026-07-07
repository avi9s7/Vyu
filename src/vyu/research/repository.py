from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.jobs.models import ResearchRun, ResearchRunEvent
from src.vyu.research.models import ResearchSearchPlanRow, ResearchToolCallRow, ResearchToolReplayRow
from src.vyu.research_mcp.contracts import (
    SearchPlan,
    ToolCallAuditRecord,
    ToolCallReplayRecord,
)
from src.vyu.research_mcp.hashing import stable_hash


TERMINAL_RESEARCH_STATUSES = frozenset(
    {"completed", "failed", "blocked", "cancelled"},
)


class ResearchCancelledError(Exception):
    """Raised when a research run is cancelled during execution."""


@dataclass(frozen=True)
class ResearchRunContext:
    run: ResearchRun
    job_id: UUID


class ResearchExecutionRepository:
    def get_run(self, session: Session, research_run_id: UUID) -> ResearchRun | None:
        row = session.scalar(select(ResearchRun).where(ResearchRun.id == research_run_id))
        return row if isinstance(row, ResearchRun) else None

    def get_plan(self, session: Session, research_run_id: UUID) -> SearchPlan | None:
        row = session.scalar(
            select(ResearchSearchPlanRow).where(
                ResearchSearchPlanRow.research_run_id == research_run_id
            )
        )
        if not isinstance(row, ResearchSearchPlanRow):
            return None
        return SearchPlan.from_json(dict(row.plan_json))

    def save_plan(self, session: Session, *, run: ResearchRun, plan: SearchPlan) -> None:
        existing = session.scalar(
            select(ResearchSearchPlanRow).where(
                ResearchSearchPlanRow.research_run_id == run.id
            )
        )
        if isinstance(existing, ResearchSearchPlanRow):
            return
        plan_json = plan.to_json()
        session.add(
            ResearchSearchPlanRow(
                id=uuid4(),
                tenant_id=run.tenant_id,
                workspace_id=run.workspace_id,
                research_run_id=run.id,
                plan_id=plan.plan_id,
                plan_hash=stable_hash(plan_json),
                policy_version=plan.policy_version,
                plan_json=plan_json,
            )
        )

    def get_tool_call(
        self,
        session: Session,
        *,
        research_run_id: UUID,
        request_hash: str,
    ) -> ToolCallAuditRecord | None:
        row = session.scalar(
            select(ResearchToolCallRow).where(
                ResearchToolCallRow.research_run_id == research_run_id,
                ResearchToolCallRow.request_hash == request_hash,
            )
        )
        if not isinstance(row, ResearchToolCallRow):
            return None
        return ToolCallAuditRecord.from_json(dict(row.record_json))

    def save_tool_call(
        self,
        session: Session,
        *,
        run: ResearchRun,
        record: ToolCallAuditRecord,
    ) -> None:
        existing = session.scalar(
            select(ResearchToolCallRow).where(
                ResearchToolCallRow.research_run_id == run.id,
                ResearchToolCallRow.request_hash == record.request_hash,
            )
        )
        if isinstance(existing, ResearchToolCallRow):
            return
        session.add(
            ResearchToolCallRow(
                id=uuid4(),
                tenant_id=run.tenant_id,
                workspace_id=run.workspace_id,
                research_run_id=run.id,
                call_id=record.call_id,
                plan_id=record.plan_id,
                request_hash=record.request_hash,
                result_hash=record.result_hash,
                status=record.status,
                result_count=record.result_count,
                record_json=record.to_json(),
            )
        )

    def get_replay(
        self,
        session: Session,
        *,
        tenant_id: UUID,
        workspace_id: UUID,
        request_hash: str,
    ) -> ToolCallReplayRecord | None:
        row = session.scalar(
            select(ResearchToolReplayRow).where(
                ResearchToolReplayRow.tenant_id == tenant_id,
                ResearchToolReplayRow.workspace_id == workspace_id,
                ResearchToolReplayRow.request_hash == request_hash,
            )
        )
        if not isinstance(row, ResearchToolReplayRow):
            return None
        return ToolCallReplayRecord(
            request_hash=row.request_hash,
            result_hash=row.result_hash,
            request_payload=dict(row.request_payload),
            result_payload=dict(row.result_payload),
            created_at=row.created_at.isoformat(),
        )

    def save_replay(
        self,
        session: Session,
        *,
        run: ResearchRun,
        record: ToolCallReplayRecord,
    ) -> None:
        existing = session.scalar(
            select(ResearchToolReplayRow).where(
                ResearchToolReplayRow.tenant_id == run.tenant_id,
                ResearchToolReplayRow.workspace_id == run.workspace_id,
                ResearchToolReplayRow.request_hash == record.request_hash,
            )
        )
        if isinstance(existing, ResearchToolReplayRow):
            return
        session.add(
            ResearchToolReplayRow(
                id=uuid4(),
                tenant_id=run.tenant_id,
                workspace_id=run.workspace_id,
                research_run_id=run.id,
                request_hash=record.request_hash,
                result_hash=record.result_hash,
                request_payload=dict(record.request_payload),
                result_payload=dict(record.result_payload),
            )
        )

    def append_event(
        self,
        session: Session,
        *,
        run: ResearchRun,
        event_type: str,
        safe_message: str,
        details: dict[str, object] | None = None,
    ) -> ResearchRunEvent:
        sequence = self._next_event_sequence(session, run.id)
        event = ResearchRunEvent(
            id=uuid4(),
            tenant_id=run.tenant_id,
            workspace_id=run.workspace_id,
            research_run_id=run.id,
            sequence=sequence,
            event_type=event_type,
            safe_message=safe_message,
            details=details or {},
        )
        session.add(event)
        return event

    def _next_event_sequence(self, session: Session, research_run_id: UUID) -> int:
        latest = session.scalar(
            select(ResearchRunEvent.sequence)
            .where(ResearchRunEvent.research_run_id == research_run_id)
            .order_by(ResearchRunEvent.sequence.desc())
            .limit(1)
        )
        return 1 if latest is None else int(latest) + 1
