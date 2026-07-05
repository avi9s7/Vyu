import unittest

from src.vyu.connectors import PubMedConnector, SearchRequest
from src.vyu.connectors.source_gate import SourceApprovalTransport
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class ConnectorSourceGateTests(unittest.TestCase):
    def test_source_gate_blocks_unapproved_source_before_transport_call(self):
        calls = []
        registry = SourceRegistry(
            [
                ProductionSourceRecord(
                    source_id="pubmed",
                    display_name="PubMed",
                    source_type="public_literature",
                    owner="National Library of Medicine",
                    license_or_terms="NLM/NCBI usage terms",
                    allowed_uses=["literature_search"],
                    approval_status="draft",
                )
            ]
        )
        gated_transport = SourceApprovalTransport(
            source_id="pubmed",
            intended_use="literature_search",
            registry=registry,
            transport=lambda url, params: calls.append((url, params)) or {"ids": []},
        )
        connector = PubMedConnector(transport=gated_transport)

        with self.assertRaises(PermissionError):
            connector.search(SearchRequest(query="migraine", limit=1))

        self.assertEqual([], calls)

    def test_source_gate_blocks_approved_source_for_unapproved_use(self):
        registry = SourceRegistry(
            [
                ProductionSourceRecord(
                    source_id="pubmed",
                    display_name="PubMed",
                    source_type="public_literature",
                    owner="National Library of Medicine",
                    license_or_terms="NLM/NCBI usage terms",
                    allowed_uses=["citation_metadata"],
                    approval_status="approved",
                    approved_by="production-review-board",
                    approved_at="2026-06-13T00:00:00Z",
                )
            ]
        )
        gated_transport = SourceApprovalTransport(
            source_id="pubmed",
            intended_use="literature_search",
            registry=registry,
            transport=lambda _url, _params: {"ids": []},
        )
        connector = PubMedConnector(transport=gated_transport)

        with self.assertRaises(PermissionError):
            connector.search(SearchRequest(query="migraine", limit=1))

    def test_source_gate_allows_approved_source_for_allowed_use(self):
        def transport(_url, params):
            if params["mode"] == "search":
                return {"ids": ["12345"]}
            return {
                "documents": [
                    {
                        "uid": "12345",
                        "title": "Approved PubMed record",
                        "pubdate": "2026 Jan",
                        "source": "Approved Journal",
                    }
                ]
            }

        registry = SourceRegistry(
            [
                ProductionSourceRecord(
                    source_id="pubmed",
                    display_name="PubMed",
                    source_type="public_literature",
                    owner="National Library of Medicine",
                    license_or_terms="NLM/NCBI usage terms",
                    allowed_uses=["literature_search"],
                    approval_status="approved",
                    approved_by="production-review-board",
                    approved_at="2026-06-13T00:00:00Z",
                )
            ]
        )
        connector = PubMedConnector(
            transport=SourceApprovalTransport(
                source_id="pubmed",
                intended_use="literature_search",
                registry=registry,
                transport=transport,
            )
        )

        result = connector.search(SearchRequest(query="migraine", limit=1))

        self.assertEqual(["PUBMED-12345"], [document.document_id for document in result.documents])


if __name__ == "__main__":
    unittest.main()
