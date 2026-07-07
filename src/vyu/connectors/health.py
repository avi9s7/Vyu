from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.vyu.connectors.contracts import SearchRequest
from src.vyu.connectors.pubmed.legacy import PubMedConnector


class ConnectorHealthStatus(StrEnum):
    OK = "ok"
    FAIL = "fail"


class ValidationStage(StrEnum):
    REPLAY = "replay"
    LIVE = "live"


@dataclass(frozen=True)
class ConnectorHealthRecord:
    source_id: str
    connector_name: str
    status: ConnectorHealthStatus
    checked_at: str
    latency_ms: int
    details: dict[str, Any]
    error: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "connector_name": self.connector_name,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "latency_ms": self.latency_ms,
            "details": dict(self.details),
            "error": self.error,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ConnectorHealthRecord":
        return cls(
            source_id=str(payload["source_id"]),
            connector_name=str(payload["connector_name"]),
            status=ConnectorHealthStatus(str(payload["status"])),
            checked_at=str(payload["checked_at"]),
            latency_ms=int(payload["latency_ms"]),
            details=dict(payload.get("details", {})),
            error=str(payload.get("error", "")),
        )


@dataclass(frozen=True)
class StagedConnectorValidationRecord:
    source_id: str
    connector_name: str
    stage: ValidationStage
    status: ConnectorHealthStatus
    checked_at: str
    query: str
    limit: int
    document_count: int
    latency_ms: int
    error: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "connector_name": self.connector_name,
            "stage": self.stage.value,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "query": self.query,
            "limit": self.limit,
            "document_count": self.document_count,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "StagedConnectorValidationRecord":
        return cls(
            source_id=str(payload["source_id"]),
            connector_name=str(payload["connector_name"]),
            stage=ValidationStage(str(payload["stage"])),
            status=ConnectorHealthStatus(str(payload["status"])),
            checked_at=str(payload["checked_at"]),
            query=str(payload["query"]),
            limit=int(payload["limit"]),
            document_count=int(payload["document_count"]),
            latency_ms=int(payload["latency_ms"]),
            error=str(payload.get("error", "")),
        )


def run_connector_health_check(
    source_id: str,
    connector_name: str,
    operation: Callable[[], dict[str, Any]],
    checked_at: str,
    clock: Callable[[], float] = time.monotonic,
) -> ConnectorHealthRecord:
    started = clock()
    try:
        details = operation()
        status = ConnectorHealthStatus.OK
        error = ""
    except Exception as exc:  # noqa: BLE001 - health checks must report failures.
        details = {}
        status = ConnectorHealthStatus.FAIL
        error = str(exc)
    latency_ms = round((clock() - started) * 1000)
    return ConnectorHealthRecord(
        source_id=source_id,
        connector_name=connector_name,
        status=status,
        checked_at=checked_at,
        latency_ms=latency_ms,
        details=details,
        error=error,
    )


def validate_pubmed_connector_stage(
    connector: PubMedConnector,
    stage: ValidationStage,
    query: str,
    limit: int,
    checked_at: str,
    clock: Callable[[], float] = time.monotonic,
) -> StagedConnectorValidationRecord:
    started = clock()
    try:
        result = connector.search(SearchRequest(query=query, limit=limit))
        status = ConnectorHealthStatus.OK
        document_count = result.document_count
        error = ""
    except Exception as exc:  # noqa: BLE001 - validation records must capture failures.
        status = ConnectorHealthStatus.FAIL
        document_count = 0
        error = str(exc)
    latency_ms = round((clock() - started) * 1000)
    return StagedConnectorValidationRecord(
        source_id="pubmed",
        connector_name="PubMed",
        stage=stage,
        status=status,
        checked_at=checked_at,
        query=query,
        limit=limit,
        document_count=document_count,
        latency_ms=latency_ms,
        error=error,
    )
