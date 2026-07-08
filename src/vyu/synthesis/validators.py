from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from src.vyu.synthesis.context import BuiltEvidenceContext
from src.vyu.synthesis.schema import (
    GroundedAnswerOutput,
    GroundedAnswerSemanticValidationError,
    validate_grounded_answer_semantics,
)

PATIENT_SPECIFIC_PATTERNS = (
    re.compile(r"\byou should take\b", re.IGNORECASE),
    re.compile(r"\byour (diagnosis|treatment|prognosis|dose)\b", re.IGNORECASE),
    re.compile(r"\bfor your patient\b", re.IGNORECASE),
    re.compile(r"\brecommend (you|your)\b", re.IGNORECASE),
    re.compile(r"\bprescribe (you|your)\b", re.IGNORECASE),
)

MIN_SUPPORTED_OVERLAP_ERROR = 0.05
MIN_MIXED_OVERLAP_WARNING = 0.15


@dataclass(frozen=True)
class ValidationWarning:
    code: str
    message: str


@dataclass(frozen=True)
class SynthesisValidationResult:
    errors: tuple[str, ...] = ()
    warnings: tuple[ValidationWarning, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class CitationEvidenceRecord:
    citation_id: str
    document_version_id: str
    document_chunk_id: str
    excerpt_sha256: str
    excerpt: str


def required_abstention_reason(context: BuiltEvidenceContext) -> str | None:
    if context.items:
        return None
    if not context.exclusions:
        return "insufficient_evidence"
    reasons = {exclusion.reason for exclusion in context.exclusions}
    if reasons == {"retracted_evidence"}:
        return "all_evidence_retracted"
    if "source_revoked_after_run" in reasons:
        return "evidence_revoked"
    return "insufficient_evidence"


def citation_index_from_context(
    context: BuiltEvidenceContext,
) -> dict[str, CitationEvidenceRecord]:
    return {
        item.citation_id: CitationEvidenceRecord(
            citation_id=item.citation_id,
            document_version_id=str(item.document_version_id),
            document_chunk_id=str(item.document_chunk_id),
            excerpt_sha256=_sha256_text(item.excerpt),
            excerpt=item.excerpt,
        )
        for item in context.items
    }


def validate_synthesis_output(
    output: GroundedAnswerOutput,
    *,
    context: BuiltEvidenceContext,
    required_abstention: str | None,
    max_answer_chars: int,
    max_claims: int,
    chunk_hashes: dict[str, str] | None = None,
) -> SynthesisValidationResult:
    errors: list[str] = []
    warnings: list[ValidationWarning] = []

    try:
        validate_grounded_answer_semantics(
            output,
            allowed_citation_ids=frozenset(item.citation_id for item in context.items),
        )
    except GroundedAnswerSemanticValidationError as exc:
        errors.extend(exc.errors)

    if required_abstention is not None and not output.abstained:
        errors.append("answer must abstain when evidence context requires abstention")
    if required_abstention is not None and output.abstained:
        if output.abstention_reason != required_abstention:
            errors.append(
                "abstention_reason does not match deterministic context requirement"
            )

    if len(output.answer_summary) > max_answer_chars:
        errors.append("answer_summary exceeds policy length limit")
    if len(output.claims) > max_claims:
        errors.append("claims exceed policy count limit")

    combined_text = " ".join(
        [
            output.answer_summary,
            output.uncertainty,
            *output.contradictions,
            *output.limitations,
            *(claim.claim_text for claim in output.claims),
        ]
    )
    for pattern in PATIENT_SPECIFIC_PATTERNS:
        if pattern.search(combined_text):
            errors.append("output contains prohibited patient-specific content")
            break

    citations = citation_index_from_context(context)
    hashes = chunk_hashes or {
        citation_id: record.excerpt_sha256 for citation_id, record in citations.items()
    }

    for index, claim in enumerate(output.claims, start=1):
        if not claim.claim_text.strip():
            errors.append(f"claim {index} is empty")
        if claim.support == "supported" and not claim.citation_ids:
            errors.append(f"supported claim {index} is missing citations")

        cited_excerpts: list[str] = []
        for citation_id in claim.citation_ids:
            record = citations.get(citation_id)
            if record is None:
                continue
            expected_hash = hashes.get(citation_id, record.excerpt_sha256)
            if record.excerpt_sha256 != expected_hash:
                errors.append(f"cited chunk hash mismatch for {citation_id}")
            cited_excerpts.append(record.excerpt)

        overlap = _claim_overlap_ratio(claim.claim_text, tuple(cited_excerpts))
        if claim.support == "supported" and overlap < MIN_SUPPORTED_OVERLAP_ERROR:
            errors.append(f"supported claim {index} lacks evidence overlap")
        elif claim.support == "mixed" and overlap < MIN_MIXED_OVERLAP_WARNING:
            warnings.append(
                ValidationWarning(
                    code="low_lexical_overlap",
                    message=f"mixed claim {index} has low lexical overlap with cited excerpts",
                )
            )

    if output.abstained and output.contradictions:
        warnings.append(
            ValidationWarning(
                code="abstained_with_contradictions",
                message="abstained answer still lists contradictions",
            )
        )

    return SynthesisValidationResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _claim_overlap_ratio(claim_text: str, excerpts: tuple[str, ...]) -> float:
    claim_tokens = _token_set(claim_text)
    if not claim_tokens:
        return 0.0
    evidence_tokens: set[str] = set()
    for excerpt in excerpts:
        evidence_tokens |= _token_set(excerpt)
    if not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def _token_set(text: str) -> set[str]:
    return {token for token in _normalize_text(text).split() if len(token) > 2}


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
