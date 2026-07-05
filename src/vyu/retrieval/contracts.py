from __future__ import annotations

from dataclasses import dataclass

from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign


@dataclass(frozen=True)
class MetadataFilter:
    include_retracted: bool = True
    include_preprints: bool = True
    study_designs: set[StudyDesign] | None = None
    publication_statuses: set[str] | None = None
    population_contains: str | None = None
    intervention: str | None = None

    def matches(self, document: DocumentRecord) -> bool:
        if not self.include_retracted and document.is_retracted:
            return False
        if not self.include_preprints and document.is_preprint:
            return False
        if self.study_designs is not None and document.study_design not in self.study_designs:
            return False
        if (
            self.publication_statuses is not None
            and document.publication_status not in self.publication_statuses
        ):
            return False
        if self.population_contains is not None:
            population = (document.population or "").lower()
            if self.population_contains.lower() not in population:
                return False
        if self.intervention is not None:
            intervention = (document.intervention or "").lower()
            if self.intervention.lower() != intervention:
                return False
        return True


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    top_k: int = 10
    metadata_filter: MetadataFilter | None = None


@dataclass(frozen=True)
class RetrievalScore:
    source: str
    value: float
    components: dict[str, float]


@dataclass(frozen=True)
class RetrievalTrace:
    retriever: str
    original_rank: int
    post_filter_rank: int
    final_rank: int


@dataclass(frozen=True)
class RetrievalHit:
    document_id: str
    passage_id: str
    document: DocumentRecord
    passage: PassageRecord
    score: RetrievalScore
    trace: RetrievalTrace
