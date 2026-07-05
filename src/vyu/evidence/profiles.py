from __future__ import annotations

from dataclasses import dataclass, field

from src.vyu.contracts import LoadedCorpus, StudyDesign


@dataclass(frozen=True)
class AutomatedEvidenceProfile:
    document_id: str
    study_design: StudyDesign
    evidence_level: str
    bias_flags: list[str]
    applicability_flags: list[str]
    warnings: list[str]
    assessment_confidence: float
    formal_risk_of_bias_completed: bool = False
    requires_human_review: bool = False
    funding: str | None = None
    conflicts: str | None = None
    missing_information_warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "study_design": self.study_design.value,
            "evidence_level": self.evidence_level,
            "bias_flags": self.bias_flags,
            "applicability_flags": self.applicability_flags,
            "warnings": self.warnings,
            "assessment_confidence": self.assessment_confidence,
            "formal_risk_of_bias_completed": self.formal_risk_of_bias_completed,
            "requires_human_review": self.requires_human_review,
            "funding": self.funding,
            "conflicts": self.conflicts,
            "missing_information_warnings": self.missing_information_warnings,
        }


def build_automated_evidence_profile(
    corpus: LoadedCorpus, document_id: str
) -> AutomatedEvidenceProfile:
    document = corpus.documents[document_id]
    source = corpus.evidence_profiles[document_id]
    warnings: list[str] = []
    applicability_flags = list(source.applicability_flags)
    bias_flags = list(source.bias_flags)

    if document.is_retracted or source.retraction_status == "retracted":
        warnings.append("retracted")
    if document.is_preprint or source.preprint_status:
        warnings.append("preprint_not_peer_reviewed")
        if "preprint" not in applicability_flags:
            applicability_flags.append("preprint")
    if source.assessment_confidence < 0.75:
        warnings.append("low_assessment_confidence")
    if bias_flags:
        warnings.append("bias_flags_present")
    if applicability_flags:
        warnings.append("applicability_limitations_present")

    requires_human_review = bool(warnings) or source.requires_human_review
    return AutomatedEvidenceProfile(
        document_id=document_id,
        study_design=source.study_design,
        evidence_level=source.evidence_level,
        bias_flags=bias_flags,
        applicability_flags=applicability_flags,
        warnings=warnings,
        assessment_confidence=source.assessment_confidence,
        requires_human_review=requires_human_review,
        funding=source.funding,
        conflicts=source.conflicts,
        missing_information_warnings=list(source.missing_information_warnings),
    )
