from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.vyu.ingestion.service import IngestionService, IngestionVerifyResult
from src.vyu.jobs.contracts import HandlerResult, JobRecord


@dataclass(frozen=True)
class IngestionVerifyHandler:
    service: IngestionService

    def handle(
        self,
        job: JobRecord,
        *,
        session: Session,
        heartbeat: Callable[[], None],
    ) -> HandlerResult:
        verify_result = self.service.run_ingestion_verify(
            job=job,
            session=session,
            heartbeat=heartbeat,
        )
        return _to_handler_result(verify_result)


def _to_handler_result(result: IngestionVerifyResult) -> HandlerResult:
    return HandlerResult(
        outcome=result.outcome,
        result=result.result,
        error_code=result.error_code,
        retryable=result.retryable,
    )
