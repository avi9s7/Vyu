import tempfile
import unittest
from pathlib import Path

from src.vyu.connectors import ConnectorResult, SearchRequest
from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign
from src.vyu.research_mcp import (
    GovernedResearchMCP,
    JsonlReplayStore,
    JsonlToolCallAuditSink,
    ResearchScope,
    ResearchSearchPlanner,
    ResearchToolDefinition,
    ResearchToolRegistry,
)
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class StaticPubMedConnector:
    source = "pubmed"

    def __init__(self):
        self.calls = 0

    def search(self, request: SearchRequest) -> ConnectorResult:
        self.calls += 1
        document = DocumentRecord(
            document_id="PUBMED-123",
            title="VX-101 randomized migraine prevention trial",
            year=2026,
            study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL,
            source_type="pubmed",
            publication_status="peer_reviewed",
            abstract="VX-101 reduced monthly migraine days compared with standard therapy.",
            pmid="123",
        )
        passage = PassageRecord(
            passage_id="PUBMED-123-SUMMARY",
            document_id="PUBMED-123",
            section="summary",
            text=document.abstract,
        )
        return ConnectorResult(source=self.source, request=request, documents=[document], passages=[passage])

    def fetch(self, document_id: str) -> DocumentRecord:
        raise NotImplementedError


def build_registries():
    source_registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="pubmed",
                display_name="PubMed",
                source_type="public_literature",
                owner="National Library of Medicine",
                license_or_terms="NLM/NCBI usage terms",
                allowed_uses=["literature_search"],
                access_policy="all_approved_workspaces",
                approval_status="approved",
                approved_by="production-review-board",
                approved_at="2026-06-13T00:00:00Z",
            )
        ]
    )
    tool_registry = ResearchToolRegistry(
        [
            ResearchToolDefinition(
                tool_id="pubmed.search",
                display_name="PubMed Search",
                source_id="pubmed",
                connector_name="pubmed",
                approved=True,
                max_results=1,
            )
        ]
    )
    return source_registry, tool_registry


class ResearchMcpRuntimeTests(unittest.TestCase):
    def test_runtime_executes_approved_plan_and_writes_audit_and_replay_records(self):
        source_registry, tool_registry = build_registries()
        plan = ResearchSearchPlanner(tool_registry, source_registry).plan(
            "VX-101 migraine",
            run_id="run-1",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a", user_id="user-a"),
            max_steps=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "mcp_audit.jsonl"
            replay_path = Path(tmp) / "mcp_replay.jsonl"
            connector = StaticPubMedConnector()
            runtime = GovernedResearchMCP(
                tool_registry=tool_registry,
                source_registry=source_registry,
                audit_sink=JsonlToolCallAuditSink(audit_path),
                replay_store=JsonlReplayStore(replay_path),
            )

            execution = runtime.execute_plan(plan, connectors={"pubmed": connector})

            audit_records = JsonlToolCallAuditSink(audit_path).read_records()
            replay_records = JsonlReplayStore(replay_path).read_records()

        self.assertEqual(1, connector.calls)
        self.assertEqual(1, len(execution.results))
        self.assertEqual(1, len(audit_records))
        self.assertEqual(1, len(replay_records))
        self.assertEqual(audit_records[0].request_hash, replay_records[0].request_hash)
        self.assertEqual(audit_records[0].result_hash, replay_records[0].result_hash)
        self.assertEqual(("PUBMED-123",), audit_records[0].result_document_ids)
        self.assertFalse(audit_records[0].replayed)

    def test_runtime_replays_result_without_calling_connector(self):
        source_registry, tool_registry = build_registries()
        plan = ResearchSearchPlanner(tool_registry, source_registry).plan(
            "VX-101 migraine",
            run_id="run-1",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            max_steps=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            replay_store = JsonlReplayStore(Path(tmp) / "mcp_replay.jsonl")
            audit_sink = JsonlToolCallAuditSink(Path(tmp) / "mcp_audit.jsonl")
            connector = StaticPubMedConnector()
            runtime = GovernedResearchMCP(
                tool_registry=tool_registry,
                source_registry=source_registry,
                audit_sink=audit_sink,
                replay_store=replay_store,
            )
            runtime.execute_plan(plan, connectors={"pubmed": connector})

            replay_connector = StaticPubMedConnector()
            execution = runtime.execute_plan(
                plan,
                connectors={"pubmed": replay_connector},
                replay=True,
            )
            records = audit_sink.read_records()

        self.assertEqual(0, replay_connector.calls)
        self.assertEqual("PUBMED-123", execution.results[0].documents[0].document_id)
        self.assertTrue(records[-1].replayed)


if __name__ == "__main__":
    unittest.main()
