import tempfile
import unittest
from pathlib import Path

from src.vyu.research_mcp import ResearchScope, ResearchToolDefinition, ResearchToolRegistry
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


def approved_source(source_id="pubmed", access_policy="tenant:tenant-a:workspace:workspace-a"):
    return ProductionSourceRecord(
        source_id=source_id,
        display_name="PubMed",
        source_type="public_literature",
        owner="National Library of Medicine",
        license_or_terms="NLM/NCBI usage terms",
        allowed_uses=["literature_search"],
        access_policy=access_policy,
        approval_status="approved",
        approved_by="production-review-board",
        approved_at="2026-06-13T00:00:00Z",
    )


class ResearchMcpRegistryTests(unittest.TestCase):
    def test_tool_registry_requires_tool_source_and_scope_approval(self):
        source_registry = SourceRegistry([approved_source()])
        tool_registry = ResearchToolRegistry(
            [
                ResearchToolDefinition(
                    tool_id="pubmed.search",
                    display_name="PubMed Search",
                    source_id="pubmed",
                    connector_name="pubmed",
                    approved=True,
                )
            ]
        )

        tool = tool_registry.require_approved(
            "pubmed.search",
            source_registry=source_registry,
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a", user_id="user-a"),
            intended_use="literature_search",
        )

        self.assertEqual("pubmed", tool.source_id)

    def test_tool_registry_blocks_scope_that_source_does_not_allow(self):
        source_registry = SourceRegistry([approved_source()])
        tool_registry = ResearchToolRegistry(
            [
                ResearchToolDefinition(
                    tool_id="pubmed.search",
                    display_name="PubMed Search",
                    source_id="pubmed",
                    connector_name="pubmed",
                    approved=True,
                )
            ]
        )

        with self.assertRaises(PermissionError):
            tool_registry.require_approved(
                "pubmed.search",
                source_registry=source_registry,
                scope=ResearchScope(tenant_id="tenant-b", workspace_id="workspace-b"),
                intended_use="literature_search",
            )

    def test_tool_registry_blocks_unapproved_tool_even_when_source_is_approved(self):
        source_registry = SourceRegistry([approved_source(access_policy="all_approved_workspaces")])
        tool_registry = ResearchToolRegistry(
            [
                ResearchToolDefinition(
                    tool_id="pubmed.search",
                    display_name="PubMed Search",
                    source_id="pubmed",
                    connector_name="pubmed",
                    approved=False,
                )
            ]
        )

        with self.assertRaises(PermissionError):
            tool_registry.require_approved(
                "pubmed.search",
                source_registry=source_registry,
                scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                intended_use="literature_search",
            )

    def test_tool_registry_round_trips_json(self):
        registry = ResearchToolRegistry(
            [
                ResearchToolDefinition(
                    tool_id="pubmed.search",
                    display_name="PubMed Search",
                    source_id="pubmed",
                    connector_name="pubmed",
                    approved=True,
                    capabilities=("search", "citation_metadata"),
                    max_results=25,
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_tools.json"
            registry.write(path)
            loaded = ResearchToolRegistry.read(path)

        self.assertEqual(registry.to_json(), loaded.to_json())


if __name__ == "__main__":
    unittest.main()
