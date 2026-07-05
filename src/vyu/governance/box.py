from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.vyu.generation import EvidenceContext
from src.vyu.governance.trust import TrustScore


@dataclass(frozen=True)
class GovernanceBox:
    question: str
    sources_searched: list[str]
    search_run_at: str
    retrieved_count: int
    included_count: int
    excluded_count: int
    evidence_mix: dict[str, int]
    conflicts: list[str]
    models: dict[str, str]
    policy_versions: dict[str, str]
    human_review_required: bool
    human_review_reason: str
    trust_score: TrustScore

    def to_json(self) -> dict[str, object]:
        return {
            "question": self.question,
            "sources_searched": self.sources_searched,
            "search_run_at": self.search_run_at,
            "retrieved_count": self.retrieved_count,
            "included_count": self.included_count,
            "excluded_count": self.excluded_count,
            "evidence_mix": self.evidence_mix,
            "conflicts": self.conflicts,
            "models": self.models,
            "policy_versions": self.policy_versions,
            "human_review_required": self.human_review_required,
            "human_review_reason": self.human_review_reason,
            "trust_score": self.trust_score.to_json(),
        }


def build_governance_box(
    question: str,
    context: EvidenceContext,
    trust_score: TrustScore,
    sources_searched: list[str],
) -> GovernanceBox:
    conflicts = [
        warning
        for warning in trust_score.warnings
        if "conflicting" in warning.lower() or "conflict" in warning.lower()
    ]
    human_review_required = bool(trust_score.warnings) or trust_score.overall < 80
    human_review_reason = (
        "; ".join(trust_score.warnings)
        if trust_score.warnings
        else "Trust score below governance threshold"
        if human_review_required
        else "No POC governance warnings"
    )
    return GovernanceBox(
        question=question,
        sources_searched=sources_searched,
        search_run_at=datetime.now(timezone.utc).isoformat(),
        retrieved_count=len(context.items),
        included_count=len([item for item in context.items if not item.is_retracted]),
        excluded_count=len([item for item in context.items if item.is_retracted]),
        evidence_mix=_evidence_mix(context),
        conflicts=conflicts,
        models={
            "retriever": "bm25_v1_or_placeholder_dense",
            "generator": "deterministic_grounded_answer_v1",
        },
        policy_versions={
            "answer_prompt": "deterministic_answer_v1",
            "evidence_rules": "evidence_rules_v1",
            "governance_policy": "governance_policy_v1",
        },
        human_review_required=human_review_required,
        human_review_reason=human_review_reason,
        trust_score=trust_score,
    )


def _evidence_mix(context: EvidenceContext) -> dict[str, int]:
    mix: dict[str, int] = {}
    for item in context.items:
        key = "preprint" if item.is_preprint else "retracted" if item.is_retracted else "reviewed"
        mix[key] = mix.get(key, 0) + 1
    return mix
