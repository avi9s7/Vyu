from __future__ import annotations

from src.vyu.generation import EvidenceContext, GroundedAnswer
from src.vyu.governance import GovernanceBox, TrustScore


def render_evidence_brief(
    answer: GroundedAnswer,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
) -> str:
    claims = "\n".join(
        f"- {claim.text} ({', '.join(claim.citation_ids)})" for claim in answer.claims
    ) or "- No material claims generated."
    return "\n".join(
        [
            "# Evidence Brief",
            "",
            f"Question: {answer.question}",
            f"Answer: {answer.answer_text}",
            "",
            "Material claims:",
            claims,
            "",
            f"Trust Score: {trust_score.overall}",
            f"Human review: {'Required' if governance_box.human_review_required else 'Not required'}",
            f"Reason: {governance_box.human_review_reason}",
        ]
    )


def render_research_report(
    answer: GroundedAnswer,
    context: EvidenceContext,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
) -> str:
    evidence_lines = "\n".join(
        f"- {item.citation_id}: {item.title} [{item.document_id}/{item.passage_id}]"
        for item in context.items
    ) or "- No evidence included."
    warnings = "\n".join(f"- {warning}" for warning in trust_score.warnings) or "- None"
    return "\n".join(
        [
            "# Research Report",
            "",
            f"Question: {answer.question}",
            "",
            "Answer:",
            answer.answer_text,
            "",
            "Included evidence:",
            evidence_lines,
            "",
            "Governance warnings:",
            warnings,
            "",
            f"Sources searched: {', '.join(governance_box.sources_searched)}",
            f"Trust Score: {trust_score.overall}",
        ]
    )


def render_policy_output(
    answer: GroundedAnswer,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
) -> str:
    return "\n".join(
        [
            "# Policy Output",
            "",
            f"Policy question: {answer.question}",
            f"Recommended stance: {'Defer pending human review' if governance_box.human_review_required else 'Proceed with caution'}",
            f"Human review: {'Required' if governance_box.human_review_required else 'Not required'}",
            f"Review reason: {governance_box.human_review_reason}",
            f"Trust Score: {trust_score.overall}",
            "",
            "Decision support summary:",
            answer.answer_text,
        ]
    )
