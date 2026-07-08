from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.vyu.api.schemas.synthesis import (
    MODEL_POLICY_ACTIVATE_ROUTE,
    PROMPT_TEMPLATE_ACTIVATE_ROUTE,
    ActivationResponse,
    AnswerCitationItem,
    AnswerClaimItem,
    AnswerVersionLinks,
    ModelGatewayOverviewResponse,
    ModelPolicyListResponse,
    ModelPolicySummary,
    PromptTemplateListResponse,
    PromptTemplateSummary,
    ProviderHealthItem,
    ResearchAnswerResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.jobs.contracts import IdempotencyConflict, IdempotencyRequest
from src.vyu.jobs.models import ResearchRun
from src.vyu.jobs.repository import JobRepository
from src.vyu.model_gateway.gateway import ModelGateway
from src.vyu.retrieval.models import RetrievalIndex, RetrievalRun
from src.vyu.synthesis.repository import ModelSynthesisRepository
from src.vyu.synthesis.settings import SynthesisApiSettings


class SynthesisApiServiceError(Exception):
    def __init__(self, *, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SynthesisAnswerNotFound(SynthesisApiServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="not_found",
            message="The requested resource was not found.",
            status_code=404,
        )


class SynthesisResearchNotFound(SynthesisApiServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="not_found",
            message="The requested resource was not found.",
            status_code=404,
        )


class SynthesisForbidden(SynthesisApiServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="forbidden",
            message="Admin permission is required for this operation.",
            status_code=403,
        )


class SynthesisIdempotencyConflict(SynthesisApiServiceError):
    def __init__(self) -> None:
        super().__init__(
            code="idempotency_conflict",
            message="Idempotency key was reused with a different request body.",
            status_code=409,
        )


ADMIN_ROLES = frozenset({"admin", "operator"})


@dataclass
class SynthesisApiService:
    settings: SynthesisApiSettings
    repository: ModelSynthesisRepository
    gateway: ModelGateway
    job_repository: JobRepository = JobRepository()

    @classmethod
    def from_settings(
        cls,
        settings: SynthesisApiSettings,
        *,
        gateway: ModelGateway,
        repository: ModelSynthesisRepository | None = None,
    ) -> "SynthesisApiService":
        return cls(
            settings=settings,
            repository=repository or ModelSynthesisRepository(),
            gateway=gateway,
        )

    def get_research_answer(
        self,
        *,
        search_id: UUID,
        version: int | None,
        principal: RequestPrincipal,
        session: Session,
    ) -> ResearchAnswerResponse:
        run = self._get_research_run(session, search_id)
        if run is None:
            raise SynthesisResearchNotFound()

        answer = self.repository.get_answer_for_research_run(
            session,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
            research_run_id=search_id,
            version=version,
        )
        if answer is None:
            raise SynthesisAnswerNotFound()

        model_call = self.repository.get_model_call(session, call_id=answer.model_call_id)
        if model_call is None:
            raise SynthesisAnswerNotFound()

        retrieval_run = session.scalar(
            select(RetrievalRun).where(RetrievalRun.id == answer.retrieval_run_id)
        )
        index_id: str | None = None
        manifest_checksum: str | None = None
        if isinstance(retrieval_run, RetrievalRun):
            index_id = str(retrieval_run.retrieval_index_id)
            index_row = session.scalar(
                select(RetrievalIndex).where(RetrievalIndex.id == retrieval_run.retrieval_index_id)
            )
            if isinstance(index_row, RetrievalIndex):
                manifest_checksum = index_row.manifest_checksum

        claims = [
            AnswerClaimItem(
                ordinal=claim.ordinal,
                claim_text=claim.text,
                support_status=claim.support_status,
                citation_ids=list(claim.citation_ids),
                citations=[
                    AnswerCitationItem(
                        citation_id=citation_id,
                        document_version_id=str(claim.document_version_id)
                        if claim.document_version_id is not None
                        else None,
                        chunk_id=str(claim.chunk_id) if claim.chunk_id is not None else None,
                    )
                    for citation_id in claim.citation_ids
                ],
            )
            for claim in answer.claims
        ]

        return ResearchAnswerResponse(
            answer_id=str(answer.answer_id),
            research_run_id=str(answer.research_run_id),
            retrieval_run_id=str(answer.retrieval_run_id),
            version=answer.version,
            status=answer.status,
            answer_summary=answer.answer_text,
            uncertainty=answer.uncertainty,
            contradictions=[],
            limitations=list(answer.limitations),
            claims=claims,
            model_provider_id=model_call.provider_id,
            model_id=model_call.model_id,
            prompt_version=answer.prompt_version,
            policy_version=model_call.policy_version,
            retrieval_index_id=index_id,
            index_manifest_checksum=manifest_checksum,
            evidence_context_sha256=answer.evidence_context_sha256,
            created_at=answer.created_at,
            links=self._answer_links(search_id, answer.version),
        )

    def list_provider_health(self, *, principal: RequestPrincipal) -> list[ProviderHealthItem]:
        self._require_admin(principal)
        items: list[ProviderHealthItem] = []
        provider_ids = sorted(
            set(self.gateway.generation_adapters) | set(self.gateway.health_adapters)
        )
        for provider_id in provider_ids:
            health = self.gateway.health(provider_id)
            items.append(
                ProviderHealthItem(
                    provider_id=health.provider_id,
                    status=str(health.status),
                    checked_at=health.checked_at,
                    latency_ms=health.latency_ms,
                    safe_code=health.safe_code,
                )
            )
        return items

    def get_gateway_overview(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
    ) -> ModelGatewayOverviewResponse:
        self._require_admin(principal)
        metrics = self.repository.aggregate_model_call_metrics(
            session,
            tenant_id=principal.tenant_id,
            workspace_id=principal.workspace_id,
        )
        active_policy = self.repository.get_active_model_policy(session)
        prompts = self.repository.list_prompt_templates(session)
        active_prompt_count = sum(1 for prompt in prompts if prompt.status == "active")
        return ModelGatewayOverviewResponse(
            metrics={
                "total_calls": metrics.total_calls,
                "succeeded_calls": metrics.succeeded_calls,
                "failed_calls": metrics.failed_calls,
                "blocked_calls": metrics.blocked_calls,
                "total_input_tokens": metrics.total_input_tokens,
                "total_output_tokens": metrics.total_output_tokens,
                "total_estimated_cost_minor": metrics.total_estimated_cost_minor,
                "average_latency_ms": metrics.average_latency_ms,
                "errors_by_code": metrics.errors_by_code,
            },
            active_policy_version=active_policy.version_number if active_policy else None,
            active_prompt_count=active_prompt_count,
            evaluation_status="pending_staging_gate",
        )

    def list_model_policies(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
    ) -> ModelPolicyListResponse:
        self._require_admin(principal)
        items = [
            ModelPolicySummary(
                policy_id=str(policy.policy_id),
                version_number=policy.version_number,
                status=policy.status,
                allowed_providers=list(policy.allowed_providers),
                allowed_models=list(policy.allowed_models),
                use_cases=list(policy.use_cases),
                sha256=policy.sha256,
                approved_by=policy.approved_by,
                approved_at=policy.approved_at,
            )
            for policy in self.repository.list_model_policies(session)
        ]
        return ModelPolicyListResponse(items=items)

    def list_prompt_templates(
        self,
        *,
        principal: RequestPrincipal,
        session: Session,
    ) -> PromptTemplateListResponse:
        self._require_admin(principal)
        items = [
            PromptTemplateSummary(
                template_id=str(prompt.template_id),
                name=prompt.name,
                use_case=prompt.use_case,
                version=prompt.version,
                status=prompt.status,
                sha256=prompt.sha256,
                approved_by=prompt.approved_by,
                approved_at=prompt.approved_at,
                evaluation_status="pending_staging_gate",
            )
            for prompt in self.repository.list_prompt_templates(session)
        ]
        return PromptTemplateListResponse(items=items)

    def activate_model_policy(
        self,
        *,
        policy_id: UUID,
        body: object,
        principal: RequestPrincipal,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> ActivationResponse:
        self._require_admin(principal)
        from src.vyu.api.schemas.synthesis import ActivatePolicyRequest

        if not isinstance(body, ActivatePolicyRequest):
            raise TypeError("body must be ActivatePolicyRequest")
        request_sha256 = _request_sha256(
            {
                "policy_id": str(policy_id),
                "reason": body.reason,
                "approved_evaluation_id": body.approved_evaluation_id,
            }
        )

        def activate() -> tuple[str, str, int]:
            try:
                policy = self.repository.activate_model_policy(session, policy_id=policy_id)
            except KeyError as exc:
                raise SynthesisApiServiceError(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=404,
                ) from exc
            AuditRepository(session).append(
                NewAuditEvent(
                    id=uuid4(),
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    actor_type="user",
                    actor_id=principal.subject,
                    request_id=request_id,
                    trace_id=trace_id,
                    event_type="model_policy_activated",
                    resource_type="model_policy_version",
                    resource_id=str(policy.policy_id),
                    outcome="success",
                    payload_sha256=request_sha256,
                    details={
                        "reason": body.reason,
                        "approved_evaluation_id": body.approved_evaluation_id,
                        "version_number": policy.version_number,
                    },
                )
            )
            session.flush()
            return ("model_policy_version", str(policy.policy_id), 200)

        route = MODEL_POLICY_ACTIVATE_ROUTE.format(policy_id=policy_id)
        return self._idempotent_activation(
            principal=principal,
            route=route,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            approved_evaluation_id=body.approved_evaluation_id,
            activate=activate,
            session=session,
        )

    def activate_prompt_template(
        self,
        *,
        template_id: UUID,
        body: object,
        principal: RequestPrincipal,
        idempotency_key: str,
        request_id: str,
        trace_id: str,
        session: Session,
    ) -> ActivationResponse:
        self._require_admin(principal)
        from src.vyu.api.schemas.synthesis import ActivatePromptRequest

        if not isinstance(body, ActivatePromptRequest):
            raise TypeError("body must be ActivatePromptRequest")
        request_sha256 = _request_sha256(
            {
                "template_id": str(template_id),
                "reason": body.reason,
                "approved_evaluation_id": body.approved_evaluation_id,
            }
        )

        def activate() -> tuple[str, str, int]:
            try:
                prompt = self.repository.activate_prompt_template(
                    session, template_id=template_id
                )
            except KeyError as exc:
                raise SynthesisApiServiceError(
                    code="not_found",
                    message="The requested resource was not found.",
                    status_code=404,
                ) from exc
            AuditRepository(session).append(
                NewAuditEvent(
                    id=uuid4(),
                    tenant_id=principal.tenant_id,
                    workspace_id=principal.workspace_id,
                    actor_type="user",
                    actor_id=principal.subject,
                    request_id=request_id,
                    trace_id=trace_id,
                    event_type="prompt_template_activated",
                    resource_type="prompt_template",
                    resource_id=str(prompt.template_id),
                    outcome="success",
                    payload_sha256=request_sha256,
                    details={
                        "reason": body.reason,
                        "approved_evaluation_id": body.approved_evaluation_id,
                        "name": prompt.name,
                        "version": prompt.version,
                    },
                )
            )
            session.flush()
            return ("prompt_template", str(prompt.template_id), 200)

        route = PROMPT_TEMPLATE_ACTIVATE_ROUTE.format(template_id=template_id)
        return self._idempotent_activation(
            principal=principal,
            route=route,
            idempotency_key=idempotency_key,
            request_sha256=request_sha256,
            approved_evaluation_id=body.approved_evaluation_id,
            activate=activate,
            session=session,
        )

    def _idempotent_activation(
        self,
        *,
        principal: RequestPrincipal,
        route: str,
        idempotency_key: str,
        request_sha256: str,
        approved_evaluation_id: str,
        activate: object,
        session: Session,
    ) -> ActivationResponse:
        expires_at = datetime.now(tz=UTC) + timedelta(hours=self.settings.idempotency_ttl_hours)
        idempotency_request = IdempotencyRequest(
            tenant_id=principal.tenant_id,
            actor_id=principal.subject,
            route=route,
            key=idempotency_key,
            request_sha256=request_sha256,
            expires_at=expires_at,
        )
        try:
            result = self.job_repository.get_or_create_idempotent(
                idempotency_request,
                activate,  # type: ignore[arg-type]
                session,
            )
        except IdempotencyConflict as exc:
            raise SynthesisIdempotencyConflict() from exc
        return ActivationResponse(
            resource_id=result.resource_id,
            status="active",
            approved_evaluation_id=approved_evaluation_id,
        )

    def _get_research_run(self, session: Session, search_id: UUID) -> ResearchRun | None:
        row = session.scalar(select(ResearchRun).where(ResearchRun.id == search_id))
        return row if isinstance(row, ResearchRun) else None

    def _answer_links(self, search_id: UUID, version: int) -> AnswerVersionLinks:
        search = str(search_id)
        return AnswerVersionLinks(
            self=f"/v1/research/searches/{search}/answer?version={version}",
            research_search=f"/v1/research/searches/{search}",
            review_queue=f"/v1/review-queue?run_id={search}",
            governance=f"/v1/governance/research-runs/{search}",
        )

    def _require_admin(self, principal: RequestPrincipal) -> None:
        if principal.role not in ADMIN_ROLES:
            raise SynthesisForbidden()


def _request_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
