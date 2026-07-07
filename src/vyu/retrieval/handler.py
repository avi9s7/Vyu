from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.vyu.jobs.contracts import HandlerResult, JobRecord
from src.vyu.retrieval.builder import IndexBuildExecutor, IndexBuildResult


@dataclass(frozen=True)
class IndexBuildHandler:
    executor: IndexBuildExecutor

    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        result = self.executor.execute(job, session=session, heartbeat=heartbeat)
        return _to_handler_result(result)


def _to_handler_result(result: IndexBuildResult) -> HandlerResult:
    return HandlerResult(
        outcome=result.outcome,
        result=result.result,
        error_code=result.error_code,
        retryable=result.retryable,
    )
