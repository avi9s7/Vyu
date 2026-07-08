from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.api.exceptions import ApiError
from src.vyu.api.schemas.synthesis import (
    ActivatePolicyRequest,
    ActivatePromptRequest,
    ActivationResponse,
    ModelGatewayOverviewResponse,
    ModelPolicyListResponse,
    PromptTemplateListResponse,
    ProviderHealthItem,
    ResearchAnswerResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.synthesis.api_service import SynthesisApiService, SynthesisApiServiceError


def get_synthesis_api_service(request: Request) -> SynthesisApiService:
    service = request.app.state.synthesis_api_service
    assert isinstance(service, SynthesisApiService)
    return service


def create_research_answer_router() -> APIRouter:
    router = APIRouter(prefix="/research", tags=["research"])

    @router.get("/searches/{search_id}/answer", response_model=ResearchAnswerResponse)
    def get_research_search_answer(
        search_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
        version: Annotated[int | None, Query(ge=1)] = None,
    ) -> ResearchAnswerResponse:
        try:
            answer: ResearchAnswerResponse = service.get_research_answer(
                search_id=search_id,
                version=version,
                principal=principal,
                session=session,
            )
            return answer
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router


def create_model_gateway_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin/model-gateway", tags=["model-gateway-admin"])

    @router.get("/health", response_model=list[ProviderHealthItem])
    def list_provider_health(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
    ) -> list[ProviderHealthItem]:
        try:
            health: list[ProviderHealthItem] = service.list_provider_health(principal=principal)
            return health
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.get("/overview", response_model=ModelGatewayOverviewResponse)
    def get_model_gateway_overview(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
    ) -> ModelGatewayOverviewResponse:
        try:
            overview: ModelGatewayOverviewResponse = service.get_gateway_overview(
                principal=principal,
                session=session,
            )
            return overview
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.get("/policies", response_model=ModelPolicyListResponse)
    def list_model_policies(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
    ) -> ModelPolicyListResponse:
        try:
            policies: ModelPolicyListResponse = service.list_model_policies(
                principal=principal,
                session=session,
            )
            return policies
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.get("/prompts", response_model=PromptTemplateListResponse)
    def list_prompt_templates(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
    ) -> PromptTemplateListResponse:
        try:
            prompts: PromptTemplateListResponse = service.list_prompt_templates(
                principal=principal,
                session=session,
            )
            return prompts
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.post("/policies/{policy_id}/activate", response_model=ActivationResponse)
    def activate_model_policy(
        policy_id: UUID,
        body: ActivatePolicyRequest,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ActivationResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise ApiError(
                status_code=400,
                code="missing_idempotency_key",
                message="Idempotency-Key header is required.",
            )
        try:
            activated: ActivationResponse = service.activate_model_policy(
                policy_id=policy_id,
                body=body,
                principal=principal,
                idempotency_key=idempotency_key.strip(),
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
            return activated
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.post("/prompts/{template_id}/activate", response_model=ActivationResponse)
    def activate_prompt_template(
        template_id: UUID,
        body: ActivatePromptRequest,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[SynthesisApiService, Depends(get_synthesis_api_service)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ActivationResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise ApiError(
                status_code=400,
                code="missing_idempotency_key",
                message="Idempotency-Key header is required.",
            )
        try:
            activated: ActivationResponse = service.activate_prompt_template(
                template_id=template_id,
                body=body,
                principal=principal,
                idempotency_key=idempotency_key.strip(),
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
            return activated
        except SynthesisApiServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router
