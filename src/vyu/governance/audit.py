from __future__ import annotations

from src.vyu.generation import EvidenceContext, GroundedAnswer
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore


def export_audit_record(
    answer: GroundedAnswer,
    context: EvidenceContext,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
) -> dict[str, object]:
    return {
        "answer": {
            "question": answer.question,
            "answer_text": answer.answer_text,
            "abstained": answer.abstained,
            "abstention_reason": answer.abstention_reason,
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "citation_ids": claim.citation_ids,
                    "material": claim.material,
                }
                for claim in answer.claims
            ],
        },
        "evidence_context": {
            "question": context.question,
            "items": [
                {
                    "citation_id": item.citation_id,
                    "document_id": item.document_id,
                    "passage_id": item.passage_id,
                    "title": item.title,
                    "retrieval_score": item.retrieval_score,
                    "retrieval_source": item.retrieval_source,
                    "is_retracted": item.is_retracted,
                    "is_preprint": item.is_preprint,
                }
                for item in context.items
            ],
        },
        "trust_score": trust_score.to_json(),
        "governance_box": governance_box.to_json(),
    }
