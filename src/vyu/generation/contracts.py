from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceItem:
    citation_id: str
    document_id: str
    passage_id: str
    title: str
    passage_text: str
    retrieval_score: float
    retrieval_source: str
    is_retracted: bool
    is_preprint: bool


@dataclass(frozen=True)
class EvidenceContext:
    question: str
    items: list[EvidenceItem]

    @property
    def citation_ids(self) -> set[str]:
        return {item.citation_id for item in self.items}


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    citation_ids: list[str]
    material: bool = True


@dataclass(frozen=True)
class GroundedAnswer:
    question: str
    answer_text: str
    claims: list[AnswerClaim]
    abstained: bool
    abstention_reason: str | None = None


@dataclass(frozen=True)
class CitationValidationResult:
    valid: bool
    invalid_citation_ids: list[str]
    uncited_material_claim_ids: list[str]
