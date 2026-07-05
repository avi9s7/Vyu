from __future__ import annotations

from src.vyu.generation.contracts import (
    AnswerClaim,
    CitationValidationResult,
    EvidenceContext,
    GroundedAnswer,
)


def generate_grounded_answer(context: EvidenceContext, max_claims: int = 3) -> GroundedAnswer:
    usable_items = [item for item in context.items if not item.is_retracted]
    if not usable_items:
        return GroundedAnswer(
            question=context.question,
            answer_text=(
                "Vyu cannot provide a grounded answer because no non-retracted "
                "passage-level evidence was available in the retrieved context."
            ),
            claims=[],
            abstained=True,
            abstention_reason="insufficient_non_retracted_evidence",
        )

    claims: list[AnswerClaim] = []
    for index, item in enumerate(usable_items[:max_claims], start=1):
        claim_text = _claim_from_item(item.title, item.passage_text)
        claims.append(
            AnswerClaim(
                claim_id=f"CLM-{index:03d}",
                text=claim_text,
                citation_ids=[item.citation_id],
            )
        )

    citation_summary = "; ".join(
        f"{claim.text} [{', '.join(claim.citation_ids)}]" for claim in claims
    )
    return GroundedAnswer(
        question=context.question,
        answer_text=(
            f"Based on the retrieved synthetic evidence, {citation_summary}. "
            "This is a POC-generated answer and requires human review before use."
        ),
        claims=claims,
        abstained=False,
    )


def validate_citations(
    answer: GroundedAnswer, context: EvidenceContext
) -> CitationValidationResult:
    valid_citation_ids = context.citation_ids
    invalid: list[str] = []
    uncited_material_claims: list[str] = []

    for claim in answer.claims:
        if claim.material and not claim.citation_ids:
            uncited_material_claims.append(claim.claim_id)
        for citation_id in claim.citation_ids:
            if citation_id not in valid_citation_ids:
                invalid.append(citation_id)

    unique_invalid = sorted(set(invalid))
    unique_uncited = sorted(set(uncited_material_claims))
    return CitationValidationResult(
        valid=not unique_invalid and not unique_uncited,
        invalid_citation_ids=unique_invalid,
        uncited_material_claim_ids=unique_uncited,
    )


def _claim_from_item(title: str, passage_text: str) -> str:
    first_sentence = passage_text.split(".")[0].strip()
    if first_sentence:
        return first_sentence
    return f"Retrieved evidence from {title}"
