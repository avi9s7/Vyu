from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from src.vyu.connectors.contracts import ConnectorAuditEvent


@dataclass(frozen=True)
class TransportAuditRecord:
    source: str
    action: str
    request_hash: str
    response_hash: str
    status_code: int | None
    result_count: int
    latency_ms: float
    attempts: int
    provider_request_id: str | None = None
    error_code: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "action": self.action,
            "request_hash": self.request_hash,
            "response_hash": self.response_hash,
            "status_code": self.status_code,
            "result_count": self.result_count,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "provider_request_id": self.provider_request_id,
            "error_code": self.error_code,
            "created_at": self.created_at,
        }


class JsonlAuditSink:
    def __init__(self, path: Path):
        self.path = path

    def append(self, event: ConnectorAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_json(), sort_keys=True) + "\n")

    def read_events(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class JsonlTransportAuditSink:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: TransportAuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_json(), sort_keys=True) + "\n")

    def read_records(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
