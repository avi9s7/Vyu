from __future__ import annotations

from sqlalchemy.orm import Session

from src.vyu.policy.repository import PolicyRepository
from src.vyu.research_mcp.contracts import ResearchScope, ResearchToolDefinition
from src.vyu.research_mcp.registry import ResearchToolRegistry
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class PolicyService:
    def __init__(self, repository: PolicyRepository | None = None) -> None:
        self.repository = repository or PolicyRepository()

    def build_source_registry(self, session: Session) -> SourceRegistry:
        version = self.repository.get_active_source_policy_version(session)
        if version is None:
            return SourceRegistry([])
        records = self.repository.list_sources_for_version(session, version.id)
        sources: list[ProductionSourceRecord] = []
        for row in records:
            if row.approval_status != "approved":
                continue
            sources.append(ProductionSourceRecord.from_json(dict(row.record_json)))
        return SourceRegistry(sources)

    def build_tool_registry(self, session: Session) -> ResearchToolRegistry:
        version = self.repository.get_active_research_tool_policy_version(session)
        if version is None:
            return ResearchToolRegistry([])
        records = self.repository.list_tools_for_version(session, version.id)
        tools: list[ResearchToolDefinition] = []
        for row in records:
            if row.approval_status != "approved":
                continue
            payload = dict(row.record_json)
            payload["approved"] = True
            tools.append(ResearchToolDefinition.from_json(payload))
        return ResearchToolRegistry(tools)

    def approved_tools_for_planning(
        self,
        session: Session,
        *,
        scope: ResearchScope,
        intended_use: str,
        source_ids: set[str] | None = None,
        action: str = "search",
    ) -> list[ResearchToolDefinition]:
        source_registry = self.build_source_registry(session)
        tool_registry = self.build_tool_registry(session)
        return tool_registry.approved_tools(
            source_registry,
            scope=scope,
            intended_use=intended_use,
            action=action,
            source_ids=source_ids,
        )
