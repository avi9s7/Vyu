from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol

from src.vyu.contracts import LoadedCorpus
from src.vyu.evidence.methodology import (
    EvidenceAssessmentStatus,
    EvidenceMethodologyAssessmentRecord,
    EvidenceMethodologyRuleSet,
    EvidenceStrengthBand,
)
from src.vyu.retrieval.production import RetrievalRunRecord


class ExternalEvidenceGradingStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    ACCEPTED_ASYNC = "accepted_async"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    WEBHOOK_REJECTED = "webhook_rejected"


@dataclass(frozen=True)
class ExternalEvidenceGradingProviderConfig:
    provider_id: str
    endpoint_url: str
    webhook_url: str
    request_schema_version: str = "vyu.external_evidence_grading.request.v1"
    response_schema_version: str = "vyu.external_evidence_grading.response.v1"
    auth_mode: str = "bearer_token"
    auth_secret_ref: str | None = None
    webhook_secret_ref: str | None = None
    timeout_seconds: int = 30
    include_passage_text: bool = True
    max_passages_per_document: int = 3
    data_minimization_policy: str = "send_metadata_and_selected_evidence_passages_only"
    supported_specialties: tuple[str, ...] = ("general_biomedical_research",)

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
            "max_passages_per_document": self.max_passages_per_document,
            "data_minimization_policy": self.data_minimization_policy,
            "supported_specialties": list(self.supported_specialties),
        }


