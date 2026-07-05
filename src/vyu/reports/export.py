from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable
import uuid

from src.vyu.authz import AuthorizationPolicy, Principal
from src.vyu.generation import EvidenceContext, GroundedAnswer, validate_citations
from src.vyu.governance import GovernanceBox, TrustScore
from src.vyu.reports.templates import (
    render_evidence_brief,
    render_policy_output,
    render_research_report,
)
from src.vyu.review import ReviewTask, evaluate_export_gate
from src.vyu.safety import (
    CitationPolicyDecision,
    PromptInjectionReport,
    evaluate_citation_policy,
    scan_prompt_injection,
)
from src.vyu.storage import ProductionAuditEvent, ProductionStorage


class ReportType(StrEnum):
    EVIDENCE_BRIEF = "evidence_brief"
    RESEARCH_REPORT = "research_report"
    POLICY_OUTPUT = "policy_output"


@dataclass(frozen=True)
class ReportExportResult:
    allowed: bool
    reason: str
    content: str = ""
    details: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "content": self.content,
            "details": self.details,
        }


def export_report(
    principal: Principal,
    report_type: ReportType,
    answer: GroundedAnswer,
    context: EvidenceContext,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
    review_task: ReviewTask,
    policy: AuthorizationPolicy | None = None,
    storage: ProductionStorage | None = None,
    audit_event_id_factory: Callable[[str, str], str] | None = None,
    audit_created_at: str | None = None,
) -> ReportExportResult:
    export_gate = evaluate_export_gate(principal, review_task, policy=policy)
    if not export_gate.allowed:
        result = ReportExportResult(allowed=False, reason=export_gate.reason)
        _record_report_export_decision(
            storage=storage,
            principal=principal,
            report_type=report_type,
            review_task=review_task,
            result=result,
            audit_event_id_factory=audit_event_id_factory,
            audit_created_at=audit_created_at,
        )
        return result

    prompt_report = scan_prompt_injection(context)
    _record_prompt_injection_decision(
        storage=storage,
        review_task=review_task,
        report=prompt_report,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
    if not prompt_report.allowed_for_model_context:
        detail_ids = [
            signal.citation_id or signal.location
            for signal in prompt_report.signals
        ]
        result = ReportExportResult(
            allowed=False,
            reason="prompt_injection_risk",
            details=", ".join(detail_ids),
        )
        _record_report_export_decision(
            storage=storage,
            principal=principal,
            report_type=report_type,
            review_task=review_task,
            result=result,
            audit_event_id_factory=audit_event_id_factory,
            audit_created_at=audit_created_at,
        )
        return result

    citation_decision = evaluate_citation_policy(
        answer,
        validate_citations(answer, context),
    )
    _record_citation_policy_decision(
        storage=storage,
        review_task=review_task,
        decision=citation_decision,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
    if not citation_decision.export_allowed:
        result = ReportExportResult(
            allowed=False,
            reason="citation_policy_blocked",
            details="; ".join(citation_decision.reasons),
        )
        _record_report_export_decision(
            storage=storage,
            principal=principal,
            report_type=report_type,
            review_task=review_task,
            result=result,
            audit_event_id_factory=audit_event_id_factory,
            audit_created_at=audit_created_at,
        )
        return result

    result = ReportExportResult(
        allowed=True,
        reason="export_allowed",
        content=_render_report(report_type, answer, context, trust_score, governance_box),
    )
    _record_report_export_decision(
        storage=storage,
        principal=principal,
        report_type=report_type,
        review_task=review_task,
        result=result,
        audit_event_id_factory=audit_event_id_factory,
        audit_created_at=audit_created_at,
    )
    return result


def _record_report_export_decision(
    storage: ProductionStorage | None,
    principal: Principal,
    report_type: ReportType,
    review_task: ReviewTask,
    result: ReportExportResult,
    audit_event_id_factory: Callable[[str, str], str] | None,
    audit_created_at: str | None,
) -> None:
    if storage is None:
        return
    event_type = "report_export_decision_recorded"
    storage.append_audit_event(
        ProductionAuditEvent(
            event_id=_audit_event_id(
                review_task.run_id,
                event_type,
                audit_event_id_factory,
            ),
            run_id=review_task.run_id,
            event_type=event_type,
            payload={
                "tenant_id": review_task.scope.tenant_id,
                "workspace_id": review_task.scope.workspace_id,
                "review_id": review_task.review_id,
                "principal_user_id": principal.user_id,
                "report_type": report_type.value,
                "allowed": result.allowed,
                "reason": result.reason,
                "details": result.details,
                "content_rendered": bool(result.content),
                "review_status": review_task.status.value,
            },
            created_at=audit_created_at or datetime.now(timezone.utc).isoformat(),
        )
    )


def _record_prompt_injection_decision(
    storage: ProductionStorage | None,
    review_task: ReviewTask,
    report: PromptInjectionReport,
    audit_event_id_factory: Callable[[str, str], str] | None,
    audit_created_at: str | None,
) -> None:
    if storage is None:
        return
    event_type = "prompt_injection_decision_recorded"
    storage.append_audit_event(
        ProductionAuditEvent(
            event_id=_audit_event_id(
                review_task.run_id,
                event_type,
                audit_event_id_factory,
            ),
            run_id=review_task.run_id,
            event_type=event_type,
            payload={
                "tenant_id": review_task.scope.tenant_id,
                "workspace_id": review_task.scope.workspace_id,
                "review_id": review_task.review_id,
                "risk": report.risk.value,
                "allowed_for_model_context": report.allowed_for_model_context,
                "signals": [signal.to_json() for signal in report.signals],
            },
            created_at=audit_created_at or datetime.now(timezone.utc).isoformat(),
        )
    )


def _record_citation_policy_decision(
    storage: ProductionStorage | None,
    review_task: ReviewTask,
    decision: CitationPolicyDecision,
    audit_event_id_factory: Callable[[str, str], str] | None,
    audit_created_at: str | None,
) -> None:
    if storage is None:
        return
    event_type = "citation_policy_decision_recorded"
    storage.append_audit_event(
        ProductionAuditEvent(
            event_id=_audit_event_id(
                review_task.run_id,
                event_type,
                audit_event_id_factory,
            ),
            run_id=review_task.run_id,
            event_type=event_type,
            payload={
                "tenant_id": review_task.scope.tenant_id,
                "workspace_id": review_task.scope.workspace_id,
                "review_id": review_task.review_id,
                "status": decision.status.value,
                "export_allowed": decision.export_allowed,
                "reasons": list(decision.reasons),
            },
            created_at=audit_created_at or datetime.now(timezone.utc).isoformat(),
        )
    )


def _audit_event_id(
    run_id: str,
    event_type: str,
    audit_event_id_factory: Callable[[str, str], str] | None,
) -> str:
    if audit_event_id_factory is not None:
        return audit_event_id_factory(run_id, event_type)
    return f"{run_id}-{event_type}-{uuid.uuid4().hex}"


def _render_report(
    report_type: ReportType,
    answer: GroundedAnswer,
    context: EvidenceContext,
    trust_score: TrustScore,
    governance_box: GovernanceBox,
) -> str:
    if report_type == ReportType.EVIDENCE_BRIEF:
        return render_evidence_brief(answer, trust_score, governance_box)
    if report_type == ReportType.RESEARCH_REPORT:
        return render_research_report(answer, context, trust_score, governance_box)
    if report_type == ReportType.POLICY_OUTPUT:
        return render_policy_output(answer, trust_score, governance_box)
    raise ValueError(f"Unsupported report type: {report_type}")
