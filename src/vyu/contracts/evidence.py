from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StudyDesign(StrEnum):
    RANDOMIZED_CONTROLLED_TRIAL = "randomized_controlled_trial"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    COHORT_STUDY = "cohort_study"
    CASE_CONTROL_STUDY = "case_control_study"
    CASE_SERIES = "case_series"
    CASE_REPORT = "case_report"
    GUIDELINE = "guideline"
    PREPRINT = "preprint"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DocumentRecord:
    document_id: str
    title: str
    year: int
    study_design: StudyDesign
    source_type: str
    publication_status: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    journal: str = "Vyu Synthetic Biomedical Corpus"
    doi: str | None = None
    pmid: str | None = None
    is_preprint: bool = False
    is_retracted: bool = False
    funding: str | None = None
    conflicts: str | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    outcomes: tuple[str, ...] = ()

    @property
    def citation_label(self) -> str:
        return f"{self.document_id} ({self.year})"


@dataclass(frozen=True)
class PassageRecord:
    passage_id: str
    document_id: str
    section: str
    text: str
    page: int | None = None
    table_id: str | None = None


@dataclass(frozen=True)
class EvidenceProfile:
    document_id: str
    study_design: StudyDesign
    evidence_level: str
    bias_flags: list[str]
    applicability_flags: list[str]
    retraction_status: str
    preprint_status: bool
    assessment_confidence: float
    funding: str | None = None
    conflicts: str | None = None
    missing_information_warnings: list[str] = field(default_factory=list)

    @property
    def requires_human_review(self) -> bool:
        return (
            self.retraction_status == "retracted"
            or self.preprint_status
            or bool(self.bias_flags)
            or bool(self.applicability_flags)
            or self.assessment_confidence < 0.75
        )


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    document_id: str
    passage_id: str
    claim: str
    supports_claim: bool


@dataclass(frozen=True)
class GoldenQuestion:
    question_id: str
    question: str
    category: str
    expected_action: str


@dataclass(frozen=True)
class LoadedCorpus:
    documents: dict[str, DocumentRecord]
    passages: dict[str, PassageRecord]
    evidence_profiles: dict[str, EvidenceProfile]
    retracted_document_ids: set[str]
    golden_questions: dict[str, GoldenQuestion]
    expected_documents: dict[str, list[str]]
    expected_citations: dict[str, list[str]]
    expected_evidence_flags: dict[str, list[str]]

    def find_documents(self, keyword: str) -> list[DocumentRecord]:
        needle = keyword.lower()
        return [
            document
            for document in self.documents.values()
            if needle in document.title.lower()
            or needle in document.abstract.lower()
            or needle in document.publication_status.lower()
        ]
