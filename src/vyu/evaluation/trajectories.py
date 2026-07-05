from __future__ import annotations

from dataclasses import dataclass

from src.vyu.workflow import DeepDiveResult


@dataclass(frozen=True)
class TrajectoryEvent:
    step: int
    action: str
    query: str
    retrieved_document_ids: list[str]
    coverage_gap: str | None
    observation: str

    def to_json(self) -> dict[str, object]:
        return {
            "step": self.step,
            "action": self.action,
            "query": self.query,
            "retrieved_document_ids": list(self.retrieved_document_ids),
            "coverage_gap": self.coverage_gap,
            "observation": self.observation,
        }


@dataclass(frozen=True)
class ResearchTrajectory:
    workflow: str
    question: str
    events: list[TrajectoryEvent]
    stopping_reason: str

    def to_json(self) -> dict[str, object]:
        return {
            "workflow": self.workflow,
            "question": self.question,
            "events": [event.to_json() for event in self.events],
            "stopping_reason": self.stopping_reason,
        }


def export_deep_dive_trajectory(result: DeepDiveResult) -> ResearchTrajectory:
    events = [
        TrajectoryEvent(
            step=round_result.round_number,
            action="retrieve",
            query=round_result.query,
            retrieved_document_ids=_unique_document_ids(round_result),
            coverage_gap=round_result.coverage_gap,
            observation=_summarize_round(round_result.coverage_gap, len(round_result.hits)),
        )
        for round_result in result.rounds
    ]
    return ResearchTrajectory(
        workflow="guided_deep_dive",
        question=result.question,
        events=events,
        stopping_reason=result.stopping_reason,
    )


def _unique_document_ids(round_result) -> list[str]:
    document_ids: list[str] = []
    seen: set[str] = set()
    for hit in round_result.hits:
        if hit.document_id not in seen:
            seen.add(hit.document_id)
            document_ids.append(hit.document_id)
    return document_ids


def _summarize_round(coverage_gap: str | None, hit_count: int) -> str:
    if coverage_gap is None:
        return f"retrieved {hit_count} hits and found no coverage gap"
    return f"retrieved {hit_count} hits with coverage gap: {coverage_gap}"
