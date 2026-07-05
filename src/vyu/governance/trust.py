from __future__ import annotations

from dataclasses import dataclass

from src.vyu.generation import CitationValidationResult, EvidenceContext, GroundedAnswer


@dataclass(frozen=True)
class TrustScore:
    overall: int
    components: dict[str, int]
    warnings: list[str]

    def to_json(self) -> dict[str, object]:
        return {
            "overall": self.overall,
            "components": self.components,
            "warnings": self.warnings,
        }


def calculate_trust_score(
    answer: GroundedAnswer,
    context: EvidenceContext,
    validation: CitationValidationResult,
) -> TrustScore:
    material_claims = [claim for claim in answer.claims if claim.material]
    cited_claims = [claim for claim in material_claims if claim.citation_ids]
    citation_coverage = _percent(len(cited_claims), len(material_claims)) if material_claims else 100
    citation_faithfulness = 100 if validation.valid else 45
    evidence_strength = _evidence_strength(context)
    retrieval_stability = 70 if context.items else 0
    conflict_handling = 65 if _has_conflict_marker(context) else 85
    bias_completeness = 70 if context.items else 0
    source_status = _source_status(context)
    audit_completeness = 100

    components = {
        "citation_coverage": citation_coverage,
        "citation_faithfulness": citation_faithfulness,
        "evidence_strength": evidence_strength,
        "retrieval_stability": retrieval_stability,
        "conflict_handling": conflict_handling,
        "bias_completeness": bias_completeness,
        "source_status": source_status,
        "audit_completeness": audit_completeness,
    }
    weights = {
        "citation_coverage": 0.25,
        "citation_faithfulness": 0.20,
        "evidence_strength": 0.15,
        "retrieval_stability": 0.10,
        "conflict_handling": 0.10,
        "bias_completeness": 0.10,
        "source_status": 0.05,
        "audit_completeness": 0.05,
    }
    overall = round(sum(components[key] * weights[key] for key in components))
    warnings: list[str] = []
    if answer.abstained:
        warnings.append("Answer abstained because evidence was insufficient")
    if _has_conflict_marker(context):
        warnings.append("Potential conflicting evidence detected in retrieved passages")
    if any(item.is_preprint for item in context.items):
        warnings.append("Preprint evidence is present")
    if any(item.is_retracted for item in context.items):
        warnings.append("Retracted evidence was retrieved and should be excluded or reviewed")
    return TrustScore(overall=overall, components=components, warnings=warnings)


def _percent(numerator: int, denominator: int) -> int:
    if denominator == 0:
        return 0
    return round(100 * numerator / denominator)


def _evidence_strength(context: EvidenceContext) -> int:
    if not context.items:
        return 0
    joined = " ".join(item.passage_text.lower() for item in context.items)
    score = 50
    if "randomized_controlled_trial" in joined or "randomized trial" in joined:
        score += 20
    if "systematic_review" in joined or "meta-analysis" in joined:
        score += 15
    if "case_report" in joined or "case report" in joined:
        score -= 15
    return max(0, min(100, score))


def _source_status(context: EvidenceContext) -> int:
    if not context.items:
        return 0
    score = 100
    if any(item.is_retracted for item in context.items):
        score -= 35
    if any(item.is_preprint for item in context.items):
        score -= 15
    return max(0, score)


def _has_conflict_marker(context: EvidenceContext) -> bool:
    text = " ".join(item.passage_text.lower() for item in context.items)
    return "conflicting" in text or ("positive finding" in text and "negative finding" in text)
