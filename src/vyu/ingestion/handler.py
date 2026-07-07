from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.vyu.ingestion.service import IngestionService
from src.vyu.jobs.contracts import JobRecord
from src.vyu.jobs.worker import HandlerResult


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
        return self.service.run_ingestion_verify(
            job=job,
            session=session,
            heartbeat=heartbeat,
        )
