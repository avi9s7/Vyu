import json
import tempfile
import unittest
from pathlib import Path

from src.vyu.connectors import PubMedConnector
from src.vyu.connectors.health import (
    ConnectorHealthStatus,
    ValidationStage,
    run_connector_health_check,
    validate_pubmed_connector_stage,
)
from src.vyu.connectors.pubmed_live import PubMedReplayTransport


class ConnectorHealthTests(unittest.TestCase):
    def test_health_check_records_success_latency_and_payload(self):
        times = iter([10.0, 10.125])

        record = run_connector_health_check(
            source_id="pubmed",
            connector_name="PubMed",
            operation=lambda: {"ids": ["12345"]},
            checked_at="2026-06-14T00:00:00Z",
            clock=lambda: next(times),
        )

        self.assertEqual(ConnectorHealthStatus.OK, record.status)
        self.assertEqual(125, record.latency_ms)
        self.assertEqual({"ids": ["12345"]}, record.details)
        self.assertEqual("", record.error)
        self.assertEqual("ok", record.to_json()["status"])

    def test_health_check_records_failure_without_raising(self):
        times = iter([10.0, 10.05])

        record = run_connector_health_check(
            source_id="pubmed",
            connector_name="PubMed",
            operation=lambda: (_ for _ in ()).throw(TimeoutError("connector timeout")),
            checked_at="2026-06-14T00:00:00Z",
            clock=lambda: next(times),
        )

        self.assertEqual(ConnectorHealthStatus.FAIL, record.status)
        self.assertEqual(50, record.latency_ms)
        self.assertEqual("connector timeout", record.error)
        self.assertEqual({}, record.details)

    def test_pubmed_replay_validation_records_pass_with_document_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "pubmed_replay.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "search": {"ids": ["12345"]},
                        "summary": {
                            "documents": [
                                {
                                    "uid": "12345",
                                    "title": "Replayed VX-101 record",
                                    "pubdate": "2026 Jan",
                                    "source": "Replay Journal",
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            connector = PubMedConnector(transport=PubMedReplayTransport(fixture_path))

            record = validate_pubmed_connector_stage(
                connector=connector,
                stage=ValidationStage.REPLAY,
                query="VX-101",
                limit=1,
                checked_at="2026-06-14T00:00:00Z",
                clock=lambda: 10.0,
            )

        self.assertEqual(ConnectorHealthStatus.OK, record.status)
        self.assertEqual(ValidationStage.REPLAY, record.stage)
        self.assertEqual("pubmed", record.source_id)
        self.assertEqual(1, record.document_count)
        self.assertEqual("VX-101", record.query)
        self.assertEqual("replay", record.to_json()["stage"])

    def test_pubmed_validation_records_failure_when_connector_errors(self):
        class FailingConnector:
            def search(self, _request):
                raise ConnectionError("pubmed unavailable")

        record = validate_pubmed_connector_stage(
            connector=FailingConnector(),
            stage=ValidationStage.LIVE,
            query="migraine",
            limit=1,
            checked_at="2026-06-14T00:00:00Z",
            clock=lambda: 10.0,
        )

        self.assertEqual(ConnectorHealthStatus.FAIL, record.status)
        self.assertEqual(ValidationStage.LIVE, record.stage)
        self.assertEqual(0, record.document_count)
        self.assertEqual("pubmed unavailable", record.error)


if __name__ == "__main__":
    unittest.main()
