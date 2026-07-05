import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.vyu.connectors import PubMedConnector, SearchRequest
from src.vyu.connectors.pubmed_live import PubMedHttpTransport, PubMedReplayTransport


class PubMedLiveConnectorTests(unittest.TestCase):
    def test_http_transport_maps_ncbi_esearch_and_esummary_json(self):
        requested = []

        def opener(url, timeout):
            requested.append((url, timeout))
            query = parse_qs(urlparse(url).query)
            if url.endswith("esearch.fcgi?" + urlparse(url).query):
                self.assertEqual(["json"], query["retmode"])
                self.assertEqual(["vyu-poc-test"], query["tool"])
                self.assertEqual(["dev@example.com"], query["email"])
                return json.dumps({"esearchresult": {"idlist": ["12345"]}}).encode("utf-8")
            return json.dumps(
                {
                    "result": {
                        "uids": ["12345"],
                        "12345": {
                            "uid": "12345",
                            "title": "Live-style VX-101 abstract",
                            "pubdate": "2026 Jan",
                            "source": "PubMed Test Journal",
                        },
                    }
                }
            ).encode("utf-8")

        transport = PubMedHttpTransport(
            tool="vyu-poc-test",
            email="dev@example.com",
            timeout_seconds=7.5,
            opener=opener,
        )

        search_payload = transport(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            {"mode": "search", "db": "pubmed", "term": "VX-101", "retmax": 1},
        )
        summary_payload = transport(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            {"mode": "summary", "db": "pubmed", "ids": "12345"},
        )

        self.assertEqual({"ids": ["12345"]}, search_payload)
        self.assertEqual("Live-style VX-101 abstract", summary_payload["documents"][0]["title"])
        self.assertEqual([7.5, 7.5], [timeout for _url, timeout in requested])

    def test_replay_transport_lets_pubmed_connector_run_without_network(self):
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
            result = connector.search(SearchRequest(query="VX-101", limit=1))

        self.assertEqual(["PUBMED-12345"], [document.document_id for document in result.documents])
        self.assertEqual("Replayed VX-101 record", result.documents[0].title)

    @unittest.skipUnless(
        os.environ.get("VYU_RUN_LIVE_PUBMED_TESTS") == "1",
        "Set VYU_RUN_LIVE_PUBMED_TESTS=1 to run live PubMed integration test.",
    )
    def test_live_pubmed_search_is_gated_by_environment(self):
        connector = PubMedConnector(
            transport=PubMedHttpTransport(
                tool=os.environ.get("VYU_NCBI_TOOL", "vyu-poc"),
                email=os.environ["VYU_NCBI_EMAIL"],
            )
        )

        result = connector.search(SearchRequest(query="migraine", limit=1))

        self.assertGreaterEqual(result.document_count, 1)


if __name__ == "__main__":
    unittest.main()
