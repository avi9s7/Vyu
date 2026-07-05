from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.vyu.research_mcp.contracts import ResearchScope, ResearchToolDefinition
from src.vyu.sources import SourceRegistry


class ResearchToolRegistry:
    def __init__(self, tools: list[ResearchToolDefinition]):
        self._tools = {tool.tool_id: tool for tool in tools}
        if len(self._tools) != len(tools):
            raise ValueError("Research tool registry contains duplicate tool_id values.")

    def tool_ids(self) -> list[str]:
        return sorted(self._tools)

    def get(self, tool_id: str) -> ResearchToolDefinition:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"Unknown research tool: {tool_id}") from exc

    def require_approved(
        self,
        tool_id: str,
        source_registry: SourceRegistry,
        scope: ResearchScope,
        intended_use: str,
        action: str = "search",
    ) -> ResearchToolDefinition:
        tool = self.get(tool_id)
        if not tool.approved:
            raise PermissionError(f"Research tool {tool_id!r} is not approved.")
        if action not in tool.allowed_actions:
            raise PermissionError(f"Research tool {tool_id!r} does not allow action {action!r}.")
        if intended_use not in tool.allowed_uses:
            raise PermissionError(f"Research tool {tool_id!r} is not approved for use {intended_use!r}.")
        if not tool.allows_scope(scope):
            raise PermissionError(
                f"Research tool {tool_id!r} is not approved for tenant/workspace scope "
                f"tenant={scope.tenant_id!r}, workspace={scope.workspace_id!r}."
            )
        source_registry.require_approved(
            tool.source_id,
            intended_use=intended_use,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        return tool

    def approved_tools(
        self,
        source_registry: SourceRegistry,
        scope: ResearchScope,
        intended_use: str,
        action: str = "search",
        source_ids: set[str] | None = None,
    ) -> list[ResearchToolDefinition]:
        approved: list[ResearchToolDefinition] = []
        for tool_id in self.tool_ids():
            tool = self._tools[tool_id]
            if source_ids is not None and tool.source_id not in source_ids:
                continue
            try:
                approved.append(
                    self.require_approved(
                        tool_id,
                        source_registry=source_registry,
                        scope=scope,
                        intended_use=intended_use,
                        action=action,
                    )
                )
            except PermissionError:
                continue
        return approved

    def to_json(self) -> dict[str, Any]:
        return {"tools": [self._tools[tool_id].to_json() for tool_id in self.tool_ids()]}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ResearchToolRegistry":
        return cls([ResearchToolDefinition.from_json(tool) for tool in payload.get("tools", [])])

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "ResearchToolRegistry":
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
