import unittest
from unittest.mock import Mock
from uuid import uuid4

from src.vyu.jobs.contracts import JobRecord
from src.vyu.research.executor import ResearchRunExecutor
from src.vyu.research_mcp import (
    GovernedResearchMCP,
    ResearchSearchPlanner,
    ResearchToolDefinition,
    ResearchToolRegistry,
)
from src.vyu.research_mcp.contracts import ResearchScope
from src.vyu.research_mcp.runtime import ResearchRunCancelled
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class StaticPubMedConnector:
    source = "pubmed"

    def __init__(self):
        self.calls = 0

    def search(self, request):
        from src.vyu.connectors import ConnectorResult, SearchRequest
        from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign

        del request
        self.calls += 1
        document = DocumentRecord(
            document_id="PUBMED-123",
            title="VX-101 trial",
            year=2026,
            study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL,
            source_type="pubmed",
            publication_status="peer_reviewed",
            abstract="VX-101 reduced migraine days.",
            pmid="123",
        )
        passage = PassageRecord(
            passage_id="PUBMED-123-ABSTRACT",
            document_id="PUBMED-123",
            section="abstract",
            text=document.abstract,
        )
        return ConnectorResult(
            source=self.source,
            request=SearchRequest(query="VX-101", limit=1),
            documents=[document],
            passages=[passage],
        )

    def fetch(self, document_id: str):
        raise NotImplementedError(document_id)


def build_registries():
    source_registry = SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="pubmed",
                display_name="PubMed",
                source_type="public_literature",
                owner="NLM",
                license_or_terms="NLM terms",
                allowed_uses=["literature_search"],
                access_policy="all_approved_workspaces",
                approval_status="approved",
                approved_by="board",
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


class GovernedResearchMcpWorkerIntegrationTests(unittest.TestCase):
    def test_runtime_honours_cancellation_before_transport(self):
        source_registry, tool_registry = build_registries()
        plan = ResearchSearchPlanner(tool_registry, source_registry).plan(
            "VX-101 migraine",
            run_id="run-1",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            max_steps=1,
        )
        runtime = GovernedResearchMCP(
            tool_registry=tool_registry,
            source_registry=source_registry,
            is_cancelled=lambda: True,
        )
        with self.assertRaises(ResearchRunCancelled):
            runtime.execute_plan(plan, connectors={"pubmed": StaticPubMedConnector()})


class ResearchRunExecutorUnitTests(unittest.TestCase):
    def test_simulate_payload_preserves_worker_stub_behaviour(self):
        executor = ResearchRunExecutor()
        job = JobRecord(
            id=uuid4(),
            tenant_id=uuid4(),
            workspace_id=uuid4(),
            kind="research.run",
            status="running",
            attempt=1,
            max_attempts=3,
            payload={"simulate": "retry"},
            result=None,
            error_code=None,
            available_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            leased_until=None,
            lease_owner="worker",
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            updated_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            started_at=None,
            completed_at=None,
        )
        result = executor.execute(job, session=Mock(), heartbeat=lambda: None)
        self.assertEqual("retry", result.outcome)
        self.assertTrue(result.retryable)


if __name__ == "__main__":
    unittest.main()