@dataclass(frozen=True)
class ExternalEvidenceGradingRequestRecord:
    request_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    provider_id: str
    endpoint_url: str
    webhook_url: str
    status: ExternalEvidenceGradingStatus
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
    def from_json(cls, payload: dict[str, Any]) -> "ExternalEvidenceGradingRequestRecord":
        return cls(
            request_id=str(payload["request_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            provider_id=str(payload["provider_id"]),
            endpoint_url=str(payload["endpoint_url"]),
            webhook_url=str(payload["webhook_url"]),
            status=ExternalEvidenceGradingStatus(str(payload["status"])),
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
class ExternalEvidenceGradingResponseRecord:
    response_id: str
    request_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    retrieval_run_id: str
    provider_id: str
    status: ExternalEvidenceGradingStatus
    response_payload_hash: str
    received_at: str
    assessment_ids: tuple[str, ...] = ()
    provider_version: str | None = None
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
            "provider_id": self.provider_id,
            "status": self.status.value,
            "response_payload_hash": self.response_payload_hash,
            "received_at": self.received_at,
            "assessment_ids": list(self.assessment_ids),
            "provider_version": self.provider_version,
            "webhook_signature_valid": self.webhook_signature_valid,
            "error": self.error,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ExternalEvidenceGradingResponseRecord":
        return cls(
            response_id=str(payload["response_id"]),
            request_id=str(payload["request_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            retrieval_run_id=str(payload["retrieval_run_id"]),
            provider_id=str(payload["provider_id"]),
            status=ExternalEvidenceGradingStatus(str(payload["status"])),
            response_payload_hash=str(payload["response_payload_hash"]),
            received_at=str(payload["received_at"]),
            assessment_ids=tuple(str(item) for item in payload.get("assessment_ids", [])),
            provider_version=(
                str(payload["provider_version"])
                if payload.get("provider_version") is not None
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


class ExternalEvidenceGradingTransport(Protocol):
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        ...


class ExternalEvidenceGradingConnector:
    def __init__(
        self,
        config: ExternalEvidenceGradingProviderConfig,
        transport: ExternalEvidenceGradingTransport,
    ) -> None:
        self.config = config
        self.transport = transport

    def submit(
        self,
        request: ExternalEvidenceGradingRequestRecord,
        *,
        bearer_token: str | None = None,
        sent_at: str | None = None,
    ) -> tuple[ExternalEvidenceGradingRequestRecord, ExternalEvidenceGradingResponseRecord | None]:
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": request.idempotency_key,
            "X-Vyu-Request-Id": request.request_id,
            "X-Vyu-Tenant-Id": request.tenant_id,
            "X-Vyu-Workspace-Id": request.workspace_id,
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
                status=ExternalEvidenceGradingStatus.FAILED,
                sent_at=sent_at or datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
            return failed, None

        provider_status = str(response_payload.get("status", "accepted")).lower()
        if provider_status in {"succeeded", "completed"}:
            status = ExternalEvidenceGradingStatus.SUCCEEDED
        elif provider_status in {"failed", "error"}:
            status = ExternalEvidenceGradingStatus.FAILED
        else:
            status = ExternalEvidenceGradingStatus.ACCEPTED_ASYNC
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
        response = ExternalEvidenceGradingResponseRecord(
            response_id=f"response-{request.request_id}-ack",
            request_id=request.request_id,
            run_id=request.run_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            retrieval_run_id=request.retrieval_run_id,
            provider_id=request.provider_id,
            status=status,
            response_payload_hash=_stable_json_sha256(response_payload),
            received_at=sent.sent_at or datetime.now(timezone.utc).isoformat(),
            assessment_ids=tuple(
                str(item) for item in response_payload.get("assessment_ids", [])
            ),
            provider_version=(
                str(response_payload["provider_version"])
                if response_payload.get("provider_version") is not None
                else None
            ),
            webhook_signature_valid=None,
            error=sent.error,
            payload=response_payload,
        )
        return sent, response


def build_external_grading_request_record(
    *,
    request_id: str,
    retrieval_run: RetrievalRunRecord,
    corpus: LoadedCorpus,
    document_ids: tuple[str, ...],
    ruleset: EvidenceMethodologyRuleSet,
    provider_config: ExternalEvidenceGradingProviderConfig,
    created_at: str | None = None,
) -> ExternalEvidenceGradingRequestRecord:
    payload = build_external_grading_payload(
        retrieval_run=retrieval_run,
        corpus=corpus,
        document_ids=document_ids,
        ruleset=ruleset,
        provider_config=provider_config,
    )
    payload_hash = _stable_json_sha256(payload)
    return ExternalEvidenceGradingRequestRecord(
        request_id=request_id,
        run_id=retrieval_run.run_id,
        tenant_id=retrieval_run.tenant_id,
        workspace_id=retrieval_run.workspace_id,
        retrieval_run_id=retrieval_run.retrieval_run_id,
        provider_id=provider_config.provider_id,
        endpoint_url=provider_config.endpoint_url,
        webhook_url=provider_config.webhook_url,
        status=ExternalEvidenceGradingStatus.QUEUED,
        request_payload_hash=payload_hash,
        idempotency_key=f"{retrieval_run.run_id}:{retrieval_run.retrieval_run_id}:{payload_hash[:16]}",
        payload=payload,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )


def build_external_grading_payload(
    *,
    retrieval_run: RetrievalRunRecord,
    corpus: LoadedCorpus,
    document_ids: tuple[str, ...],
    ruleset: EvidenceMethodologyRuleSet,
    provider_config: ExternalEvidenceGradingProviderConfig,
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for document_id in document_ids:
        document = corpus.documents[document_id]
        profile = corpus.evidence_profiles[document_id]
        passages = [
            passage
            for passage in corpus.passages.values()
            if passage.document_id == document_id
        ][: provider_config.max_passages_per_document]
        documents.append(
            {
                "document_id": document.document_id,
                "title": document.title,
                "year": document.year,
                "study_design": document.study_design.value,
                "source_type": document.source_type,
                "publication_status": document.publication_status,
                "is_preprint": document.is_preprint,
                "is_retracted": document.is_retracted,
                "population": document.population,
                "intervention": document.intervention,
                "comparator": document.comparator,
                "outcomes": list(document.outcomes),
                "funding_present": bool(profile.funding or document.funding),
                "conflicts_present": bool(profile.conflicts or document.conflicts),
                "evidence_profile": {
                    "bias_flags": list(profile.bias_flags),
                    "applicability_flags": list(profile.applicability_flags),
                    "missing_information_warnings": list(profile.missing_information_warnings),
                    "assessment_confidence": profile.assessment_confidence,
                    "retraction_status": profile.retraction_status,
                    "preprint_status": profile.preprint_status,
                },
                "passages": [
                    {
                        "passage_id": passage.passage_id,
                        "section": passage.section,
                        "page": passage.page,
                        "text": passage.text if provider_config.include_passage_text else None,
                    }
                    for passage in passages
                ],
            }
        )
    return {
        "schema_version": provider_config.request_schema_version,
        "run_id": retrieval_run.run_id,
        "tenant_id": retrieval_run.tenant_id,
        "workspace_id": retrieval_run.workspace_id,
        "retrieval_run_id": retrieval_run.retrieval_run_id,
        "question": retrieval_run.question,
        "topic": retrieval_run.topic,
        "ruleset": ruleset.to_json(),
        "data_minimization": {
            "policy": provider_config.data_minimization_policy,
            "raw_patient_data_included": False,
            "secrets_included": False,
            "selected_passage_text_included": provider_config.include_passage_text,
        },
        "documents": documents,
        "callback": {
            "webhook_url": provider_config.webhook_url,
            "response_schema_version": provider_config.response_schema_version,
        },
    }


def parse_external_grading_webhook(
    *,
    request: ExternalEvidenceGradingRequestRecord,
    raw_body: bytes,
    signature: str | None,
    webhook_secret: str | None,
    received_at: str | None = None,
) -> tuple[ExternalEvidenceGradingResponseRecord, tuple[EvidenceMethodologyAssessmentRecord, ...]]:
    signature_valid = None
    if webhook_secret is not None:
        if signature is None:
            raise PermissionError("Missing evidence-grading webhook signature.")
        signature_valid = verify_webhook_signature(raw_body, signature, webhook_secret)
        if not signature_valid:
            raise PermissionError("Invalid evidence-grading webhook signature.")
    payload = json.loads(raw_body.decode("utf-8"))
    if str(payload.get("request_id")) != request.request_id:
        raise ValueError("Evidence-grading webhook request_id mismatch.")
    status = ExternalEvidenceGradingStatus(
        str(payload.get("status", ExternalEvidenceGradingStatus.SUCCEEDED.value))
    )
    assessments = tuple(
        external_assessment_from_payload(
            item,
            request=request,
            received_at=received_at,
        )
        for item in payload.get("assessments", [])
    )
    response = ExternalEvidenceGradingResponseRecord(
        response_id=str(payload.get("response_id", f"response-{request.request_id}-webhook")),
        request_id=request.request_id,
        run_id=request.run_id,
        tenant_id=request.tenant_id,
        workspace_id=request.workspace_id,
        retrieval_run_id=request.retrieval_run_id,
        provider_id=request.provider_id,
        status=status,
        response_payload_hash=_stable_json_sha256(payload),
        received_at=received_at or datetime.now(timezone.utc).isoformat(),
        assessment_ids=tuple(assessment.assessment_id for assessment in assessments),
        provider_version=(
            str(payload["provider_version"])
            if payload.get("provider_version") is not None
            else None
        ),
        webhook_signature_valid=signature_valid,
        error=(str(payload["error"]) if payload.get("error") else None),
        payload=payload,
    )
    return response, assessments


def external_assessment_from_payload(
    payload: dict[str, Any],
    *,
    request: ExternalEvidenceGradingRequestRecord,
    received_at: str | None = None,
) -> EvidenceMethodologyAssessmentRecord:
    score = int(payload["evidence_strength_score"])
    return EvidenceMethodologyAssessmentRecord(
        assessment_id=str(payload.get("assessment_id", f"external-{request.request_id}-{payload['document_id']}")),
        run_id=request.run_id,
        tenant_id=request.tenant_id,
        workspace_id=request.workspace_id,
        retrieval_run_id=request.retrieval_run_id,
        document_id=str(payload["document_id"]),
        question=str(request.payload.get("question", "")),
        topic=str(request.payload.get("topic", "")),
        ruleset_id=str(request.payload.get("ruleset", {}).get("ruleset_id", "external_ruleset")),
        ruleset_version=str(request.payload.get("ruleset", {}).get("version", "external")),
        specialty=str(request.payload.get("ruleset", {}).get("specialty", "external")),
        status=EvidenceAssessmentStatus.COMPLETED,
        study_design=_study_design_from_payload(payload),
        detected_study_design=_study_design_from_payload(payload),
        evidence_strength_score=score,
        evidence_strength_band=EvidenceStrengthBand(str(payload["evidence_strength_band"])),
        source_reliability_score=int(payload.get("source_reliability_score", score)),
        recency_score=int(payload.get("recency_score", score)),
        population_context_match_score=int(payload.get("population_context_match_score", score)),
        methodology_domain_scores={
            str(key): int(value)
            for key, value in payload.get("methodology_domain_scores", {}).items()
        },
        bias_flags=tuple(str(item) for item in payload.get("bias_flags", [])),
        applicability_flags=tuple(
            str(item) for item in payload.get("applicability_flags", [])
        ),
        limitation_flags=tuple(str(item) for item in payload.get("limitation_flags", [])),
        contradiction_flags=tuple(
            str(item) for item in payload.get("contradiction_flags", [])
        ),
        missing_information_warnings=tuple(
            str(item) for item in payload.get("missing_information_warnings", [])
        ),
        funding=(str(payload["funding"]) if payload.get("funding") is not None else None),
        conflicts=(str(payload["conflicts"]) if payload.get("conflicts") is not None else None),
        retraction_status=str(payload.get("retraction_status", "not_retracted")),
        preprint_status=bool(payload.get("preprint_status", False)),
        assessment_confidence=float(payload.get("assessment_confidence", 0.0)),
        requires_human_review=bool(payload.get("requires_human_review", False)),
        assessment_source="external_provider",
        external_request_id=request.request_id,
        provider_id=request.provider_id,
        created_at=received_at or datetime.now(timezone.utc).isoformat(),
        metadata=dict(payload.get("metadata", {})),
    )


def sign_webhook_payload(raw_body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = sign_webhook_payload(raw_body, secret)
    return hmac.compare_digest(expected, signature)


def _study_design_from_payload(payload: dict[str, Any]):
    from src.vyu.contracts import StudyDesign

    return StudyDesign(str(payload.get("study_design", StudyDesign.UNKNOWN.value)))


def _stable_json_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
