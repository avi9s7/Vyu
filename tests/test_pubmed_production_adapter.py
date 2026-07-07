from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.vyu.connectors import JsonlAuditSink, SearchRequest
from src.vyu.connectors.health import ConnectorHealthStatus, ValidationStage
from src.vyu.connectors.pubmed.adapter import ProductionPubMedConnector, PubMedRetractionBlockedError
from src.vyu.connectors.pubmed.contracts import RetractionPolicy
from src.vyu.connectors.pubmed.normalization import NORMALIZATION_SCHEMA_VERSION, parse_pubmed_xml
from src.vyu.connectors.pubmed.probe import PubMedStagingProbe
from src.vyu.connectors.pubmed_live import PubMedReplayTransport


FIXTURE_PATH = Path("tests/fixtures/connectors/pubmed/replay.json")

SAMPLE_XML = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">12345</PMID>
      <Article>
        <ArticleTitle>Aspirin trial</ArticleTitle>
        <Abstract>
          <AbstractText>Aspirin reduced headache frequency.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author>
        </AuthorList>
        <Language>eng</Language>
        <PublicationTypeList>
          <PublicationType>Journal Article</PublicationType>
        </PublicationTypeList>
      </Article>
      <MedlineJournalInfo><MedlineTA>Headache</MedlineTA></MedlineJournalInfo>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345</ArticleId>
        <ArticleId IdType="doi">10.1000/aspirin</ArticleId>
      </ArticleIdList>
      <PublicationStatus>ppublish</PublicationStatus>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".strip()


class PubMedNormalizationTests(unittest.TestCase):
    def test_parse_pubmed_xml_normalizes_metadata_and_hashes(self):
        records = parse_pubmed_xml(SAMPLE_XML, raw_body=SAMPLE_XML.encode("utf-8"))
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertEqual("12345", record.pmid)
        self.assertEqual("10.1000/aspirin", record.doi)
        self.assertEqual("Aspirin trial", record.title)
        self.assertIn("headache", record.abstract.lower())
        self.assertEqual("Headache", record.journal)
        self.assertEqual(("Jane Smith",), record.authors)
        self.assertFalse(record.is_retracted)
        self.assertTrue(record.metadata_only)
        self.assertTrue(record.raw_response_hash)
        self.assertTrue(record.normalized_record_hash)


class ProductionPubMedConnectorTests(unittest.TestCase):
    def test_search_uses_replay_fixture_and_excludes_retracted_records(self):
        connector = ProductionPubMedConnector(transport=PubMedReplayTransport(FIXTURE_PATH))
        result = connector.search(SearchRequest(query="aspirin", limit=2))
        self.assertEqual(["PUBMED-12345"], [document.document_id for document in result.documents])
        self.assertTrue(all(not document.is_retracted for document in result.documents))

    def test_fetch_blocks_retracted_record(self):
        connector = ProductionPubMedConnector(
            transport=PubMedReplayTransport(FIXTURE_PATH),
            retraction_policy=RetractionPolicy.BLOCK,
        )
        with self.assertRaises(PubMedRetractionBlockedError):
            connector.fetch("PUBMED-67890")

    def test_search_supports_pagination_filters(self):
        calls = []

        def transport(url, params):
            calls.append((url, params))
            if params["mode"] == "search":
                return {"ids": ["12345"], "count": 10, "retstart": 5}
            return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fetch"]

        connector = ProductionPubMedConnector(transport=transport)
        connector.search(
            SearchRequest(
                query="aspirin",
                limit=1,
                filters={"page_token": "5", "date_from": "2020/01/01", "date_to": "2024/12/31"},
            )
        )
        self.assertEqual(5, calls[0][1]["retstart"])
        self.assertEqual("2020/01/01", calls[0][1]["mindate"])
        self.assertEqual("2024/12/31", calls[0][1]["maxdate"])

    def test_search_audits_retraction_block_for_excluded_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            connector = ProductionPubMedConnector(
                transport=PubMedReplayTransport(FIXTURE_PATH),
                audit_sink=JsonlAuditSink(audit_path),
            )
            connector.search(SearchRequest(query="aspirin", limit=2))
            events = JsonlAuditSink(audit_path).read_events()
        actions = [event["action"] for event in events]
        self.assertIn("search", actions)
        self.assertIn("retraction_blocked", actions)


class PubMedStagingProbeTests(unittest.TestCase):
    def test_replay_probe_records_schema_and_hashes(self):
        connector = ProductionPubMedConnector(transport=PubMedReplayTransport(FIXTURE_PATH))
        result = PubMedStagingProbe(connector, clock=lambda: 10.0).run(
            stage=ValidationStage.REPLAY,
            query="aspirin",
            limit=1,
            checked_at="2026-07-07T00:00:00Z",
        )
        self.assertEqual(ConnectorHealthStatus.OK, result.status)
        self.assertEqual(ValidationStage.REPLAY, result.stage)
        self.assertEqual(1, result.document_count)
        self.assertEqual(NORMALIZATION_SCHEMA_VERSION, result.normalization_schema)
        self.assertEqual(1, len(result.record_hashes))


if __name__ == "__main__":
    unittest.main()
