import unittest

from src.vyu.research_mcp import (
    ResearchScope,
    ResearchSearchPlanner,
    ResearchToolDefinition,
    ResearchToolRegistry,
)
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class ResearchMcpPlannerTests(unittest.TestCase):
    def test_planner_decomposes_query_and_uses_only_approved_tools(self):
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
                ),
                ProductionSourceRecord(
                    source_id="semantic_scholar",
                    display_name="Semantic Scholar",
                    source_type="public_literature",
                    owner="Semantic Scholar",
                    license_or_terms="terms pending review",
                    allowed_uses=["literature_search"],
                    approval_status="draft",
                ),
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
                    max_results=3,
                ),
                ResearchToolDefinition(
                    tool_id="semantic_scholar.search",
                    display_name="Semantic Scholar Search",
                    source_id="semantic_scholar",
                    connector_name="semantic_scholar",
                    approved=True,
                    max_results=3,
                ),
            ]
        )
        planner = ResearchSearchPlanner(tool_registry=tool_registry, source_registry=source_registry)

        plan = planner.plan(
            "Does VX-101 reduce migraine days?",
            run_id="run-1",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
        )

        self.assertEqual({"pubmed.search"}, {step.tool_id for step in plan.steps})
        self.assertIn('"VX-101"', plan.decomposition.subqueries)
        self.assertTrue(plan.plan_id.startswith("plan-"))
        self.assertLessEqual(max(step.limit for step in plan.steps), 3)

    def test_planner_fails_closed_when_no_approved_tool_available(self):
        source_registry = SourceRegistry(
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
            ResearchSearchPlanner(tool_registry, source_registry).plan(
                "migraine prevention",
                run_id="run-1",
                scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            )


if __name__ == "__main__":
    unittest.main()
