from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class IngestionMetricsRecorder:
    """Records ingestion counters and histograms through OpenTelemetry."""

    meter_name: str = "vyu.ingestion"
    _instruments: dict[str, object] = field(default_factory=dict, init=False, repr=False)

    def _counter(self, name: str) -> Any:
        instrument = self._instruments.get(name)
        if instrument is not None:
            return instrument
        from opentelemetry import metrics

        instrument = metrics.get_meter(self.meter_name).create_counter(name)
        self._instruments[name] = instrument
        return instrument

    def _histogram(self, name: str) -> Any:
        instrument = self._instruments.get(name)
        if instrument is not None:
            return instrument
        from opentelemetry import metrics

        instrument = metrics.get_meter(self.meter_name).create_histogram(name)
        self._instruments[name] = instrument
        return instrument

    def record_upload(self) -> None:
        self._counter("IngestionUploads").add(1)

    def record_upload_bytes(self, size_bytes: int) -> None:
        if size_bytes > 0:
            self._counter("IngestionBytes").add(size_bytes)

    def record_scan_latency_ms(self, duration_ms: float) -> None:
        self._histogram("IngestionScanLatencyMs").record(duration_ms)

    def record_scan_error(self) -> None:
        self._counter("IngestionScanErrors").add(1)

    def record_malware_infected(self) -> None:
        self._counter("IngestionMalwareInfected").add(1)

    def record_phi_blocked(self) -> None:
        self._counter("IngestionPhiBlocked").add(1)

    def record_phi_unknown(self) -> None:
        self._counter("IngestionPhiUnknown").add(1)

    def record_parser_failure(self, *, media_type: str) -> None:
        self._counter("IngestionParserFailures").add(
            1,
            attributes={"media_type": media_type or "unknown"},
        )

    def record_ready_latency_ms(self, duration_ms: float) -> None:
        self._histogram("IngestionReadyLatencyMs").record(duration_ms)

    def record_duplicate(self) -> None:
        self._counter("IngestionDuplicates").add(1)

    def record_quarantine_age_seconds(self, age_seconds: float) -> None:
        self._histogram("IngestionQuarantineAgeSeconds").record(age_seconds)

    @staticmethod
    def elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000

    @staticmethod
    def age_seconds_since(created_at: datetime) -> float:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(tz=UTC) - created_at).total_seconds())
