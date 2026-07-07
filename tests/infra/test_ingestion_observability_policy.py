from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_MODULE = ROOT / "infra" / "terraform" / "modules" / "observability"
INGESTION_RUNBOOK = ROOT / "docs" / "production" / "runbooks" / "ingestion.md"
REPROCESS_SCRIPT = ROOT / "scripts" / "reprocess_document.py"
METRICS_MODULE = ROOT / "src" / "vyu" / "ingestion" / "metrics.py"

REQUIRED_INGESTION_ALARMS = (
    "ingestion_malware_infected",
    "ingestion_phi_blocked",
    "ingestion_phi_unknown",
    "ingestion_scan_errors",
    "ingestion_parser_failures",
    "ingestion_ready_latency",
    "ingestion_quarantine_age",
)

REQUIRED_INGESTION_METRICS = (
    "IngestionUploads",
    "IngestionBytes",
    "IngestionScanLatencyMs",
    "IngestionScanErrors",
    "IngestionMalwareInfected",
    "IngestionPhiBlocked",
    "IngestionPhiUnknown",
    "IngestionParserFailures",
    "IngestionReadyLatencyMs",
    "IngestionDuplicates",
    "IngestionQuarantineAgeSeconds",
)


def test_ingestion_metrics_recorder_declares_required_signals() -> None:
    content = METRICS_MODULE.read_text(encoding="utf-8")
    for metric in REQUIRED_INGESTION_METRICS:
        assert metric in content


def test_observability_module_defines_ingestion_alarms_and_dashboard_widgets() -> None:
    alarms = (OBSERVABILITY_MODULE / "alarms.tf").read_text(encoding="utf-8")
    dashboards = (OBSERVABILITY_MODULE / "dashboards.tf").read_text(encoding="utf-8")
    locals_tf = (OBSERVABILITY_MODULE / "locals.tf").read_text(encoding="utf-8")

    for alarm in REQUIRED_INGESTION_ALARMS:
        assert f'"{alarm}"' in alarms
        assert "aws_cloudwatch_metric_alarm" in alarms

    for metric in REQUIRED_INGESTION_METRICS:
        assert metric in dashboards

    for widget in (
        "ingestion_uploads",
        "ingestion_scan_latency",
        "ingestion_malware_infected",
        "ingestion_phi_blocked",
        "ingestion_parser_failures",
        "ingestion_ready_latency",
        "ingestion_duplicates",
        "ingestion_quarantine_age",
    ):
        assert widget in locals_tf


def test_reprocess_document_script_contract() -> None:
    content = REPROCESS_SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "--environment",
        "--tenant-id",
        "--workspace-id",
        "--document-id",
        "--version-id",
        "--reason",
        "--actor",
        "--mode",
        "dry-run",
        "apply",
        "VYU_REPROCESS_BEARER_TOKEN",
        "Idempotency-Key",
        "/v1/evidence-documents/",
        "/reprocess",
    ):
        assert marker in content


def test_ingestion_runbook_covers_required_triage_topics() -> None:
    content = INGESTION_RUNBOOK.read_text(encoding="utf-8").lower()
    for topic in (
        "stuck upload",
        "checksum mismatch",
        "malware",
        "suspected phi",
        "parser",
        "duplicate",
        "wrong metadata",
        "quarantine retention",
        "security review",
        "reprocess",
        "retention-request",
        "deletion escalation",
        "ingestionreadylatencyms",
        "ingestionquarantineageseconds",
        "reprocess_document.py",
        "validate_ingestion_staging.py",
        "staging validation",
    ):
        assert topic in content
