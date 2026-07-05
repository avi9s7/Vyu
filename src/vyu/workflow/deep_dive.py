from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.vyu.retrieval import RetrievalHit, RetrievalQuery


class Retriever(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        ...


@dataclass(frozen=True)
class PICOQuestion:
    population: str
    intervention: str
    comparator: str
    outcomes: list[str]


@dataclass(frozen=True)
class DeepDiveRound:
    round_number: int
    query: str
    hits: list[RetrievalHit]
    coverage_gap: str | None


@dataclass(frozen=True)
class DeepDiveResult:
    question: str
    pico: PICOQuestion
    rounds: list[DeepDiveRound]
    stopping_reason: str


def decompose_pico(question: str) -> PICOQuestion:
    text = question.lower()
    population = "adults with episodic migraine" if "episodic migraine" in text else "target population not specified"
    intervention = "VX-101" if "vx-101" in text else "intervention not specified"
    comparator = "standard therapy" if "standard therapy" in text or "compared" in text else "comparator not specified"
    outcomes: list[str] = []
    if "migraine day" in text or "migraine days" in text:
        outcomes.append("migraine days")
    if "safety" in text or "adverse" in text:
        outcomes.append("safety")
    if not outcomes:
        outcomes.append("outcome not specified")
    return PICOQuestion(
        population=population,
        intervention=intervention,
        comparator=comparator,
        outcomes=outcomes,
    )


def detect_coverage_gap(pico: PICOQuestion, hits: list[RetrievalHit]) -> str | None:
    if not hits:
        return "no_evidence_retrieved"
    joined = " ".join(f"{hit.document.title} {hit.passage.text}".lower() for hit in hits)
    if "migraine days" in pico.outcomes and "migraine day" not in joined:
        return "missing_primary_outcome"
    if "safety" in pico.outcomes and "safety" not in joined and "adverse" not in joined:
        return "missing_safety_evidence"
    if "adults with episodic migraine" in pico.population and "episodic migraine" not in joined:
        return "missing_population_match"
    return None


def run_guided_deep_dive(
    question: str,
    retriever: Retriever,
    max_rounds: int = 2,
    top_k: int = 5,
) -> DeepDiveResult:
    pico = decompose_pico(question)
    rounds: list[DeepDiveRound] = []
    query = _query_from_pico(pico)
    stopping_reason = "max_rounds_reached"

    for round_number in range(1, max_rounds + 1):
        hits = retriever.search(RetrievalQuery(text=query, top_k=top_k))
        gap = detect_coverage_gap(pico, hits)
        rounds.append(
            DeepDiveRound(
                round_number=round_number,
                query=query,
                hits=hits,
                coverage_gap=gap,
            )
        )
        if gap is None:
            stopping_reason = "enough_evidence"
            break
        query = _follow_up_query(pico, gap)

    return DeepDiveResult(
        question=question,
        pico=pico,
        rounds=rounds,
        stopping_reason=stopping_reason,
    )


def _query_from_pico(pico: PICOQuestion) -> str:
    return " ".join(
        part
        for part in [
            pico.intervention,
            pico.population,
            pico.comparator,
            " ".join(pico.outcomes),
        ]
        if "not specified" not in part
    )


def _follow_up_query(pico: PICOQuestion, gap: str) -> str:
    if gap == "missing_safety_evidence":
        return f"{pico.intervention} safety adverse events"
    if gap == "missing_primary_outcome":
        return f"{pico.intervention} migraine days primary outcome"
    if gap == "missing_population_match":
        return f"{pico.intervention} adults episodic migraine"
    return f"{pico.intervention} evidence"
