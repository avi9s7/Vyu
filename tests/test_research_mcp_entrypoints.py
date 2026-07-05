import tempfile
import unittest
from pathlib import Path

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.connectors import ConnectorResult, SearchRequest
from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign
from src.vyu.entrypoints.research_mcp import (
    ResearchMcpExecuteApiRequest,
    ResearchMcpExecutePayload,
    ResearchMcpExecuteWorkerJob,
    handle_research_mcp_execute_api,
    run_research_mcp_execute_worker_job,
)
from src.vyu.research_mcp import ResearchToolDefinition, ResearchToolRegistry
from src.vyu.sources import ProductionSourceRecord, SourceRegistry
from src.vyu.storage import ProductionScope, ProductionStorage


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


class ResearchMcpEntrypointTests(unittest.TestCase):
    def test_api_executes_authorized_research_mcp_and_persists_operational_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            connector = StaticPubMedConnector()
            response = handle_research_mcp_execute_api(
                ResearchMcpExecuteApiRequest(
                    request_id="request-1",
                    payload=ResearchMcpExecutePayload(
                        principal=_researcher(),
                        run_id="run-001",
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                        question="Does VX-101 reduce migraine days?",
                        max_steps=1,
                    ),
                ),
                storage=storage,
                source_registry=_source_registry(),
                tool_registry=_tool_registry(),
                connectors={"pubmed": connector},
                created_at="2026-06-18T00:00:00Z",
            )
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            plans = storage.list_research_mcp_plans_for_scope(scope, run_id="run-001")
            calls = storage.list_research_mcp_tool_calls_for_scope(scope, run_id="run-001")
            replay_records = storage.list_research_mcp_replay_records_for_scope(scope, run_id="run-001")

        self.assertEqual(200, response.status_code)
        self.assertEqual("completed", response.body["status"])
        self.assertEqual(["PUBMED-123"], response.body["result_document_ids"])
        self.assertEqual(1, connector.calls)
        self.assertEqual(1, len(plans))
        self.assertEqual(1, len(calls))
        self.assertEqual(1, len(replay_records))
        self.assertEqual("ok", calls[0].status)

    def test_api_blocks_unauthorized_principal_before_research_tools_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            connector = StaticPubMedConnector()
            response = handle_research_mcp_execute_api(
                ResearchMcpExecuteApiRequest(
                    request_id="request-1",
                    payload=ResearchMcpExecutePayload(
                        principal=Principal(user_id="outsider", memberships=()),
                        run_id="run-001",
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                        question="Does VX-101 reduce migraine days?",
                    ),
                ),
                storage=storage,
                source_registry=_source_registry(),
                tool_registry=_tool_registry(),
                connectors={"pubmed": connector},
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual("blocked", response.body["status"])
        self.assertEqual(0, connector.calls)

    def test_worker_replay_uses_persisted_result_without_calling_connector(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            payload = ResearchMcpExecutePayload(
                principal=_researcher(),
                run_id="run-001",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                question="Does VX-101 reduce migraine days?",
                max_steps=1,
            )
            run_research_mcp_execute_worker_job(
                ResearchMcpExecuteWorkerJob(job_id="job-1", payload=payload),
                storage=storage,
                source_registry=_source_registry(),
                tool_registry=_tool_registry(),
                connectors={"pubmed": StaticPubMedConnector()},
            )
            replay_connector = StaticPubMedConnector()
            replay_result = run_research_mcp_execute_worker_job(
                ResearchMcpExecuteWorkerJob(
                    job_id="job-2",
                    payload=ResearchMcpExecutePayload(
                        principal=_researcher(),
                        run_id="run-001",
                        tenant_id="tenant-a",
                        workspace_id="workspace-a",
                        question="Does VX-101 reduce migraine days?",
                        max_steps=1,
                        replay=True,
                    ),
                ),
                storage=storage,
                source_registry=_source_registry(),
                tool_registry=_tool_registry(),
                connectors={"pubmed": replay_connector},
            )

        self.assertEqual("completed", replay_result.status)
        self.assertEqual(0, replay_connector.calls)
        self.assertEqual(["PUBMED-123"], replay_result.body["result_document_ids"])


def _researcher() -> Principal:
    return Principal(
        user_id="researcher-1",
        memberships=(
            WorkspaceMembership(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(Role.RESEARCHER,),
            ),
        ),
    )


def _source_registry() -> SourceRegistry:
    return SourceRegistry(
        [
            ProductionSourceRecord(
                source_id="pubmed",
                display_name="PubMed",
                source_type="public_literature",
                owner="National Library of Medicine",
                license_or_terms="NLM/NCBI usage terms",
                allowed_uses=["literature_search"],
                access_policy="tenant:tenant-a:workspace:workspace-a",
                approval_status="approved",
                approved_by="production-review-board",
                approved_at="2026-06-13T00:00:00Z",
            )
        ]
    )


def _tool_registry() -> ResearchToolRegistry:
    return ResearchToolRegistry(
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


if __name__ == "__main__":
    unittest.main()
