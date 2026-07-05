from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from src.vyu.evidence.methodology import (
    EvidenceMethodologyAssessmentRecord,
    EvidenceMethodologyRunRecord,
)
from src.vyu.generation import EvidenceContext, GroundedAnswer
from src.vyu.governance.production import (
    GovernanceDecisionStatus,
    GovernanceExportStatus,
    ProductionGovernanceBoxRecord,
    ProductionTrustScoreRecord,
)
from src.vyu.retrieval.production import RetrievalRunRecord


class ExternalGovernanceStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    ACCEPTED_ASYNC = "accepted_async"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WEBHOOK_REJECTED = "webhook_rejected"


@dataclass(frozen=True)
class ExternalGovernanceProviderConfig:
    provider_id: str
    endpoint_url: str
    webhook_url: str
    request_schema_version: str = "vyu.external_governance.request.v1"
    response_schema_version: str = "vyu.external_governance.response.v1"
    auth_mode: str = "bearer_token"
    auth_secret_ref: str | None = None
    webhook_secret_ref: str | None = None
    timeout_seconds: int = 30
    include_passage_text: bool = False
    include_generated_answer_text: bool = True
    data_minimization_policy: str = "send_governance_metadata_and_selected_evidence_only"
    supported_governance_modes: tuple[str, ...] = ("answer_governance", "report_export")

    def to_json(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "endpoint_url": self.endpoint_url,
            "webhook_url": self.webhook_url,
            "request_schema_version": self.request_schema_version,
            "response_schema_version": self.response_schema_version,
            "auth_mode": self.auth_mode,
            "auth_secret_ref": self.auth_secret_ref,
            "webhook_secret_ref": self.webhook_secret_ref,
            "timeout_seconds": self.timeout_seconds,
            "include_passage_text": self.include_passage_text,
            "include_generated_answer_text": self.include_generated_answer_text,
            "data_minimization_policy": self.data_minimization_policy,
            "supported_governance_modes": list(self.supported_governance_modes),
        }


