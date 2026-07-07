from __future__ import annotations

from typing import Protocol

from src.vyu.research_mcp.contracts import ToolCallAuditRecord, ToolCallReplayRecord


class ToolCallAuditSink(Protocol):
    def append(self, record: ToolCallAuditRecord) -> None:
        ...


class ReplayStore(Protocol):
    def append(self, record: ToolCallReplayRecord) -> None:
        ...

    def get(self, request_hash: str) -> ToolCallReplayRecord | None:
        ...
