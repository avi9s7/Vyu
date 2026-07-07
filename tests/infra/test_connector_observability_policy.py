from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_MODULE = ROOT / "infra" / "terraform" / "modules" / "observability"
METRICS_MODULE = ROOT / "src" / "vyu" / "connectors" / "metrics.py"
PROBE_SCRIPT = ROOT / "scripts" / "probe_pubmed_staging.py"
RUNBOOK = ROOT / "docs" / "production" / "connector-health-validation.md"

REQUIRED_CONNECTOR_METRICS = (
    "ConnectorFailures",
    "PubMedProbeSuccess",
    "PubMedProbeFailures",
    "PubMedProbeLatencyMs",
)

REQUIRED_CONNECTOR_ALARMS = (
    "connector_failures",
    "pubmed_probe_failures",
)


def test_connector_metrics_recorder_declares_required_signals() -> None:
    content = METRICS_MODULE.read_text(encoding="utf-8")
    for metric in REQUIRED_CONNECTOR_METRICS:
        assert metric in content


def test_observability_module_defines_pubmed_probe_alarm_and_dashboard_widgets() -> None:
    alarms = (OBSERVABILITY_MODULE / "alarms.tf").read_text(encoding="utf-8")
    dashboards = (OBSERVABILITY_MODULE / "dashboards.tf").read_text(encoding="utf-8")
    locals_tf = (OBSERVABILITY_MODULE / "locals.tf").read_text(encoding="utf-8")

    for alarm in REQUIRED_CONNECTOR_ALARMS:
        assert f'"{alarm}"' in alarms

    for metric in ("PubMedProbeFailures", "PubMedProbeLatencyMs"):
        assert metric in dashboards

    for widget in ("pubmed_probe_failures", "pubmed_probe_latency"):
        assert widget in locals_tf


def test_probe_script_and_runbook_document_staging_probe() -> None:
    script = PROBE_SCRIPT.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "VYU_RUN_LIVE_PUBMED_PROBE" in script
    assert "PubMed" in runbook
