import tempfile
import unittest
from pathlib import Path

from src.vyu.connectors import JsonlAuditSink, PubMedConnector, SearchRequest


class Phase2PubMedConnectorTests(unittest.TestCase):
    def test_pubmed_connector_maps_mocked_responses_to_vyu_contracts(self):
        calls = []

        def transport(url, params):
            calls.append((url, params))
            if params["mode"] == "search":
                return {"ids": ["12345"]}
            return {
                "documents": [
                    {
                        "uid": "12345",
                        "title": "Mock VX-101 PubMed abstract",
                        "pubdate": "2026 Jan",
                        "source": "Mock Journal",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            connector = PubMedConnector(
                transport=transport, audit_sink=JsonlAuditSink(audit_path)
            )
            result = connector.search(SearchRequest(query="VX-101 migraine", limit=1))
            events = JsonlAuditSink(audit_path).read_events()

        self.assertEqual(["PUBMED-12345"], [doc.document_id for doc in result.documents])
        self.assertEqual(2, len(calls))
        self.assertEqual("search", events[0]["action"])


if __name__ == "__main__":
    unittest.main()
