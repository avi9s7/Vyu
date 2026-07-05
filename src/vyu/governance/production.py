from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from src.vyu.evidence.methodology import (
    EvidenceMethodologyAssessmentRecord,
    EvidenceMethodologyRunRecord,
)
from src.vyu.generation import CitationValidationResult, EvidenceContext, GroundedAnswer
from src.vyu.governance.box import GovernanceBox, build_governance_box
from src.vyu.governance.trust import TrustScore, calculate_trust_score
from src.vyu.retrieval.production import RetrievalRunRecord


class GovernanceDecisionStatus(StrEnum):
    ALLOWED = "allowed"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class GovernanceExportStatus(StrEnum):
    DRAFT_ONLY = "draft_only"
    EXPORT_ALLOWED = "export_allowed"
    EXPORT_BLOCKED = "export_blocked"
    PENDING_REVIEW = "pending_review"


class TrustScoreRecordStatus(StrEnum):
    COMPLETED = "completed"
    EXTERNAL_PENDING = "external_pending"
    EXTERNAL_ACCEPTED = "external_accepted"
    EXTERNAL_FAILED = "external_failed"
    REVIEWER_OVERRIDDEN = "reviewer_overridden"


@dataclass(frozen=True)
class ProductionTrustScorePolicy:
    policy_id: str
    version: str
    component_weights: dict[str, float]
    review_threshold: int = 80
    block_threshold: int = 45
    export_threshold: int = 80
    unsupported_claims_block_export: bool = True
    retracted_evidence_requires_review: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "component_weights": dict(self.component_weights),
            "review_threshold": self.review_threshold,
            "block_threshold": self.block_threshold,
            "export_threshold": self.export_threshold,
            "unsupported_claims_block_export": self.unsupported_claims_block_export,
            "retracted_evidence_requires_review": self.retracted_evidence_requires_review,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionTrustScorePolicy":
        return cls(
            policy_id=str(payload["policy_id"]),
            version=str(payload["version"]),
            component_weights={
                str(key): float(value)
                for key, value in payload.get("component_weights", {}).items()
            },
            review_threshold=int(payload.get("review_threshold", 80)),
            block_threshold=int(payload.get("block_threshold", 45)),
            export_threshold=int(payload.get("export_threshold", 80)),
            unsupported_claims_block_export=bool(
                payload.get("unsupported_claims_block_export", True)
            ),
            retracted_evidence_requires_review=bool(
                payload.get("retracted_evidence_requires_review", True)
            ),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class ProductionTrustScoreRecord:
    trust_score_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    methodology_run_id: str | None
    status: TrustScoreRecordStatus
    score_version: str
    policy_id: str
    policy_version: str
    overall: int
    components: dict[str, int]
    component_weights: dict[str, float]
    warnings: tuple[str, ...]
    unsupported_claim_ids: tuple[str, ...]
    invalid_citation_ids: tuple[str, ...]
    decision_status: GovernanceDecisionStatus
    export_status: GovernanceExportStatus
    review_required: bool
    review_reasons: tuple[str, ...]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "trust_score_id": self.trust_score_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "methodology_run_id": self.methodology_run_id,
            "status": self.status.value,
            "score_version": self.score_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "overall": self.overall,
            "components": dict(self.components),
            "component_weights": dict(self.component_weights),
            "warnings": list(self.warnings),
            "unsupported_claim_ids": list(self.unsupported_claim_ids),
            "invalid_citation_ids": list(self.invalid_citation_ids),
            "decision_status": self.decision_status.value,
            "export_status": self.export_status.value,
            "review_required": self.review_required,
            "review_reasons": list(self.review_reasons),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionTrustScoreRecord":
        return cls(
            trust_score_id=str(payload["trust_score_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            methodology_run_id=(
                str(payload["methodology_run_id"])
                if payload.get("methodology_run_id") is not None
                else None
            ),
            status=TrustScoreRecordStatus(str(payload["status"])),
            score_version=str(payload["score_version"]),
            policy_id=str(payload["policy_id"]),
            policy_version=str(payload["policy_version"]),
            overall=int(payload["overall"]),
            components={
                str(key): int(value) for key, value in payload.get("components", {}).items()
            },
            component_weights={
                str(key): float(value)
                for key, value in payload.get("component_weights", {}).items()
            },
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            unsupported_claim_ids=tuple(
                str(item) for item in payload.get("unsupported_claim_ids", [])
            ),
            invalid_citation_ids=tuple(
                str(item) for item in payload.get("invalid_citation_ids", [])
            ),
            decision_status=GovernanceDecisionStatus(str(payload["decision_status"])),
            export_status=GovernanceExportStatus(str(payload["export_status"])),
            review_required=bool(payload.get("review_required", False)),
            review_reasons=tuple(str(item) for item in payload.get("review_reasons", [])),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata", {})),
        )

    def as_trust_score(self) -> TrustScore:
        return TrustScore(
            overall=self.overall,
            components=dict(self.components),
            warnings=list(self.warnings),
        )


@dataclass(frozen=True)
class ProductionGovernanceBoxRecord:
    governance_box_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    trust_score_id: str
    methodology_run_id: str | None
    question: str
    output_type: str
    decision_status: GovernanceDecisionStatus
    export_status: GovernanceExportStatus
    human_review_required: bool
    human_review_status: str
    audit_id: str
    governance_policy_version: str
    trust_score_policy_version: str
    citation_coverage: int
    source_quality_summary: dict[str, Any]
    recency_summary: dict[str, Any]
    contradiction_flags: tuple[str, ...]
    unsupported_claim_flags: tuple[str, ...]
    safety_warnings: tuple[str, ...]
    governance_box: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "governance_box_id": self.governance_box_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "trust_score_id": self.trust_score_id,
            "methodology_run_id": self.methodology_run_id,
            "question": self.question,
            "output_type": self.output_type,
            "decision_status": self.decision_status.value,
            "export_status": self.export_status.value,
            "human_review_required": self.human_review_required,
            "human_review_status": self.human_review_status,
            "audit_id": self.audit_id,
            "governance_policy_version": self.governance_policy_version,
            "trust_score_policy_version": self.trust_score_policy_version,
            "citation_coverage": self.citation_coverage,
            "source_quality_summary": dict(self.source_quality_summary),
            "recency_summary": dict(self.recency_summary),
            "contradiction_flags": list(self.contradiction_flags),
            "unsupported_claim_flags": list(self.unsupported_claim_flags),
            "safety_warnings": list(self.safety_warnings),
            "governance_box": dict(self.governance_box),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionGovernanceBoxRecord":
        return cls(
            governance_box_id=str(payload["governance_box_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            trust_score_id=str(payload["trust_score_id"]),
            methodology_run_id=(
                str(payload["methodology_run_id"])
                if payload.get("methodology_run_id") is not None
                else None
            ),
            question=str(payload["question"]),
            output_type=str(payload.get("output_type", "answer")),
            decision_status=GovernanceDecisionStatus(str(payload["decision_status"])),
            export_status=GovernanceExportStatus(str(payload["export_status"])),
            human_review_required=bool(payload.get("human_review_required", False)),
            human_review_status=str(payload.get("human_review_status", "not_required")),
            audit_id=str(payload["audit_id"]),
            governance_policy_version=str(payload["governance_policy_version"]),
            trust_score_policy_version=str(payload["trust_score_policy_version"]),
            citation_coverage=int(payload["citation_coverage"]),
            source_quality_summary=dict(payload.get("source_quality_summary", {})),
            recency_summary=dict(payload.get("recency_summary", {})),
            contradiction_flags=tuple(
                str(item) for item in payload.get("contradiction_flags", [])
            ),
            unsupported_claim_flags=tuple(
                str(item) for item in payload.get("unsupported_claim_flags", [])
            ),
            safety_warnings=tuple(str(item) for item in payload.get("safety_warnings", [])),
            governance_box=dict(payload.get("governance_box", {})),
            created_at=str(payload["created_at"]),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class ReviewerTrustScoreOverrideRecord:
    override_id: str
    trust_score_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    reviewer_id: str
    reviewer_role: str
    original_overall: int
    adjusted_overall: int
    original_decision_status: GovernanceDecisionStatus
    adjusted_decision_status: GovernanceDecisionStatus
    override_reasons: tuple[str, ...]
    comment: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> dict[str, Any]:
        return {
            "override_id": self.override_id,
            "trust_score_id": self.trust_score_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "original_overall": self.original_overall,
            "adjusted_overall": self.adjusted_overall,
            "original_decision_status": self.original_decision_status.value,
            "adjusted_decision_status": self.adjusted_decision_status.value,
            "override_reasons": list(self.override_reasons),
            "comment": self.comment,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ReviewerTrustScoreOverrideRecord":
        return cls(
            override_id=str(payload["override_id"]),
            trust_score_id=str(payload["trust_score_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            reviewer_id=str(payload["reviewer_id"]),
            reviewer_role=str(payload["reviewer_role"]),
            original_overall=int(payload["original_overall"]),
            adjusted_overall=int(payload["adjusted_overall"]),
            original_decision_status=GovernanceDecisionStatus(
                str(payload["original_decision_status"])
            ),
            adjusted_decision_status=GovernanceDecisionStatus(
                str(payload["adjusted_decision_status"])
            ),
            override_reasons=tuple(str(item) for item in payload.get("override_reasons", [])),
            comment=str(payload.get("comment", "")),
            created_at=str(payload["created_at"]),
        )


def default_trust_score_policy(*, created_at: str | None = None) -> ProductionTrustScorePolicy:
    return ProductionTrustScorePolicy(
        policy_id="vyu_trust_score_policy_v1",
        version="trust_score_policy_v1",
        component_weights={
            "citation_coverage": 0.25,
            "citation_faithfulness": 0.20,
            "evidence_strength": 0.15,
            "retrieval_stability": 0.10,
            "conflict_handling": 0.10,
            "bias_completeness": 0.10,
            "source_status": 0.05,
            "audit_completeness": 0.05,
        },
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def build_production_trust_score_record(
    *,
    trust_score_id: str,
    answer: GroundedAnswer,
    context: EvidenceContext,
    validation: CitationValidationResult,
    retrieval_run: RetrievalRunRecord,
    methodology_run: EvidenceMethodologyRunRecord | None = None,
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...] = (),
    policy: ProductionTrustScorePolicy | None = None,
    created_at: str | None = None,
) -> ProductionTrustScoreRecord:
    policy = policy or default_trust_score_policy(created_at=created_at)
    baseline = calculate_trust_score(answer, context, validation)
    components = dict(baseline.components)
    if assessments:
        components["evidence_strength"] = _average(
            assessment.evidence_strength_score for assessment in assessments
        )
        components["bias_completeness"] = _average(
            _bias_completeness(assessment) for assessment in assessments
        )
        components["source_status"] = _average(
            _source_status_from_assessment(assessment) for assessment in assessments
        )
    if methodology_run is not None:
        components["conflict_handling"] = 60 if methodology_run.contradiction_flags else 90
    components["retrieval_stability"] = _retrieval_stability(retrieval_run)
    components["audit_completeness"] = 100 if retrieval_run.run_id and retrieval_run.retrieval_run_id else 40
    components = {key: _bound_int(value) for key, value in components.items()}
    overall = round(
        sum(
            components.get(component, 0) * policy.component_weights.get(component, 0.0)
            for component in policy.component_weights
        )
    )
    unsupported_claim_ids = tuple(validation.uncited_material_claim_ids)
    invalid_citation_ids = tuple(validation.invalid_citation_ids)
    warnings = _dedupe(
        list(baseline.warnings)
        + _methodology_warnings(methodology_run, assessments)
        + _validation_warnings(validation)
    )
    decision_status = _decision_status(
        overall=overall,
        policy=policy,
        warnings=warnings,
        invalid_citation_ids=invalid_citation_ids,
        unsupported_claim_ids=unsupported_claim_ids,
        assessments=assessments,
    )
    export_status = _export_status(
        overall=overall,
        policy=policy,
        decision_status=decision_status,
        unsupported_claim_ids=unsupported_claim_ids,
        invalid_citation_ids=invalid_citation_ids,
    )
    review_reasons = _review_reasons(
        overall=overall,
        policy=policy,
        warnings=warnings,
        decision_status=decision_status,
        export_status=export_status,
    )
    return ProductionTrustScoreRecord(
        trust_score_id=trust_score_id,
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        methodology_run_id=methodology_run.methodology_run_id if methodology_run else None,
        status=TrustScoreRecordStatus.COMPLETED,
        score_version="production_trust_score_v1",
        policy_id=policy.policy_id,
        policy_version=policy.version,
        overall=overall,
        components=components,
        component_weights=dict(policy.component_weights),
        warnings=tuple(warnings),
        unsupported_claim_ids=unsupported_claim_ids,
        invalid_citation_ids=invalid_citation_ids,
        decision_status=decision_status,
        export_status=export_status,
        review_required=decision_status != GovernanceDecisionStatus.ALLOWED,
        review_reasons=tuple(review_reasons),
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        metadata={
            "answer_abstained": answer.abstained,
            "methodology_assessment_count": len(assessments),
            "retrieved_document_count": len(retrieval_run.retrieved_document_ids),
            "score_note": "Explainable heuristic trust score; not clinically validated.",
        },
    )


def build_production_governance_box_record(
    *,
    governance_box_id: str,
    answer: GroundedAnswer,
    context: EvidenceContext,
    retrieval_run: RetrievalRunRecord,
    trust_score_record: ProductionTrustScoreRecord,
    methodology_run: EvidenceMethodologyRunRecord | None = None,
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...] = (),
    sources_searched: tuple[str, ...] = (),
    output_type: str = "answer",
    audit_id: str | None = None,
    created_at: str | None = None,
) -> ProductionGovernanceBoxRecord:
    trust_score = trust_score_record.as_trust_score()
    box: GovernanceBox = build_governance_box(
        question=context.question,
        context=context,
        trust_score=trust_score,
        sources_searched=list(sources_searched),
    )
    citation_coverage = trust_score_record.components.get("citation_coverage", 0)
    contradiction_flags = _dedupe(
        list(methodology_run.contradiction_flags if methodology_run else ())
        + [warning for warning in trust_score_record.warnings if "conflict" in warning.lower()]
    )
    unsupported_claim_flags = tuple(trust_score_record.unsupported_claim_ids)
    human_review_status = (
        "required"
        if trust_score_record.review_required or box.human_review_required
        else "not_required"
    )
    safety_warnings = _dedupe(
        list(trust_score_record.warnings)
        + (["Human review required"] if human_review_status == "required" else [])
    )
    governance_box_payload = box.to_json()
    governance_box_payload.update(
        {
            "audit_id": audit_id or f"audit-{retrieval_run.run_id}",
            "export_status": trust_score_record.export_status.value,
            "decision_status": trust_score_record.decision_status.value,
            "unsupported_claim_ids": list(trust_score_record.unsupported_claim_ids),
            "invalid_citation_ids": list(trust_score_record.invalid_citation_ids),
            "methodology_run_id": methodology_run.methodology_run_id if methodology_run else None,
        }
    )
    return ProductionGovernanceBoxRecord(
        governance_box_id=governance_box_id,
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        trust_score_id=trust_score_record.trust_score_id,
        methodology_run_id=methodology_run.methodology_run_id if methodology_run else None,
        question=answer.question,
        output_type=output_type,
        decision_status=trust_score_record.decision_status,
        export_status=trust_score_record.export_status,
        human_review_required=human_review_status == "required",
        human_review_status=human_review_status,
        audit_id=audit_id or f"audit-{retrieval_run.run_id}",
        governance_policy_version="governance_box_policy_v1",
        trust_score_policy_version=trust_score_record.policy_version,
        citation_coverage=citation_coverage,
        source_quality_summary=_source_quality_summary(assessments),
        recency_summary=_recency_summary(assessments),
        contradiction_flags=tuple(contradiction_flags),
        unsupported_claim_flags=unsupported_claim_flags,
        safety_warnings=tuple(safety_warnings),
        governance_box=governance_box_payload,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        metadata={
            "generated_output_abstained": answer.abstained,
            "governance_note": "Production Governance Box record includes visible trust, citation, review, export, safety, and audit metadata.",
        },
    )


def create_reviewer_trust_score_override(
    *,
    override_id: str,
    trust_score: ProductionTrustScoreRecord,
    reviewer_id: str,
    reviewer_role: str,
    adjusted_overall: int,
    adjusted_decision_status: GovernanceDecisionStatus,
    override_reasons: tuple[str, ...],
    comment: str,
    created_at: str | None = None,
) -> ReviewerTrustScoreOverrideRecord:
    return ReviewerTrustScoreOverrideRecord(
        override_id=override_id,
        trust_score_id=trust_score.trust_score_id,
        run_id=trust_score.run_id,
        tenant_id=trust_score.tenant_id,
        workspace_id=trust_score.workspace_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        original_overall=trust_score.overall,
        adjusted_overall=_bound_int(adjusted_overall),
        original_decision_status=trust_score.decision_status,
        adjusted_decision_status=adjusted_decision_status,
        override_reasons=override_reasons,
        comment=comment,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def apply_reviewer_trust_score_override(
    trust_score: ProductionTrustScoreRecord,
    override: ReviewerTrustScoreOverrideRecord,
) -> ProductionTrustScoreRecord:
    if override.trust_score_id != trust_score.trust_score_id:
        raise ValueError("Reviewer override does not match trust score record.")
    export_status = (
        GovernanceExportStatus.EXPORT_ALLOWED
        if override.adjusted_decision_status == GovernanceDecisionStatus.ALLOWED
        and override.adjusted_overall >= 80
        else GovernanceExportStatus.PENDING_REVIEW
        if override.adjusted_decision_status == GovernanceDecisionStatus.REVIEW_REQUIRED
        else GovernanceExportStatus.EXPORT_BLOCKED
    )
    return ProductionTrustScoreRecord(
        trust_score_id=trust_score.trust_score_id,
        run_id=trust_score.run_id,
        tenant_id=trust_score.tenant_id,
        workspace_id=trust_score.workspace_id,
        retrieval_run_id=trust_score.retrieval_run_id,
        methodology_run_id=trust_score.methodology_run_id,
        status=TrustScoreRecordStatus.REVIEWER_OVERRIDDEN,
        score_version=trust_score.score_version,
        policy_id=trust_score.policy_id,
        policy_version=trust_score.policy_version,
        overall=override.adjusted_overall,
        components=dict(trust_score.components),
        component_weights=dict(trust_score.component_weights),
        warnings=trust_score.warnings,
        unsupported_claim_ids=trust_score.unsupported_claim_ids,
        invalid_citation_ids=trust_score.invalid_citation_ids,
        decision_status=override.adjusted_decision_status,
        export_status=export_status,
        review_required=override.adjusted_decision_status != GovernanceDecisionStatus.ALLOWED,
        review_reasons=override.override_reasons,
        created_at=trust_score.created_at,
        metadata={
            **trust_score.metadata,
            "reviewer_override_id": override.override_id,
            "reviewer_override_comment": override.comment,
        },
    )


def _decision_status(
    *,
    overall: int,
    policy: ProductionTrustScorePolicy,
    warnings: tuple[str, ...],
    invalid_citation_ids: tuple[str, ...],
    unsupported_claim_ids: tuple[str, ...],
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...],
) -> GovernanceDecisionStatus:
    has_retracted = any(assessment.retraction_status == "retracted" for assessment in assessments)
    if overall < policy.block_threshold or invalid_citation_ids:
        return GovernanceDecisionStatus.BLOCKED
    if policy.unsupported_claims_block_export and unsupported_claim_ids:
        return GovernanceDecisionStatus.REVIEW_REQUIRED
    if policy.retracted_evidence_requires_review and has_retracted:
        return GovernanceDecisionStatus.REVIEW_REQUIRED
    if overall < policy.review_threshold or warnings:
        return GovernanceDecisionStatus.REVIEW_REQUIRED
    return GovernanceDecisionStatus.ALLOWED


def _export_status(
    *,
    overall: int,
    policy: ProductionTrustScorePolicy,
    decision_status: GovernanceDecisionStatus,
    unsupported_claim_ids: tuple[str, ...],
    invalid_citation_ids: tuple[str, ...],
) -> GovernanceExportStatus:
    if decision_status == GovernanceDecisionStatus.BLOCKED or invalid_citation_ids:
        return GovernanceExportStatus.EXPORT_BLOCKED
    if unsupported_claim_ids and policy.unsupported_claims_block_export:
        return GovernanceExportStatus.PENDING_REVIEW
    if decision_status == GovernanceDecisionStatus.ALLOWED and overall >= policy.export_threshold:
        return GovernanceExportStatus.EXPORT_ALLOWED
    if decision_status == GovernanceDecisionStatus.REVIEW_REQUIRED:
        return GovernanceExportStatus.PENDING_REVIEW
    return GovernanceExportStatus.DRAFT_ONLY


def _review_reasons(
    *,
    overall: int,
    policy: ProductionTrustScorePolicy,
    warnings: tuple[str, ...],
    decision_status: GovernanceDecisionStatus,
    export_status: GovernanceExportStatus,
) -> list[str]:
    reasons = list(warnings)
    if overall < policy.review_threshold:
        reasons.append(f"Trust score {overall} below review threshold {policy.review_threshold}")
    if decision_status == GovernanceDecisionStatus.BLOCKED:
        reasons.append("Governance decision blocked the output")
    if export_status in {GovernanceExportStatus.EXPORT_BLOCKED, GovernanceExportStatus.PENDING_REVIEW}:
        reasons.append(f"Export status is {export_status.value}")
    return _dedupe(reasons)


def _methodology_warnings(
    methodology_run: EvidenceMethodologyRunRecord | None,
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...],
) -> list[str]:
    warnings: list[str] = []
    if methodology_run is not None:
        warnings.extend(methodology_run.limitation_flags)
        warnings.extend(methodology_run.contradiction_flags)
        if methodology_run.requires_human_review:
            warnings.append("Evidence methodology requires human review")
    for assessment in assessments:
        if assessment.preprint_status:
            warnings.append(f"{assessment.document_id} is a preprint")
        if assessment.retraction_status == "retracted":
            warnings.append(f"{assessment.document_id} is retracted")
        warnings.extend(assessment.bias_flags)
        warnings.extend(assessment.applicability_flags)
        warnings.extend(assessment.missing_information_warnings)
    return warnings


def _validation_warnings(validation: CitationValidationResult) -> list[str]:
    warnings: list[str] = []
    if validation.invalid_citation_ids:
        warnings.append("Invalid citation identifiers detected")
    if validation.uncited_material_claim_ids:
        warnings.append("Uncited material claims detected")
    return warnings


def _bias_completeness(assessment: EvidenceMethodologyAssessmentRecord) -> int:
    if assessment.missing_information_warnings:
        return 55
    if assessment.bias_flags or assessment.applicability_flags:
        return 75
    return 92


def _source_status_from_assessment(assessment: EvidenceMethodologyAssessmentRecord) -> int:
    score = min(assessment.source_reliability_score, assessment.recency_score)
    if assessment.retraction_status == "retracted":
        score = 0
    elif assessment.preprint_status:
        score = min(score, 70)
    return _bound_int(score)


def _retrieval_stability(retrieval_run: RetrievalRunRecord) -> int:
    if not retrieval_run.retrieved_document_ids:
        return 0
    score = 55
    if len(retrieval_run.index_versions) >= 1:
        score += 15
    if retrieval_run.retrieval_mode.startswith("hybrid"):
        score += 15
    if retrieval_run.score_trace:
        score += 10
    if retrieval_run.latency_ms is not None:
        score += 5
    return _bound_int(score)


def _source_quality_summary(
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...]
) -> dict[str, Any]:
    if not assessments:
        return {"assessment_count": 0, "average_source_reliability_score": 0}
    return {
        "assessment_count": len(assessments),
        "average_source_reliability_score": _average(
            assessment.source_reliability_score for assessment in assessments
        ),
        "preprint_count": sum(1 for assessment in assessments if assessment.preprint_status),
        "retracted_count": sum(
            1 for assessment in assessments if assessment.retraction_status == "retracted"
        ),
    }


def _recency_summary(assessments: tuple[EvidenceMethodologyAssessmentRecord, ...]) -> dict[str, Any]:
    if not assessments:
        return {"assessment_count": 0, "average_recency_score": 0}
    return {
        "assessment_count": len(assessments),
        "average_recency_score": _average(
            assessment.recency_score for assessment in assessments
        ),
        "low_recency_count": sum(1 for assessment in assessments if assessment.recency_score < 70),
    }


def _average(values) -> int:
    value_list = [int(value) for value in values]
    if not value_list:
        return 0
    return _bound_int(round(sum(value_list) / len(value_list)))


def _bound_int(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped
