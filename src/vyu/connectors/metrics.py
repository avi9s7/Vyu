from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectorMetricsRecorder:
    """Records connector counters and histograms through OpenTelemetry."""

    meter_name: str = "vyu.connectors"
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

    def record_connector_failure(self, source: str) -> None:
        self._counter("ConnectorFailures").add(1, attributes={"source": source})

    def record_pubmed_probe_success(self, *, document_count: int) -> None:
        self._counter("PubMedProbeSuccess").add(1, attributes={"document_count": document_count})

    def record_pubmed_probe_failure(self) -> None:
        self._counter("PubMedProbeFailures").add(1)

    def record_pubmed_probe_latency_ms(self, duration_ms: float) -> None:
        self._histogram("PubMedProbeLatencyMs").record(duration_ms)

    @staticmethod
    def elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000
