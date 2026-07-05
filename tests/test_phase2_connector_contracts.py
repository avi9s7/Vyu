import unittest

from src.vyu.connectors import ConnectorAuditEvent, ConnectorResult, SearchRequest


class Phase2ConnectorContractsTests(unittest.TestCase):
    def test_connector_result_tracks_source_and_document_counts(self):
        request = SearchRequest(query="VX-101 migraine", limit=5)
        result = ConnectorResult(source="dummy", request=request, documents=[], passages=[])

        self.assertEqual("dummy", result.source)
        self.assertEqual(0, result.document_count)

    def test_audit_event_serializes_core_fields(self):
        event = ConnectorAuditEvent(
            source="dummy",
            action="search",
            query="VX-101",
            document_ids=["DOC-001"],
            status="ok",
        )

        self.assertEqual("search", event.to_json()["action"])
        self.assertEqual(["DOC-001"], event.to_json()["document_ids"])


if __name__ == "__main__":
    unittest.main()
