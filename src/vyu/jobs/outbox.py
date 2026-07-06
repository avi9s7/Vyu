from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.jobs.models import OutboxEvent
from src.vyu.jobs.queue import QueueMessage, SqsQueue


def safe_publish_error(message: str, *, limit: int = 500) -> str:
    cleaned = " ".join(message.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


@dataclass(frozen=True)
class OutboxPublishResult:
    published: bool
    outbox_id: str | None = None
    sqs_message_id: str | None = None


@dataclass(frozen=True)
class OutboxPublisher:
    queue: SqsQueue

    def publish_next(self, session: Session) -> OutboxPublishResult:
        row = session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return OutboxPublishResult(published=False)
        try:
            message = QueueMessage.from_payload(dict(row.payload))
            sqs_message_id = self.queue.send(message)
            row.published_at = datetime.now(tz=UTC)
            row.last_error = None
            session.flush()
            return OutboxPublishResult(
                published=True,
                outbox_id=str(row.id),
                sqs_message_id=sqs_message_id,
            )
        except Exception as exc:
            row.attempt = row.attempt + 1
            row.last_error = safe_publish_error(str(exc))
            session.flush()
            return OutboxPublishResult(published=False, outbox_id=str(row.id))