@dataclass(frozen=True)
class ExternalGovernanceRequestRecord:
    request_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    trust_score_id: str
    governance_box_id: str
    provider_id: str
    endpoint_url: str
    webhook_url: str
    status: ExternalGovernanceStatus
    request_payload_hash: str
    idempotency_key: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sent_at: str | None = None
    external_job_id: str | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "trust_score_id": self.trust_score_id,
            "governance_box_id": self.governance_box_id,
            "provider_id": self.provider_id,
            "endpoint_url": self.endpoint_url,
            "webhook_url": self.webhook_url,
            "status": self.status.value,
            "request_payload_hash": self.request_payload_hash,
            "idempotency_key": self.idempotency_key,
            "payload": dict(self.payload),
            "created_at": self.created_at,
            "sent_at": self.sent_at,
            "external_job_id": self.external_job_id,
            "error": self.error,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ExternalGovernanceRequestRecord":
        return cls(
            request_id=str(payload["request_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            trust_score_id=str(payload["trust_score_id"]),
            governance_box_id=str(payload["governance_box_id"]),
            provider_id=str(payload["provider_id"]),
            endpoint_url=str(payload["endpoint_url"]),
            webhook_url=str(payload["webhook_url"]),
            status=ExternalGovernanceStatus(str(payload["status"])),
            request_payload_hash=str(payload["request_payload_hash"]),
            idempotency_key=str(payload["idempotency_key"]),
            payload=dict(payload.get("payload", {})),
            created_at=str(payload["created_at"]),
            sent_at=(str(payload["sent_at"]) if payload.get("sent_at") is not None else None),
            external_job_id=(
                str(payload["external_job_id"])
                if payload.get("external_job_id") is not None
                else None
            ),
            error=(str(payload["error"]) if payload.get("error") is not None else None),
        )


@dataclass(frozen=True)
class ExternalGovernanceResponseRecord:
    response_id: str
    request_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    trust_score_id: str
    governance_box_id: str
    provider_id: str
    status: ExternalGovernanceStatus
    response_payload_hash: str
    received_at: str
    provider_version: str | None = None
    external_decision_status: GovernanceDecisionStatus | None = None
    external_export_status: GovernanceExportStatus | None = None
    external_review_required: bool | None = None
    webhook_signature_valid: bool | None = None
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "retrieval_run_id": self.retrieval_run_id,
            "trust_score_id": self.trust_score_id,
            "governance_box_id": self.governance_box_id,
            "provider_id": self.provider_id,
            "status": self.status.value,
            "response_payload_hash": self.response_payload_hash,
            "received_at": self.received_at,
            "provider_version": self.provider_version,
            "external_decision_status": self.external_decision_status.value
            if self.external_decision_status is not None
            else None,
            "external_export_status": self.external_export_status.value
            if self.external_export_status is not None
            else None,
            "external_review_required": self.external_review_required,
            "webhook_signature_valid": self.webhook_signature_valid,
            "error": self.error,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ExternalGovernanceResponseRecord":
        return cls(
            response_id=str(payload["response_id"]),
            request_id=str(payload["request_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            trust_score_id=str(payload["trust_score_id"]),
            governance_box_id=str(payload["governance_box_id"]),
            provider_id=str(payload["provider_id"]),
            status=ExternalGovernanceStatus(str(payload["status"])),
            response_payload_hash=str(payload["response_payload_hash"]),
            received_at=str(payload["received_at"]),
            provider_version=(
                str(payload["provider_version"])
                if payload.get("provider_version") is not None
                else None
            ),
            external_decision_status=(
                GovernanceDecisionStatus(str(payload["external_decision_status"]))
                if payload.get("external_decision_status") is not None
                else None
            ),
            external_export_status=(
                GovernanceExportStatus(str(payload["external_export_status"]))
                if payload.get("external_export_status") is not None
                else None
            ),
            external_review_required=(
                bool(payload["external_review_required"])
                if payload.get("external_review_required") is not None
                else None
            ),
            webhook_signature_valid=(
                bool(payload["webhook_signature_valid"])
                if payload.get("webhook_signature_valid") is not None
                else None
            ),
            error=(str(payload["error"]) if payload.get("error") is not None else None),
            payload=dict(payload.get("payload", {})),
        )


class ExternalGovernanceTransport(Protocol):
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        ...


class ExternalGovernanceConnector:
    def __init__(
        self,
        config: ExternalGovernanceProviderConfig,
        transport: ExternalGovernanceTransport,
    ) -> None:
        self.config = config
        self.transport = transport

    def submit(
        self,
        request: ExternalGovernanceRequestRecord,
        *,
        bearer_token: str | None = None,
        sent_at: str | None = None,
    ) -> tuple[ExternalGovernanceRequestRecord, ExternalGovernanceResponseRecord | None]:
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": request.idempotency_key,
            "X-Vyu-Request-Id": request.request_id,
            "X-Vyu-Tenant-Id": request.tenant_id,
            "X-Vyu-Workspace-Id": request.workspace_id,
            "X-Vyu-Governance-Box-Id": request.governance_box_id,
        }
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        try:
            response_payload = self.transport.post_json(
                self.config.endpoint_url,
                request.payload,
                headers,
                self.config.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            failed = replace(
                request,
                status=ExternalGovernanceStatus.FAILED,
                sent_at=sent_at or datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
            return failed, None
        status = _status_from_provider(response_payload)
        sent = replace(
            request,
            status=status,
            sent_at=sent_at or datetime.now(timezone.utc).isoformat(),
            external_job_id=(
                str(response_payload["external_job_id"])
                if response_payload.get("external_job_id") is not None
                else None
            ),
            error=(str(response_payload["error"]) if response_payload.get("error") else None),
        )
        response = _response_from_payload(
            request=sent,
            payload=response_payload,
            status=status,
            received_at=sent.sent_at or datetime.now(timezone.utc).isoformat(),
            webhook_signature_valid=None,
        )
        return sent, response


def build_external_governance_request_record(
    *,
    request_id: str,
    answer: GroundedAnswer,
    context: EvidenceContext,
    retrieval_run: RetrievalRunRecord,
    trust_score: ProductionTrustScoreRecord,
    governance_box: ProductionGovernanceBoxRecord,
    methodology_run: EvidenceMethodologyRunRecord | None,
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...],
    provider_config: ExternalGovernanceProviderConfig,
    created_at: str | None = None,
) -> ExternalGovernanceRequestRecord:
    payload = build_external_governance_payload(
        answer=answer,
        context=context,
        retrieval_run=retrieval_run,
        trust_score=trust_score,
        governance_box=governance_box,
        methodology_run=methodology_run,
        assessments=assessments,
        provider_config=provider_config,
    )
    payload_hash = _stable_json_sha256(payload)
    return ExternalGovernanceRequestRecord(
        request_id=request_id,
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        trust_score_id=trust_score.trust_score_id,
        governance_box_id=governance_box.governance_box_id,
        provider_id=provider_config.provider_id,
        endpoint_url=provider_config.endpoint_url,
        webhook_url=provider_config.webhook_url,
        status=ExternalGovernanceStatus.QUEUED,
        request_payload_hash=payload_hash,
        idempotency_key=f"{retrieval_run.run_id}:{governance_box.governance_box_id}:{payload_hash[:16]}",
        payload=payload,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def build_external_governance_payload(
    *,
    answer: GroundedAnswer,
    context: EvidenceContext,
    retrieval_run: RetrievalRunRecord,
    trust_score: ProductionTrustScoreRecord,
    governance_box: ProductionGovernanceBoxRecord,
    methodology_run: EvidenceMethodologyRunRecord | None,
    assessments: tuple[EvidenceMethodologyAssessmentRecord, ...],
    provider_config: ExternalGovernanceProviderConfig,
) -> dict[str, Any]:
    return {
        "schema_version": provider_config.request_schema_version,
        "provider_id": provider_config.provider_id,
        "webhook_url": provider_config.webhook_url,
        "data_minimization_policy": provider_config.data_minimization_policy,
        "scope": {
            "tenant_id": retrieval_run.tenant_id,
            "workspace_id": retrieval_run.workspace_id,
            "run_id": retrieval_run.run_id,
            "retrieval_run_id": retrieval_run.retrieval_run_id,
        },
        "output": {
            "question": answer.question,
            "answer_text": answer.answer_text
            if provider_config.include_generated_answer_text
            else None,
            "abstained": answer.abstained,
            "claim_count": len(answer.claims),
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text if provider_config.include_generated_answer_text else None,
                    "citation_ids": list(claim.citation_ids),
                    "material": claim.material,
                }
                for claim in answer.claims
            ],
        },
        "evidence": {
            "retrieved_document_ids": list(retrieval_run.retrieved_document_ids),
            "retrieved_passage_ids": list(retrieval_run.retrieved_passage_ids),
            "index_versions": list(retrieval_run.index_versions),
            "retrieval_mode": retrieval_run.retrieval_mode,
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
                    "passage_text": item.passage_text
                    if provider_config.include_passage_text
                    else None,
                }
                for item in context.items
            ],
        },
        "methodology": {
            "methodology_run": methodology_run.to_json() if methodology_run else None,
            "assessments": [assessment.to_json() for assessment in assessments],
        },
        "trust_score": trust_score.to_json(),
        "governance_box": governance_box.to_json(),
    }


def parse_external_governance_webhook(
    *,
    request: ExternalGovernanceRequestRecord,
    payload: dict[str, Any],
    signature: str | None = None,
    webhook_secret: str | None = None,
    received_at: str | None = None,
) -> ExternalGovernanceResponseRecord:
    signature_valid: bool | None = None
    status = _status_from_provider(payload)
    error = payload.get("error")
    if webhook_secret is not None:
        signature_valid = verify_webhook_signature(payload, signature or "", webhook_secret)
        if not signature_valid:
            status = ExternalGovernanceStatus.WEBHOOK_REJECTED
            error = "Invalid webhook signature"
    return _response_from_payload(
        request=request,
        payload=payload,
        status=status,
        received_at=received_at or datetime.now(timezone.utc).isoformat(),
        webhook_signature_valid=signature_valid,
        error=(str(error) if error is not None else None),
    )


def sign_webhook_payload(payload: dict[str, Any], webhook_secret: str) -> str:
    encoded = _stable_json(payload).encode("utf-8")
    return hmac.new(webhook_secret.encode("utf-8"), encoded, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    payload: dict[str, Any],
    signature: str,
    webhook_secret: str,
) -> bool:
    expected = sign_webhook_payload(payload, webhook_secret)
    return hmac.compare_digest(expected, signature)


def _response_from_payload(
    *,
    request: ExternalGovernanceRequestRecord,
    payload: dict[str, Any],
    status: ExternalGovernanceStatus,
    received_at: str,
    webhook_signature_valid: bool | None,
    error: str | None = None,
) -> ExternalGovernanceResponseRecord:
    decision_status = _optional_decision(payload.get("decision_status"))
    export_status = _optional_export_status(payload.get("export_status"))
    return ExternalGovernanceResponseRecord(
        response_id=str(payload.get("response_id", f"response-{request.request_id}-ack")),
        request_id=request.request_id,
        run_id=request.run_id,
        tenant_id=request.tenant_id,
        workspace_id=request.workspace_id,
        retrieval_run_id=request.retrieval_run_id,
        trust_score_id=request.trust_score_id,
        governance_box_id=request.governance_box_id,
        provider_id=request.provider_id,
        status=status,
        response_payload_hash=_stable_json_sha256(payload),
        received_at=received_at,
        provider_version=(
            str(payload["provider_version"]) if payload.get("provider_version") is not None else None
        ),
        external_decision_status=decision_status,
        external_export_status=export_status,
        external_review_required=(
            bool(payload["review_required"])
            if payload.get("review_required") is not None
            else None
        ),
        webhook_signature_valid=webhook_signature_valid,
        error=error,
        payload=dict(payload),
    )


def _status_from_provider(payload: dict[str, Any]) -> ExternalGovernanceStatus:
    provider_status = str(payload.get("status", "accepted")).lower()
    if provider_status in {"succeeded", "completed", "pass", "passed"}:
        return ExternalGovernanceStatus.SUCCEEDED
    if provider_status in {"failed", "error", "blocked"}:
        return ExternalGovernanceStatus.FAILED
    return ExternalGovernanceStatus.ACCEPTED_ASYNC


def _optional_decision(value: Any) -> GovernanceDecisionStatus | None:
    if value is None:
        return None
    try:
        return GovernanceDecisionStatus(str(value))
    except ValueError:
        return None


def _optional_export_status(value: Any) -> GovernanceExportStatus | None:
    if value is None:
        return None
    try:
        return GovernanceExportStatus(str(value))
    except ValueError:
        return None


def _stable_json_sha256(payload: Any) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _stable_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))
