from __future__ import annotations

import pytest

from scripts.import_source_policy import import_policies, preview_import
from src.vyu.db.session import build_engine, build_session_factory
from src.vyu.db.settings import DatabaseSettings
from src.vyu.policy.repository import PolicyRepository
from src.vyu.policy.service import PolicyService
from src.vyu.research_mcp.contracts import ResearchScope
from src.vyu.research_mcp.planner import ResearchSearchPlanner


@pytest.fixture
def policy_factory(postgres_urls: dict[str, str]):
    return build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )


def test_import_source_policy_dry_run_counts() -> None:
    counts = preview_import(
        source_registry_path=__import__("pathlib").Path("config/source_registry.example.json"),
        tool_registry_path=__import__("pathlib").Path("config/research_tool_registry.example.json"),
    )
    assert counts.sources >= 4
    assert counts.tools >= 5
    assert counts.approved_tools == 1
    assert len(counts.source_policy_hash) == 64


def test_import_source_policy_apply_and_gate_tools(policy_factory) -> None:
    counts = import_policies(
        source_registry_path=__import__("pathlib").Path("config/source_registry.example.json"),
        tool_registry_path=__import__("pathlib").Path("config/research_tool_registry.example.json"),
        actor_id="policy-test-actor",
        apply=True,
    )
    assert counts.approved_tools == 1

    service = PolicyService(PolicyRepository())
    with policy_factory.begin() as session:
        tools = service.approved_tools_for_planning(
            session,
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            intended_use="literature_search",
        )
        assert [tool.tool_id for tool in tools] == ["pubmed.search"]

        planner = ResearchSearchPlanner(
            tool_registry=service.build_tool_registry(session),
            source_registry=service.build_source_registry(session),
        )
        plan = planner.plan(
            "What is the efficacy of VX-101?",
            run_id="run-1",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            source_ids={"pubmed"},
        )
        assert plan.steps
        assert all(step.tool_id == "pubmed.search" for step in plan.steps)


def test_quarantined_tool_is_excluded_from_planning(policy_factory) -> None:
    import_policies(
        source_registry_path=__import__("pathlib").Path("config/source_registry.example.json"),
        tool_registry_path=__import__("pathlib").Path("config/research_tool_registry.example.json"),
        actor_id="policy-test-actor",
        apply=True,
    )
    repository = PolicyRepository()
    service = PolicyService(repository)
    with policy_factory.begin() as session:
        repository.quarantine_tool(
            session,
            tool_id="pubmed.search",
            actor_id="security-operator",
            reason="staging drill",
        )
        tools = service.approved_tools_for_planning(
            session,
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            intended_use="literature_search",
        )
        assert tools == []


def test_wrong_intended_use_is_blocked(policy_factory) -> None:
    import_policies(
        source_registry_path=__import__("pathlib").Path("config/source_registry.example.json"),
        tool_registry_path=__import__("pathlib").Path("config/research_tool_registry.example.json"),
        actor_id="policy-test-actor",
        apply=True,
    )
    service = PolicyService()
    with policy_factory.begin() as session:
        tools = service.approved_tools_for_planning(
            session,
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            intended_use="trial_search",
        )
        assert tools == []
