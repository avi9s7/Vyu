from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.vyu.jobs.contracts import HandlerResult, JobRecord
from src.vyu.synthesis.service import SynthesisExecutionResult, SynthesisExecutor


@dataclass(frozen=True)
class SynthesisHandler:
    executor: SynthesisExecutor

    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        result = self.executor.execute(job, session=session, heartbeat=heartbeat)
        return _to_handler_result(result)


def _to_handler_result(result: SynthesisExecutionResult) -> HandlerResult:
    return HandlerResult(
        outcome=result.outcome,
        result=result.result,
        error_code=result.error_code,
        retryable=result.retryable,
    )
