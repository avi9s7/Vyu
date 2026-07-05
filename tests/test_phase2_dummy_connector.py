import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.connectors import DummyConnector, JsonlAuditSink, SearchRequest
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase2DummyConnectorTests(unittest.TestCase):
    def test_dummy_connector_search_fetch_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            audit_path = root / "audit.jsonl"
            connector = DummyConnector(
                load_dummy_corpus(root), audit_sink=JsonlAuditSink(audit_path)
            )

            result = connector.search(SearchRequest(query="retracted", limit=3))
            fetched = connector.fetch(result.documents[0].document_id)
            events = JsonlAuditSink(audit_path).read_events()

        self.assertGreaterEqual(result.document_count, 1)
        self.assertEqual(result.documents[0].document_id, fetched.document_id)
        self.assertEqual(["search", "fetch"], [event["action"] for event in events])


if __name__ == "__main__":
    unittest.main()
