from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.vyu.ingestion.metrics import IngestionMetricsRecorder


def test_metrics_recorder_records_without_error() -> None:
    recorder = IngestionMetricsRecorder()
    recorder.record_upload()
    recorder.record_upload_bytes(1024)
    recorder.record_scan_latency_ms(12.5)
    recorder.record_scan_error()
    recorder.record_malware_infected()
    recorder.record_phi_blocked()
    recorder.record_phi_unknown()
    recorder.record_parser_failure(media_type="application/pdf")
    recorder.record_ready_latency_ms(2500.0)
    recorder.record_duplicate()
    recorder.record_quarantine_age_seconds(3600.0)


def test_age_seconds_since_handles_naive_timestamps() -> None:
    created_at = datetime.now(tz=UTC) - timedelta(seconds=30)
    age = IngestionMetricsRecorder.age_seconds_since(created_at)
    assert 25 <= age <= 35
