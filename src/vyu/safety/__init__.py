from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.vyu.generation import CitationValidationResult, EvidenceContext, GroundedAnswer


class PromptInjectionRisk(StrEnum):
    LOW = "low"
    HIGH = "high"


class CitationPolicyStatus(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PromptInjectionSignal:
    location: str
    matched_text: str
    citation_id: str | None = None

    def to_json(self) -> dict[str, str | None]:
        return {
            "location": self.location,
            "citation_id": self.citation_id,
            "matched_text": self.matched_text,
        }


@dataclass(frozen=True)
class PromptInjectionReport:
    risk: PromptInjectionRisk
    signals: list[PromptInjectionSignal]

    @property
    def allowed_for_model_context(self) -> bool:
        return self.risk == PromptInjectionRisk.LOW

    def to_json(self) -> dict[str, object]:
        return {
            "risk": self.risk.value,
            "allowed_for_model_context": self.allowed_for_model_context,
            "signals": [signal.to_json() for signal in self.signals],
        }


@dataclass(frozen=True)
class CitationPolicyDecision:
    status: CitationPolicyStatus
    reasons: list[str]

    @property
    def export_allowed(self) -> bool:
        return self.status == CitationPolicyStatus.ALLOWED

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "export_allowed": self.export_allowed,
            "reasons": list(self.reasons),
        }


PROMPT_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore prior instructions",
    "reveal the system prompt",
    "show the system prompt",
    "developer message",
    "system message",
    "call external tool",
    "exfiltrate",
    "leak secrets",
    "bypass policy",
)


def scan_prompt_injection(context: EvidenceContext) -> PromptInjectionReport:
    signals: list[PromptInjectionSignal] = []
    question_match = _first_match(context.question)
    if question_match is not None:
        signals.append(
            PromptInjectionSignal(
                location="question",
                matched_text=question_match,
            )
        )
    for item in context.items:
        item_match = _first_match(item.passage_text)
        if item_match is not None:
            signals.append(
                PromptInjectionSignal(
                    location="evidence",
                    citation_id=item.citation_id,
                    matched_text=item_match,
                )
            )
    risk = PromptInjectionRisk.HIGH if signals else PromptInjectionRisk.LOW
    return PromptInjectionReport(risk=risk, signals=signals)


def evaluate_citation_policy(
    answer: GroundedAnswer,
    validation: CitationValidationResult,
) -> CitationPolicyDecision:
    reasons: list[str] = []
    if validation.invalid_citation_ids:
        reasons.append(
            "Invalid citations: " + ", ".join(validation.invalid_citation_ids)
        )
    if validation.uncited_material_claim_ids:
        reasons.append(
            "Uncited material claims: "
            + ", ".join(validation.uncited_material_claim_ids)
        )
    if not answer.abstained and not answer.claims:
        reasons.append("Non-abstained answer has no material claims.")
    status = CitationPolicyStatus.BLOCKED if reasons else CitationPolicyStatus.ALLOWED
    return CitationPolicyDecision(status=status, reasons=reasons)


def _first_match(text: str) -> str | None:
    lowered = text.lower()
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern in lowered:
            return pattern
    return None


__all__ = [
    "CitationPolicyDecision",
    "CitationPolicyStatus",
    "PromptInjectionReport",
    "PromptInjectionRisk",
    "PromptInjectionSignal",
    "evaluate_citation_policy",
    "scan_prompt_injection",
]
