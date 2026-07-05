from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Iterable

from src.vyu.contracts import DocumentRecord, EvidenceProfile, LoadedCorpus, StudyDesign
from src.vyu.evidence.contradictions import detect_contradictions
from src.vyu.retrieval.contracts import RetrievalHit
from src.vyu.retrieval.production import RetrievalRunRecord


class EvidenceAssessmentStatus(StrEnum):
    DRAFT = "draft"
    COMPLETED = "completed"
    EXTERNAL_PENDING = "external_pending"
    EXTERNAL_ACCEPTED = "external_accepted"
    EXTERNAL_FAILED = "external_failed"
    REVIEWER_ADJUSTED = "reviewer_adjusted"


class EvidenceStrengthBand(StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"
    UNSUITABLE = "unsuitable"


@dataclass(frozen=True)
class EvidenceMethodologyRuleSet:
    ruleset_id: str
    version: str
    specialty: str
    framework: str = "automated_evidence_profile_grade_inspired_v1"
    formal_grade_completed: bool = False
    formal_risk_of_bias_completed: bool = False
    rules: tuple[dict[str, Any], ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "version": self.version,
            "specialty": self.specialty,
            "framework": self.framework,
            "formal_grade_completed": self.formal_grade_completed,
            "formal_risk_of_bias_completed": self.formal_risk_of_bias_completed,
            "rules": [dict(rule) for rule in self.rules],
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EvidenceMethodologyRuleSet":
        return cls(
            ruleset_id=str(payload["ruleset_id"]),
            version=str(payload["version"]),
            specialty=str(payload["specialty"]),
            framework=str(payload.get("framework", "automated_evidence_profile_grade_inspired_v1")),
            formal_grade_completed=bool(payload.get("formal_grade_completed", False)),
            formal_risk_of_bias_completed=bool(
                payload.get("formal_risk_of_bias_completed", False)
            ),
            rules=tuple(dict(rule) for rule in payload.get("rules", [])),
            created_at=str(payload["created_at"]),
        )


def default_methodology_ruleset(
    specialty: str = "general_biomedical_research",
    *,
    created_at: str | None = None,
) -> EvidenceMethodologyRuleSet:
    return EvidenceMethodologyRuleSet(
        ruleset_id=f"{specialty}_automated_methodology_rules_v1",
        version="evidence_methodology_rules_v1",
        specialty=specialty,
        rules=(
            {
                "domain": "study_design",
                "description": "Systematic reviews, meta-analyses, RCTs, and guidelines start with higher evidence-design scores than observational or case-level evidence.",
            },
            {
                "domain": "risk_of_bias",
                "description": "Synthetic bias flags reduce the automated score and require human review when material.",
            },
            {
                "domain": "publication_status",
                "description": "Retracted sources are unsuitable; preprints are labeled as not peer reviewed.",
            },
            {
                "domain": "applicability",
                "description": "Population and intervention mismatch, under-representation, or missing context reduce applicability.",
            },
            {
                "domain": "conflict_handling",
                "description": "Known funding or conflict limitations are surfaced for reviewer inspection.",
            },
        ),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


@dataclass(frozen=True)
class EvidenceMethodologyAssessmentRecord:
    assessment_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    document_id: str
    question: str
    topic: str
    ruleset_id: str
    ruleset_version: str
    specialty: str
    status: EvidenceAssessmentStatus
    study_design: StudyDesign
    detected_study_design: StudyDesign
    evidence_strength_score: int
    evidence_strength_band: EvidenceStrengthBand
    source_reliability_score: int
    recency_score: int
    population_context_match_score: int
    methodology_domain_scores: dict[str, int]
    bias_flags: tuple[str, ...] = ()
    applicability_flags: tuple[str, ...] = ()
    limitation_flags: tuple[str, ...] = ()
    contradiction_flags: tuple[str, ...] = ()
    missing_information_warnings: tuple[str, ...] = ()
    funding: str | None = None
    conflicts: str | None = None
    retraction_status: str = "not_retracted"
    preprint_status: bool = False
    assessment_confidence: float = 0.0
    requires_human_review: bool = False
    assessment_source: str = "local_rules"
    external_request_id: str | None = None
    provider_id: str | None = None
    reviewer_adjusted: bool = False
    reviewer_rating_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "document_id": self.document_id,
            "question": self.question,
            "topic": self.topic,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "specialty": self.specialty,
            "status": self.status.value,
            "study_design": self.study_design.value,
            "detected_study_design": self.detected_study_design.value,
            "evidence_strength_score": self.evidence_strength_score,
            "evidence_strength_band": self.evidence_strength_band.value,
            "source_reliability_score": self.source_reliability_score,
            "recency_score": self.recency_score,
            "population_context_match_score": self.population_context_match_score,
            "methodology_domain_scores": dict(self.methodology_domain_scores),
            "bias_flags": list(self.bias_flags),
            "applicability_flags": list(self.applicability_flags),
            "limitation_flags": list(self.limitation_flags),
            "contradiction_flags": list(self.contradiction_flags),
            "missing_information_warnings": list(self.missing_information_warnings),
            "funding": self.funding,
            "conflicts": self.conflicts,
            "retraction_status": self.retraction_status,
            "preprint_status": self.preprint_status,
            "assessment_confidence": self.assessment_confidence,
            "requires_human_review": self.requires_human_review,
            "assessment_source": self.assessment_source,
            "external_request_id": self.external_request_id,
            "provider_id": self.provider_id,
            "reviewer_adjusted": self.reviewer_adjusted,
            "reviewer_rating_id": self.reviewer_rating_id,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EvidenceMethodologyAssessmentRecord":
        return cls(
            assessment_id=str(payload["assessment_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            document_id=str(payload["document_id"]),
            question=str(payload["question"]),
            topic=str(payload["topic"]),
            ruleset_id=str(payload["ruleset_id"]),
            ruleset_version=str(payload["ruleset_version"]),
            specialty=str(payload["specialty"]),
            status=EvidenceAssessmentStatus(str(payload["status"])),
            study_design=StudyDesign(str(payload["study_design"])),
            detected_study_design=StudyDesign(str(payload["detected_study_design"])),
            evidence_strength_score=int(payload["evidence_strength_score"]),
            evidence_strength_band=EvidenceStrengthBand(str(payload["evidence_strength_band"])),
            source_reliability_score=int(payload["source_reliability_score"]),
            recency_score=int(payload["recency_score"]),
            population_context_match_score=int(payload["population_context_match_score"]),
            methodology_domain_scores={
                str(key): int(value)
                for key, value in payload.get("methodology_domain_scores", {}).items()
            },
            bias_flags=tuple(str(item) for item in payload.get("bias_flags", [])),
            applicability_flags=tuple(
                str(item) for item in payload.get("applicability_flags", [])
            ),
            limitation_flags=tuple(str(item) for item in payload.get("limitation_flags", [])),
            contradiction_flags=tuple(
                str(item) for item in payload.get("contradiction_flags", [])
            ),
            missing_information_warnings=tuple(
                str(item) for item in payload.get("missing_information_warnings", [])
            ),
            funding=(str(payload["funding"]) if payload.get("funding") is not None else None),
            conflicts=(str(payload["conflicts"]) if payload.get("conflicts") is not None else None),
            retraction_status=str(payload.get("retraction_status", "not_retracted")),
            preprint_status=bool(payload.get("preprint_status", False)),
            assessment_confidence=float(payload.get("assessment_confidence", 0.0)),
            requires_human_review=bool(payload.get("requires_human_review", False)),
            assessment_source=str(payload.get("assessment_source", "local_rules")),
            external_request_id=(
                str(payload["external_request_id"])
                if payload.get("external_request_id") is not None
                else None
            ),
            provider_id=(
                str(payload["provider_id"]) if payload.get("provider_id") is not None else None
            ),
            reviewer_adjusted=bool(payload.get("reviewer_adjusted", False)),
            reviewer_rating_id=(
                str(payload["reviewer_rating_id"])
                if payload.get("reviewer_rating_id") is not None
                else None
            ),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class EvidenceMethodologyRunRecord:
    methodology_run_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    question: str
    topic: str
    ruleset_id: str
    ruleset_version: str
    status: EvidenceAssessmentStatus
    assessment_ids: tuple[str, ...]
    document_ids: tuple[str, ...]
    evidence_mix: dict[str, int]
    overall_strength_score: int
    overall_strength_band: EvidenceStrengthBand
    limitation_flags: tuple[str, ...]
    contradiction_flags: tuple[str, ...]
    requires_human_review: bool
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "methodology_run_id": self.methodology_run_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "question": self.question,
            "topic": self.topic,
            "ruleset_id": self.ruleset_id,
            "ruleset_version": self.ruleset_version,
            "status": self.status.value,
            "assessment_ids": list(self.assessment_ids),
            "document_ids": list(self.document_ids),
            "evidence_mix": dict(self.evidence_mix),
            "overall_strength_score": self.overall_strength_score,
            "overall_strength_band": self.overall_strength_band.value,
            "limitation_flags": list(self.limitation_flags),
            "contradiction_flags": list(self.contradiction_flags),
            "requires_human_review": self.requires_human_review,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EvidenceMethodologyRunRecord":
        return cls(
            methodology_run_id=str(payload["methodology_run_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            question=str(payload["question"]),
            topic=str(payload["topic"]),
            ruleset_id=str(payload["ruleset_id"]),
            ruleset_version=str(payload["ruleset_version"]),
            status=EvidenceAssessmentStatus(str(payload["status"])),
            assessment_ids=tuple(str(item) for item in payload.get("assessment_ids", [])),
            document_ids=tuple(str(item) for item in payload.get("document_ids", [])),
            evidence_mix={str(key): int(value) for key, value in payload.get("evidence_mix", {}).items()},
            overall_strength_score=int(payload["overall_strength_score"]),
            overall_strength_band=EvidenceStrengthBand(str(payload["overall_strength_band"])),
            limitation_flags=tuple(str(item) for item in payload.get("limitation_flags", [])),
            contradiction_flags=tuple(
                str(item) for item in payload.get("contradiction_flags", [])
            ),
            requires_human_review=bool(payload.get("requires_human_review", False)),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class ReviewerEvidenceRatingRecord:
    rating_id: str
    assessment_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    reviewer_id: str
    reviewer_role: str
    original_strength_score: int
    adjusted_strength_score: int
    adjusted_strength_band: EvidenceStrengthBand
    adjusted_evidence_level: str
    adjustment_reasons: tuple[str, ...]
    comment: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "rating_id": self.rating_id,
            "assessment_id": self.assessment_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "original_strength_score": self.original_strength_score,
            "adjusted_strength_score": self.adjusted_strength_score,
            "adjusted_strength_band": self.adjusted_strength_band.value,
            "adjusted_evidence_level": self.adjusted_evidence_level,
            "adjustment_reasons": list(self.adjustment_reasons),
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ReviewerEvidenceRatingRecord":
        return cls(
            rating_id=str(payload["rating_id"]),
            assessment_id=str(payload["assessment_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            reviewer_id=str(payload["reviewer_id"]),
            reviewer_role=str(payload["reviewer_role"]),
            original_strength_score=int(payload["original_strength_score"]),
            adjusted_strength_score=int(payload["adjusted_strength_score"]),
            adjusted_strength_band=EvidenceStrengthBand(str(payload["adjusted_strength_band"])),
            adjusted_evidence_level=str(payload["adjusted_evidence_level"]),
            adjustment_reasons=tuple(
                str(item) for item in payload.get("adjustment_reasons", [])
            ),
            comment=str(payload.get("comment", "")),
            created_at=str(payload["created_at"]),
        )


def build_methodology_assessments_from_hits(
    *,
    corpus: LoadedCorpus,
    hits: list[RetrievalHit],
    retrieval_run: RetrievalRunRecord,
    ruleset: EvidenceMethodologyRuleSet | None = None,
    specialty: str = "general_biomedical_research",
    created_at: str | None = None,
    current_year: int = 2026,
) -> tuple[EvidenceMethodologyAssessmentRecord, ...]:
    ruleset = ruleset or default_methodology_ruleset(specialty, created_at=created_at)
    document_ids = _unique_in_order(hit.document_id for hit in hits)
    documents = [corpus.documents[document_id] for document_id in document_ids]
    contradiction_ids = _contradiction_document_ids(documents)
    return tuple(
        build_methodology_assessment(
            corpus=corpus,
            document_id=document_id,
            retrieval_run=retrieval_run,
            ruleset=ruleset,
            contradiction_document_ids=contradiction_ids,
            created_at=created_at,
            current_year=current_year,
        )
        for document_id in document_ids
    )


def build_methodology_assessment(
    *,
    corpus: LoadedCorpus,
    document_id: str,
    retrieval_run: RetrievalRunRecord,
    ruleset: EvidenceMethodologyRuleSet,
    contradiction_document_ids: set[str] | None = None,
    created_at: str | None = None,
    current_year: int = 2026,
) -> EvidenceMethodologyAssessmentRecord:
    document = corpus.documents[document_id]
    profile = corpus.evidence_profiles[document_id]
    contradiction_document_ids = contradiction_document_ids or set()
    domain_scores = _domain_scores(
        document=document,
        profile=profile,
        question=retrieval_run.question,
        current_year=current_year,
        contradicted=document_id in contradiction_document_ids,
    )
    score = _weighted_score(domain_scores)
    limitation_flags = _limitation_flags(document, profile)
    contradiction_flags = (
        ("conflicting_primary_outcome_signal",)
        if document_id in contradiction_document_ids
        else ()
    )
    if document.is_retracted or profile.retraction_status == "retracted":
        score = 0
    band = evidence_strength_band(score)
    requires_human_review = (
        score < 70
        or bool(profile.bias_flags)
        or bool(profile.applicability_flags)
        or bool(profile.missing_information_warnings)
        or bool(contradiction_flags)
        or document.is_retracted
        or document.is_preprint
        or profile.assessment_confidence < 0.75
    )
    return EvidenceMethodologyAssessmentRecord(
        assessment_id=f"methodology-{retrieval_run.retrieval_run_id}-{document_id}",
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        document_id=document_id,
        question=retrieval_run.question,
        topic=retrieval_run.topic,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.version,
        specialty=ruleset.specialty,
        status=EvidenceAssessmentStatus.COMPLETED,
        study_design=profile.study_design,
        detected_study_design=document.study_design,
        evidence_strength_score=score,
        evidence_strength_band=band,
        source_reliability_score=domain_scores["source_reliability"],
        recency_score=domain_scores["recency"],
        population_context_match_score=domain_scores["applicability"],
        methodology_domain_scores=domain_scores,
        bias_flags=tuple(profile.bias_flags),
        applicability_flags=tuple(profile.applicability_flags),
        limitation_flags=limitation_flags,
        contradiction_flags=contradiction_flags,
        missing_information_warnings=tuple(profile.missing_information_warnings),
        funding=profile.funding or document.funding,
        conflicts=profile.conflicts or document.conflicts,
        retraction_status=profile.retraction_status,
        preprint_status=profile.preprint_status,
        assessment_confidence=profile.assessment_confidence,
        requires_human_review=requires_human_review,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        metadata={
            "formal_grade_completed": ruleset.formal_grade_completed,
            "formal_risk_of_bias_completed": ruleset.formal_risk_of_bias_completed,
            "methodology_note": "Automated Evidence Profile; not a formal GRADE, RoB 2, ROBINS-I, AMSTAR 2, or QUADAS-2 assessment.",
        },
    )


def build_methodology_run_record(
    *,
    methodology_run_id: str,
    retrieval_run: RetrievalRunRecord,
    assessments: Iterable[EvidenceMethodologyAssessmentRecord],
    ruleset: EvidenceMethodologyRuleSet,
    created_at: str | None = None,
) -> EvidenceMethodologyRunRecord:
    assessment_list = list(assessments)
    if not assessment_list:
        overall_score = 0
    else:
        overall_score = round(
            sum(assessment.evidence_strength_score for assessment in assessment_list)
            / len(assessment_list)
        )
    limitation_flags = tuple(
        sorted({flag for assessment in assessment_list for flag in assessment.limitation_flags})
    )
    contradiction_flags = tuple(
        sorted({flag for assessment in assessment_list for flag in assessment.contradiction_flags})
    )
    evidence_mix = dict(
        sorted(
            Counter(assessment.detected_study_design.value for assessment in assessment_list).items()
        )
    )
    return EvidenceMethodologyRunRecord(
        methodology_run_id=methodology_run_id,
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        question=retrieval_run.question,
        topic=retrieval_run.topic,
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.version,
        status=EvidenceAssessmentStatus.COMPLETED,
        assessment_ids=tuple(assessment.assessment_id for assessment in assessment_list),
        document_ids=tuple(assessment.document_id for assessment in assessment_list),
        evidence_mix=evidence_mix,
        overall_strength_score=overall_score,
        overall_strength_band=evidence_strength_band(overall_score),
        limitation_flags=limitation_flags,
        contradiction_flags=contradiction_flags,
        requires_human_review=any(
            assessment.requires_human_review for assessment in assessment_list
        ),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        metadata={
            "assessment_count": len(assessment_list),
            "human_review_reason": "one_or_more_assessments_require_review"
            if any(assessment.requires_human_review for assessment in assessment_list)
            else None,
        },
    )


def create_reviewer_evidence_rating(
    *,
    rating_id: str,
    assessment: EvidenceMethodologyAssessmentRecord,
    reviewer_id: str,
    reviewer_role: str,
    adjusted_strength_score: int,
    adjusted_evidence_level: str,
    adjustment_reasons: tuple[str, ...],
    comment: str,
    created_at: str | None = None,
) -> ReviewerEvidenceRatingRecord:
    adjusted = _clamp(adjusted_strength_score)
    return ReviewerEvidenceRatingRecord(
        rating_id=rating_id,
        assessment_id=assessment.assessment_id,
        run_id=assessment.run_id,
        tenant_id=assessment.tenant_id,
        workspace_id=assessment.workspace_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        original_strength_score=assessment.evidence_strength_score,
        adjusted_strength_score=adjusted,
        adjusted_strength_band=evidence_strength_band(adjusted),
        adjusted_evidence_level=adjusted_evidence_level,
        adjustment_reasons=adjustment_reasons,
        comment=comment,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def apply_reviewer_rating(
    assessment: EvidenceMethodologyAssessmentRecord,
    rating: ReviewerEvidenceRatingRecord,
) -> EvidenceMethodologyAssessmentRecord:
    if rating.assessment_id != assessment.assessment_id:
        raise ValueError("Reviewer rating does not target this assessment.")
    return replace(
        assessment,
        status=EvidenceAssessmentStatus.REVIEWER_ADJUSTED,
        evidence_strength_score=rating.adjusted_strength_score,
        evidence_strength_band=rating.adjusted_strength_band,
        reviewer_adjusted=True,
        reviewer_rating_id=rating.rating_id,
        requires_human_review=False,
        metadata={
            **assessment.metadata,
            "reviewer_adjustment_reasons": list(rating.adjustment_reasons),
            "reviewer_comment_present": bool(rating.comment),
        },
    )


def evidence_strength_band(score: int) -> EvidenceStrengthBand:
    score = _clamp(score)
    if score >= 80:
        return EvidenceStrengthBand.HIGH
    if score >= 65:
        return EvidenceStrengthBand.MODERATE
    if score >= 40:
        return EvidenceStrengthBand.LOW
    if score > 0:
        return EvidenceStrengthBand.VERY_LOW
    return EvidenceStrengthBand.UNSUITABLE


def _domain_scores(
    *,
    document: DocumentRecord,
    profile: EvidenceProfile,
    question: str,
    current_year: int,
    contradicted: bool,
) -> dict[str, int]:
    design = _study_design_score(profile.study_design)
    source = _source_reliability_score(document, profile)
    recency = _recency_score(document.year, current_year)
    applicability = _applicability_score(document, profile, question)
    bias = _bias_score(profile)
    consistency = 55 if contradicted else 88
    precision = _precision_score(profile)
    return {
        "study_design": design,
        "source_reliability": source,
        "recency": recency,
        "applicability": applicability,
        "risk_of_bias": bias,
        "consistency": consistency,
        "precision_and_completeness": precision,
    }


def _weighted_score(domain_scores: dict[str, int]) -> int:
    weights = {
        "study_design": 0.24,
        "source_reliability": 0.18,
        "risk_of_bias": 0.16,
        "applicability": 0.14,
        "consistency": 0.12,
        "precision_and_completeness": 0.10,
        "recency": 0.06,
    }
    return _clamp(round(sum(domain_scores[key] * weight for key, weight in weights.items())))


def _study_design_score(study_design: StudyDesign) -> int:
    return {
        StudyDesign.SYSTEMATIC_REVIEW: 90,
        StudyDesign.META_ANALYSIS: 88,
        StudyDesign.RANDOMIZED_CONTROLLED_TRIAL: 86,
        StudyDesign.GUIDELINE: 82,
        StudyDesign.COHORT_STUDY: 64,
        StudyDesign.CASE_CONTROL_STUDY: 58,
        StudyDesign.CASE_SERIES: 38,
        StudyDesign.CASE_REPORT: 28,
        StudyDesign.PREPRINT: 40,
        StudyDesign.UNKNOWN: 25,
    }[study_design]


def _source_reliability_score(document: DocumentRecord, profile: EvidenceProfile) -> int:
    if document.is_retracted or profile.retraction_status == "retracted":
        return 0
    score = 88
    if document.is_preprint or profile.preprint_status:
        score -= 35
    if profile.funding and "manufacturer" in profile.funding.lower():
        score -= 8
    if profile.conflicts and "incomplete" in profile.conflicts.lower():
        score -= 10
    if profile.missing_information_warnings:
        score -= 6 * len(profile.missing_information_warnings)
    return _clamp(score)


def _recency_score(year: int, current_year: int) -> int:
    age = max(0, current_year - year)
    if age <= 2:
        return 95
    if age <= 5:
        return 88
    if age <= 10:
        return 72
    return 55


def _applicability_score(
    document: DocumentRecord,
    profile: EvidenceProfile,
    question: str,
) -> int:
    score = 86
    text = question.lower()
    population = (document.population or "").lower()
    intervention = (document.intervention or "").lower()
    if "adult" in text and "adult" not in population:
        score -= 18
    if "vx-101" in text and "vx-101" not in intervention:
        score -= 25
    if any("over_65" in flag or "underrepresented" in flag for flag in profile.applicability_flags):
        score -= 12
    score -= 6 * len(profile.applicability_flags)
    return _clamp(score)


def _bias_score(profile: EvidenceProfile) -> int:
    score = 90
    for flag in profile.bias_flags:
        if "high" in flag or "retracted" in flag:
            score -= 30
        elif "unclear" in flag:
            score -= 14
        else:
            score -= 10
    return _clamp(score)


def _precision_score(profile: EvidenceProfile) -> int:
    score = 86
    for warning in profile.missing_information_warnings:
        if "sample" in warning or "confidence" in warning:
            score -= 14
        else:
            score -= 8
    return _clamp(score)


def _limitation_flags(document: DocumentRecord, profile: EvidenceProfile) -> tuple[str, ...]:
    flags: list[str] = []
    if document.is_retracted or profile.retraction_status == "retracted":
        flags.append("retracted_source")
    if document.is_preprint or profile.preprint_status:
        flags.append("preprint_not_peer_reviewed")
    if profile.funding:
        flags.append("funding_disclosure_present")
    if profile.conflicts:
        flags.append("conflict_of_interest_disclosure_present")
    flags.extend(profile.bias_flags)
    flags.extend(profile.applicability_flags)
    flags.extend(profile.missing_information_warnings)
    return tuple(dict.fromkeys(flags))


def _contradiction_document_ids(documents: list[DocumentRecord]) -> set[str]:
    ids: set[str] = set()
    for contradiction in detect_contradictions(documents):
        ids.update(contradiction.document_ids)
    return ids


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _clamp(value: int | float) -> int:
    return max(0, min(100, int(round(value))))
