from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from src.vyu.contracts import DocumentRecord, PassageRecord


@dataclass(frozen=True)
class SearchRequest:
    query: str
    limit: int = 10
    filters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorResult:
    source: str
    request: SearchRequest
    documents: list[DocumentRecord]
    passages: list[PassageRecord]

    @property
    def document_count(self) -> int:
        return len(self.documents)


@dataclass(frozen=True)
class ConnectorAuditEvent:
    source: str
    action: str
    query: str | None
    document_ids: list[str]
    status: str
    message: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "action": self.action,
            "query": self.query,
            "document_ids": self.document_ids,
            "status": self.status,
            "message": self.message,
            "created_at": self.created_at,
        }


class SourceConnector(Protocol):
    source: str

    def search(self, request: SearchRequest) -> ConnectorResult:
        ...

    def fetch(self, document_id: str) -> DocumentRecord:
        ...
