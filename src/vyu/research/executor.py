from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.jobs.contracts import HandlerResult, JobRecord
from src.vyu.jobs.models import Job, ResearchRun
from src.vyu.policy.repository import PolicyRepository
from src.vyu.policy.service import PolicyService
from src.vyu.research.connectors import build_research_connectors
from src.vyu.research.repository import (
    TERMINAL_RESEARCH_STATUSES,
    ResearchExecutionRepository,
)
from src.vyu.research_mcp.contracts import ResearchScope
from src.vyu.research_mcp.persistence import (
    PostgresReplayStore,
    PostgresToolCallAuditSink,
    lookup_completed_tool_call,
)
from src.vyu.research_mcp.planner import ResearchSearchPlanner
from src.vyu.research_mcp.runtime import GovernedResearchMCP, ResearchRunCancelled


@dataclass(frozen=True)
class ResearchExecutionResult:
    outcome: str
    result: dict[str, object] | None = None
    error_code: str | None = None
    retryable: bool = False


class ResearchRunExecutor:
    def __init__(
        self,
        *,
        policy_service: PolicyService | None = None,
        repository: ResearchExecutionRepository | None = None,
    ):
        self.policy_service = policy_service or PolicyService(PolicyRepository())
        self.repository = repository or ResearchExecutionRepository()

    def execute(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> ResearchExecutionResult:
        del heartbeat
        if job.payload.get("simulate") is not None:
            return self._simulate(job.payload)

        research_run_id = UUID(str(job.payload["research_run_id"]))
        run = self.repository.get_run(session, research_run_id)
        if run is None:
            return ResearchExecutionResult(
                outcome="terminal_failure",
                error_code="research_run_not_found",
            )

        if run.status in TERMINAL_RESEARCH_STATUSES:
            return ResearchExecutionResult(
                outcome="complete",
                result=self._terminal_result(run),
            )

        if self._is_cancelled(session, job, run):
            self._mark_cancelled(session, run)
            return ResearchExecutionResult(
                outcome="complete",
                result={"status": "cancelled", "research_run_id": str(run.id)},
            )

        scope = ResearchScope(
            tenant_id=str(run.tenant_id),
            workspace_id=str(run.workspace_id),
            user_id=str(run.created_by),
        )
        raw_source_ids = job.payload.get("source_ids")
        if isinstance(raw_source_ids, list):
            source_ids = {str(source_id) for source_id in raw_source_ids}
        else:
            source_ids = {str(source_id) for source_id in run.requested_sources}
        intended_use = str(job.payload.get("intended_use", run.intended_use))

        approved_tools = self.policy_service.approved_tools_for_planning(
            session,
            scope=scope,
            intended_use=intended_use,
            source_ids=source_ids,
        )
        if not approved_tools:
            self._set_run_status(session, run, "blocked", current_step="authorization")
            self.repository.append_event(
                session,
                run=run,
                event_type="research_source_blocked",
                safe_message="No approved research tools are available for this run.",
                details={"source_ids": sorted(source_ids), "intended_use": intended_use},
            )
            return ResearchExecutionResult(
                outcome="terminal_failure",
                error_code="no_approved_tools",
            )

        if run.status == "queued":
            self._set_run_status(session, run, "planning", current_step="planning")
            self.repository.append_event(
                session,
                run=run,
                event_type="research_planning_started",
                safe_message="Research planning started.",
            )

        source_registry = self.policy_service.build_source_registry(session)
        tool_registry = self.policy_service.build_tool_registry(session)
        planner = ResearchSearchPlanner(tool_registry, source_registry)
        plan = self.repository.get_plan(session, run.id)
        if plan is None:
            plan = planner.plan(
                str(job.payload.get("question", run.question)),
                run_id=str(run.id),
                scope=scope,
                intended_use=intended_use,
                source_ids=source_ids,
                max_results_per_step=3,
                max_steps=4,
            )
            source_policy = self.policy_service.repository.get_active_source_policy_version(session)
            tool_policy = self.policy_service.repository.get_active_research_tool_policy_version(session)
            if source_policy is not None and tool_policy is not None:
                plan = _replace(
                    plan,
                    policy_version=f"{source_policy.policy_hash}:{tool_policy.policy_hash}",
                )
            self.repository.save_plan(session, run=run, plan=plan)
            self.repository.append_event(
                session,
                run=run,
                event_type="research_plan_persisted",
                safe_message="Search plan persisted before transport.",
                details={"plan_id": plan.plan_id, "step_count": len(plan.steps)},
            )

        self._set_run_status(session, run, "searching", current_step="searching")
        self.repository.append_event(
            session,
            run=run,
            event_type="research_searching",
            safe_message="Executing approved research tool calls.",
            details={"plan_id": plan.plan_id},
        )

        audit_sink = PostgresToolCallAuditSink(self.repository, session, run)
        replay_store = PostgresReplayStore(self.repository, session, run)
        lookup = partial(
            lookup_completed_tool_call,
            self.repository,
            session,
            research_run_id=run.id,
        )
        runtime = GovernedResearchMCP(
            tool_registry=tool_registry,
            source_registry=source_registry,
            audit_sink=audit_sink,
            replay_store=replay_store,
            is_cancelled=lambda: self._is_cancelled(session, job, run),
            lookup_completed=lookup,
        )
        connectors = build_research_connectors(source_ids=source_ids)

        try:
            execution = runtime.execute_plan(plan, connectors)
        except ResearchRunCancelled:
            self._mark_cancelled(session, run)
            return ResearchExecutionResult(
                outcome="complete",
                result={"status": "cancelled", "research_run_id": str(run.id)},
            )
        except PermissionError as exc:
            self._set_run_status(session, run, "blocked", current_step="authorization")
            self.repository.append_event(
                session,
                run=run,
                event_type="research_source_blocked",
                safe_message="Research source approval blocked transport.",
                details={"message": str(exc)},
            )
            return ResearchExecutionResult(
                outcome="terminal_failure",
                error_code="source_not_approved",
            )
        except Exception as exc:
            self._set_run_status(session, run, "failed", current_step="searching")
            self.repository.append_event(
                session,
                run=run,
                event_type="research_source_failed",
                safe_message="Research execution failed before completion.",
                details={"message": str(exc)},
            )
            return ResearchExecutionResult(
                outcome="retry" if _is_retryable(exc) else "terminal_failure",
                error_code=type(exc).__name__,
                retryable=_is_retryable(exc),
            )

        document_count = sum(result.document_count for result in execution.results)
        for result in execution.results:
            self.repository.append_event(
                session,
                run=run,
                event_type="research_source_completed",
                safe_message=f"Source {result.source} returned normalized documents.",
                details={
                    "source": result.source,
                    "document_count": result.document_count,
                },
            )

        self._set_run_status(session, run, "completed", current_step="completed")
        run.completed_at = datetime.now(tz=UTC)
        self.repository.append_event(
            session,
            run=run,
            event_type="research_search_completed",
            safe_message="Research search completed.",
            details={
                "plan_id": plan.plan_id,
                "document_count": document_count,
                "tool_call_count": len(execution.audit_records),
            },
        )
        session.flush()
        return ResearchExecutionResult(
            outcome="complete",
            result={
                "status": "completed",
                "research_run_id": str(run.id),
                "plan_id": plan.plan_id,
                "document_count": document_count,
                "tool_call_count": len(execution.audit_records),
            },
        )

    def _simulate(self, payload: dict[str, object]) -> ResearchExecutionResult:
        simulate = payload.get("simulate")
        if simulate == "retry":
            return ResearchExecutionResult(outcome="retry", error_code="transient", retryable=True)
        if simulate == "fail":
            return ResearchExecutionResult(outcome="terminal_failure", error_code="policy_blocked")
        if simulate == "raise":
            raise RuntimeError("simulated handler crash")
        return ResearchExecutionResult(outcome="complete", result={"status": "processed"})

    def _is_cancelled(self, session: Session, job: JobRecord, run: ResearchRun) -> bool:
        if run.cancel_requested:
            return True
        current_job = session.scalar(select(Job).where(Job.id == job.id))
        return current_job is not None and current_job.status == "cancelled"

    def _mark_cancelled(self, session: Session, run: ResearchRun) -> None:
        self._set_run_status(session, run, "cancelled", current_step="cancelled")
        run.completed_at = datetime.now(tz=UTC)
        self.repository.append_event(
            session,
            run=run,
            event_type="research_search_cancelled",
            safe_message="Research search cancelled.",
        )

    def _set_run_status(
        self,
        session: Session,
        run: ResearchRun,
        status: str,
        *,
        current_step: str | None,
    ) -> None:
        run.status = status
        run.current_step = current_step
        if run.started_at is None and status not in {"queued"}:
            run.started_at = datetime.now(tz=UTC)
        session.flush()

    def _terminal_result(self, run: ResearchRun) -> dict[str, object]:
        return {
            "status": run.status,
            "research_run_id": str(run.id),
            "current_step": run.current_step,
        }


def _replace(plan, **changes):
    from dataclasses import replace

    return replace(plan, **changes)


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, (TimeoutError, ConnectionError))


@dataclass(frozen=True)
class ResearchRunHandler:
    executor: ResearchRunExecutor

    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        result = self.executor.execute(job, session=session, heartbeat=heartbeat)
        return HandlerResult(
            outcome=result.outcome,
            result=result.result,
            error_code=result.error_code,
            retryable=result.retryable,
        )
