from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from src.vyu.jobs.models import ResearchRun
from src.vyu.research.repository import ResearchExecutionRepository
from src.vyu.research_mcp.contracts import ToolCallAuditRecord, ToolCallReplayRecord


class PostgresToolCallAuditSink:
    def __init__(
        self,
        repository: ResearchExecutionRepository,
        session: Session,
        run: ResearchRun,
    ):
        self.repository = repository
        self.session = session
        self.run = run

    def append(self, record: ToolCallAuditRecord) -> None:
        self.repository.save_tool_call(self.session, run=self.run, record=record)


class PostgresReplayStore:
    def __init__(
        self,
        repository: ResearchExecutionRepository,
        session: Session,
        run: ResearchRun,
    ):
        self.repository = repository
        self.session = session
        self.run = run

    def append(self, record: ToolCallReplayRecord) -> None:
        self.repository.save_replay(self.session, run=self.run, record=record)

    def get(self, request_hash: str) -> ToolCallReplayRecord | None:
        return self.repository.get_replay(
            self.session,
            tenant_id=self.run.tenant_id,
            workspace_id=self.run.workspace_id,
            request_hash=request_hash,
        )


def lookup_completed_tool_call(
    repository: ResearchExecutionRepository,
    session: Session,
    *,
    research_run_id: UUID,
    request_hash: str,
) -> tuple[ToolCallAuditRecord, ToolCallReplayRecord] | None:
    record = repository.get_tool_call(
        session,
        research_run_id=research_run_id,
        request_hash=request_hash,
    )
    if record is None or record.status != "ok":
        return None
    replay = repository.get_replay(
        session,
        tenant_id=UUID(record.tenant_id),
        workspace_id=UUID(record.workspace_id),
        request_hash=request_hash,
    )
    if replay is None:
        return None
    return record, replay
