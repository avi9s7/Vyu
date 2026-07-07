from collections.abc import Callable
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.vyu.config import RuntimeSettings
from src.vyu.connectors import SearchRequest
from src.vyu.connectors.health import ConnectorHealthStatus, ValidationStage
from src.vyu.connectors.metrics import ConnectorMetricsRecorder
from src.vyu.connectors.pubmed.adapter import ProductionPubMedConnector
from src.vyu.connectors.pubmed.normalization import NORMALIZATION_SCHEMA_VERSION
from src.vyu.connectors.pubmed_live import PubMedHttpTransport, PubMedReplayTransport


PROBE_QUERY = "aspirin"
PROBE_LIMIT = 3
PROBE_SCHEMA_VERSION = "pubmed-probe-v1"


@dataclass(frozen=True)
class PubMedStagingProbeResult:
    stage: ValidationStage
    status: ConnectorHealthStatus
    checked_at: str
    query: str
    limit: int
    document_count: int
    latency_ms: int
    schema_version: str
    normalization_schema: str
    freshness_timestamp: str
    record_hashes: tuple[str, ...]
    error: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "query": self.query,
            "limit": self.limit,
            "document_count": self.document_count,
            "latency_ms": self.latency_ms,
            "schema_version": self.schema_version,
            "normalization_schema": self.normalization_schema,
            "freshness_timestamp": self.freshness_timestamp,
            "record_hashes": list(self.record_hashes),
            "error": self.error,
        }


class PubMedStagingProbe:
    def __init__(
        self,
        connector: ProductionPubMedConnector,
        *,
        metrics: ConnectorMetricsRecorder | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.connector = connector
        self.metrics = metrics or ConnectorMetricsRecorder()
        self.clock = clock

    def run(
        self,
        *,
        stage: ValidationStage,
        query: str = PROBE_QUERY,
        limit: int = PROBE_LIMIT,
        checked_at: str | None = None,
    ) -> PubMedStagingProbeResult:
        checked = checked_at or datetime.now(timezone.utc).isoformat()
        started = self.clock()
        document_count = 0
        record_hashes: tuple[str, ...] = ()
        freshness = checked
        try:
            result = self.connector.search(SearchRequest(query=query, limit=limit))
            document_count = result.document_count
            if document_count <= 0:
                raise RuntimeError("PubMed probe returned zero normalized documents.")
            records = self.connector.fetch_records(
                [document.pmid for document in result.documents if document.pmid]
            )
            record_hashes = tuple(record.normalized_record_hash for record in records)
            freshness = max((record.source_timestamp for record in records), default=checked)
            status = ConnectorHealthStatus.OK
            error = ""
            self.metrics.record_pubmed_probe_success(document_count=document_count)
        except Exception as exc:  # noqa: BLE001 - probe must capture failures
            status = ConnectorHealthStatus.FAIL
            error = str(exc)
            self.metrics.record_connector_failure("pubmed")
            self.metrics.record_pubmed_probe_failure()
        latency_ms = round((self.clock() - started) * 1000)
        self.metrics.record_pubmed_probe_latency_ms(latency_ms)
        return PubMedStagingProbeResult(
            stage=stage,
            status=status,
            checked_at=checked,
            query=query,
            limit=limit,
            document_count=document_count,
            latency_ms=latency_ms,
            schema_version=PROBE_SCHEMA_VERSION,
            normalization_schema=NORMALIZATION_SCHEMA_VERSION,
            freshness_timestamp=freshness,
            record_hashes=record_hashes,
            error=error,
        )


def build_probe_connector(
    *,
    stage: ValidationStage,
    settings: RuntimeSettings | None = None,
    fixture_path: Path | None = None,
) -> ProductionPubMedConnector:
    runtime_settings = settings or RuntimeSettings.from_environment()
    if stage == ValidationStage.REPLAY:
        path = fixture_path or Path("tests/fixtures/connectors/pubmed/replay.json")
        return ProductionPubMedConnector(transport=PubMedReplayTransport(path))
    return ProductionPubMedConnector(
        transport=PubMedHttpTransport(
            tool=runtime_settings.ncbi_tool,
            email=runtime_settings.ncbi_email,
            api_key=runtime_settings.ncbi_api_key,
            timeout_seconds=runtime_settings.connector_timeout_seconds,
        )
    )
