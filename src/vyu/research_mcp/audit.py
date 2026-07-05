from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.vyu.research_mcp.contracts import ToolCallAuditRecord, ToolCallReplayRecord
if TYPE_CHECKING:  # pragma: no cover - type checking only.
    from src.vyu.storage.production import ProductionScope, ProductionStorage


class JsonlToolCallAuditSink:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: ToolCallAuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_json(), sort_keys=True) + "\n")

    def read_records(self) -> list[ToolCallAuditRecord]:
        if not self.path.exists():
            return []
        records: list[ToolCallAuditRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(ToolCallAuditRecord.from_json(json.loads(line)))
        return records


class JsonlReplayStore:
    def __init__(self, path: Path):
        self.path = path

    def append(self, record: ToolCallReplayRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_json(), sort_keys=True) + "\n")

    def get(self, request_hash: str) -> ToolCallReplayRecord | None:
        if not self.path.exists():
            return None
        selected: ToolCallReplayRecord | None = None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = ToolCallReplayRecord.from_json(json.loads(line))
            if record.request_hash == request_hash:
                selected = record
        return selected

    def read_records(self) -> list[ToolCallReplayRecord]:
        if not self.path.exists():
            return []
        records: list[ToolCallReplayRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(ToolCallReplayRecord.from_json(json.loads(line)))
        return records


class ProductionToolCallAuditSink:
    """Persist Research MCP tool-call audit records to production storage.

    JSONL remains useful for local development and fixture review. This adapter is the
    production-operated path: records become tenant/workspace-scoped SQLite rows and
    production audit events, which means they are covered by backup/restore and scoped
    audit inspection.
    """

    def __init__(self, storage: ProductionStorage):
        self.storage = storage

    def append(self, record: ToolCallAuditRecord) -> None:
        self.storage.record_research_mcp_tool_call(record)

    def read_records(self, run_id: str | None = None) -> list[ToolCallAuditRecord]:
        return self.storage.list_research_mcp_tool_calls(run_id=run_id)

    def read_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ToolCallAuditRecord]:
        return self.storage.list_research_mcp_tool_calls_for_scope(scope, run_id=run_id)


class ProductionReplayStore:
    """Tenant/workspace-scoped replay store backed by production storage."""

    def __init__(self, storage: ProductionStorage, scope: ProductionScope):
        self.storage = storage
        self.scope = scope

    def append(self, record: ToolCallReplayRecord) -> None:
        self.storage.save_research_mcp_replay_record(record)

    def get(self, request_hash: str) -> ToolCallReplayRecord | None:
        return self.storage.get_research_mcp_replay_record(
            request_hash,
            scope=self.scope,
        )

    def read_records(self, run_id: str | None = None) -> list[ToolCallReplayRecord]:
        return self.storage.list_research_mcp_replay_records_for_scope(
            self.scope,
            run_id=run_id,
        )
