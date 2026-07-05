from __future__ import annotations

import re

from src.vyu.research_mcp.contracts import (
    QueryDecomposition,
    ResearchScope,
    SearchPlan,
    SearchPlanStep,
)
from src.vyu.research_mcp.hashing import short_hash
from src.vyu.research_mcp.registry import ResearchToolRegistry
from src.vyu.sources import SourceRegistry


class ResearchQueryDecomposer:
    def decompose(self, question: str) -> QueryDecomposition:
        normalized = " ".join(question.split())
        if not normalized:
            raise ValueError("Research question cannot be empty.")

        acronyms = tuple(dict.fromkeys(re.findall(r"\b[A-Z][A-Z0-9-]{1,}\b", normalized)))
        subqueries: list[str] = [normalized]
        for acronym in acronyms:
            exact_query = f'"{acronym}"'
            if exact_query not in subqueries:
                subqueries.append(exact_query)

        lower = normalized.lower()
        if "clinical trial" not in lower and any(token in lower for token in ("trial", "phase", "recruiting")):
            subqueries.append(f"{normalized} clinical trial")
        if "guideline" not in lower and any(token in lower for token in ("guideline", "recommendation", "consensus")):
            subqueries.append(f"{normalized} guideline")

        return QueryDecomposition(
            original_question=normalized,
            subqueries=tuple(dict.fromkeys(subqueries)),
            detected_acronyms=acronyms,
        )


class ResearchSearchPlanner:
    def __init__(
        self,
        tool_registry: ResearchToolRegistry,
        source_registry: SourceRegistry,
        decomposer: ResearchQueryDecomposer | None = None,
    ):
        self.tool_registry = tool_registry
        self.source_registry = source_registry
        self.decomposer = decomposer or ResearchQueryDecomposer()

    def plan(
        self,
        question: str,
        run_id: str,
        scope: ResearchScope,
        intended_use: str = "literature_search",
        source_ids: set[str] | None = None,
        max_results_per_step: int = 5,
        max_steps: int = 8,
    ) -> SearchPlan:
        decomposition = self.decomposer.decompose(question)
        tools = self.tool_registry.approved_tools(
            self.source_registry,
            scope=scope,
            intended_use=intended_use,
            action="search",
            source_ids=source_ids,
        )
        if not tools:
            raise PermissionError("No approved research tools are available for this scope and intended use.")

        steps: list[SearchPlanStep] = []
        for query_index, query in enumerate(decomposition.subqueries):
            for tool in tools:
                if "search" not in tool.capabilities:
                    continue
                step_number = len(steps) + 1
                step_payload = {
                    "run_id": run_id,
                    "scope": scope.to_json(),
                    "tool_id": tool.tool_id,
                    "query": query,
                    "index": query_index,
                }
                steps.append(
                    SearchPlanStep(
                        step_id=f"step-{step_number:02d}-{short_hash(step_payload, 8)}",
                        tool_id=tool.tool_id,
                        source_id=tool.source_id,
                        connector_name=tool.connector_name,
                        action="search",
                        query=query,
                        limit=max(1, min(max_results_per_step, tool.max_results)),
                        filters={"intended_use": intended_use},
                        reason="approved_tool_and_source_for_decomposed_query",
                    )
                )
                if len(steps) >= max_steps:
                    break
            if len(steps) >= max_steps:
                break

        if not steps:
            raise PermissionError("Approved research tools exist, but none expose the required search capability.")

        plan_payload = {
            "run_id": run_id,
            "scope": scope.to_json(),
            "intended_use": intended_use,
            "question": decomposition.original_question,
            "steps": [step.to_json() for step in steps],
        }
        return SearchPlan(
            plan_id=f"plan-{short_hash(plan_payload, 12)}",
            run_id=run_id,
            scope=scope,
            intended_use=intended_use,
            question=decomposition.original_question,
            decomposition=decomposition,
            steps=tuple(steps),
        )
