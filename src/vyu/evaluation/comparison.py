from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.vyu.contracts import LoadedCorpus
from src.vyu.retrieval import RetrievalHit, RetrievalQuery
from src.vyu.workflow import run_guided_deep_dive


class Retriever(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        ...


@dataclass(frozen=True)
class WorkflowMetrics:
    quality: float
    estimated_cost_units: int
    estimated_latency_units: int
    auditability: float
    trajectory_count: int

    def to_json(self) -> dict[str, float | int]:
        return {
            "quality": self.quality,
            "estimated_cost_units": self.estimated_cost_units,
            "estimated_latency_units": self.estimated_latency_units,
            "auditability": self.auditability,
            "trajectory_count": self.trajectory_count,
        }


@dataclass(frozen=True)
class WorkflowComparison:
    workflow_metrics: dict[str, WorkflowMetrics]
    recommendation: str
    rationale: str

    def to_json(self) -> dict[str, object]:
        return {
            "workflow_metrics": {
                name: metrics.to_json()
                for name, metrics in self.workflow_metrics.items()
            },
            "recommendation": self.recommendation,
            "rationale": self.rationale,
        }


def compare_workflows(
    corpus: LoadedCorpus,
    retriever: Retriever,
    questions: list[str],
    top_k: int = 5,
    max_rounds: int = 2,
) -> WorkflowComparison:
    fixed_scores: list[float] = []
    guided_scores: list[float] = []
    fixed_cost = 0
    guided_cost = 0
    fixed_latency = 0
    guided_latency = 0
    guided_trajectories = 0

    for question in questions:
        fixed_hits = retriever.search(RetrievalQuery(text=question, top_k=top_k))
        fixed_scores.append(_quality_score(corpus, question, fixed_hits))
        fixed_cost += 1
        fixed_latency += 1

        deep_dive = run_guided_deep_dive(
            question,
            retriever,
            max_rounds=max_rounds,
            top_k=top_k,
        )
        guided_hits = [hit for round_result in deep_dive.rounds for hit in round_result.hits]
        guided_scores.append(_quality_score(corpus, question, guided_hits))
        guided_cost += len(deep_dive.rounds)
        guided_latency += len(deep_dive.rounds)
        guided_trajectories += 1

    fixed = WorkflowMetrics(
        quality=_mean(fixed_scores),
        estimated_cost_units=fixed_cost,
        estimated_latency_units=fixed_latency,
        auditability=0.80,
        trajectory_count=len(questions),
    )
    guided = WorkflowMetrics(
        quality=_mean(guided_scores),
        estimated_cost_units=guided_cost,
        estimated_latency_units=guided_latency,
        auditability=0.95,
        trajectory_count=guided_trajectories,
    )
    recommendation, rationale = _recommend(fixed, guided)
    return WorkflowComparison(
        workflow_metrics={
            "fixed_one_shot": fixed,
            "guided_deep_dive": guided,
        },
        recommendation=recommendation,
        rationale=rationale,
    )


def _quality_score(corpus: LoadedCorpus, question: str, hits: list[RetrievalHit]) -> float:
    expected_document_ids = _expected_document_ids(corpus, question)
    retrieved_ids = {hit.document_id for hit in hits}
    if expected_document_ids:
        return len(retrieved_ids & expected_document_ids) / len(expected_document_ids)
    return 1.0 if retrieved_ids else 0.0


def _expected_document_ids(corpus: LoadedCorpus, question: str) -> set[str]:
    normalized = question.strip().lower()
    for question_id, golden_question in corpus.golden_questions.items():
        if golden_question.question.strip().lower() == normalized:
            return set(corpus.expected_documents.get(question_id, []))
    return set()


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _recommend(fixed: WorkflowMetrics, guided: WorkflowMetrics) -> tuple[str, str]:
    if guided.quality > fixed.quality and guided.auditability >= fixed.auditability:
        return (
            "evaluate_guided_workflow_for_adoption",
            "Guided deep dive improved quality without reducing auditability.",
        )
    return (
        "keep_deterministic_baseline",
        "Guided deep dive has not demonstrated a quality gain over the deterministic baseline.",
    )
