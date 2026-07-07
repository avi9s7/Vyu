from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalMetricsRecorder:
    """Records retrieval index and embedding counters through OpenTelemetry."""

    meter_name: str = "vyu.retrieval"
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

    def record_index_build_started(self, *, use_case: str) -> None:
        self._counter("RetrievalIndexBuildStarted").add(1, attributes={"use_case": use_case})

    def record_index_activation(self, *, use_case: str) -> None:
        self._counter("RetrievalIndexActivated").add(1, attributes={"use_case": use_case})

    def record_index_failure(self, *, use_case: str) -> None:
        self._counter("RetrievalIndexFailed").add(1, attributes={"use_case": use_case})

    def record_embedding_batch(self, *, provider: str, batch_size: int, latency_ms: float) -> None:
        self._counter("EmbeddingBatches").add(1, attributes={"provider": provider})
        self._histogram("EmbeddingBatchLatencyMs").record(
            latency_ms,
            attributes={"provider": provider, "batch_size": batch_size},
        )

    @staticmethod
    def elapsed_ms(started: float) -> float:
        return (time.perf_counter() - started) * 1000
