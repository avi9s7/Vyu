from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.api.exceptions import ApiError
from src.vyu.api.schemas.research import (
    CreateResearchSearchRequest,
    ResearchCancelResponse,
    ResearchEventListResponse,
    ResearchSearchCreatedResponse,
    ResearchSearchDetail,
    ResearchSearchListResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.research.service import ResearchService, ResearchServiceError


def get_research_service(request: Request) -> ResearchService:
    service = request.app.state.research_service
    assert isinstance(service, ResearchService)
    return service


def create_research_router() -> APIRouter:
    router = APIRouter(prefix="/research", tags=["research"])

    @router.post("/searches", status_code=202, response_model=ResearchSearchCreatedResponse)
    def create_research_search(
        body: CreateResearchSearchRequest,
        request: Request,
        response: Response,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[ResearchService, Depends(get_research_service)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ResearchSearchCreatedResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise ApiError(
                status_code=400,
                code="missing_idempotency_key",
                message="Idempotency-Key header is required.",
            )
        try:
            result = service.create_search(
                body=body,
                principal=principal,
                idempotency_key=idempotency_key.strip(),
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
        except ResearchServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc
        response.status_code = 202
        return result

    @router.get("/searches", response_model=ResearchSearchListResponse)
    def list_research_searches(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[ResearchService, Depends(get_research_service)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ResearchSearchListResponse:
        del principal
        try:
            return service.list_searches(cursor=cursor, limit=limit, session=session)
        except ResearchServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.get("/searches/{search_id}", response_model=ResearchSearchDetail)
    def get_research_search(
        search_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[ResearchService, Depends(get_research_service)],
    ) -> ResearchSearchDetail:
        del principal
        try:
            return service.get_search(search_id=search_id, session=session)
        except ResearchServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.get("/searches/{search_id}/events", response_model=ResearchEventListResponse)
    def list_research_search_events(
        search_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[ResearchService, Depends(get_research_service)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ResearchEventListResponse:
        del principal
        try:
            return service.list_events(
                search_id=search_id,
                cursor=cursor,
                limit=limit,
                session=session,
            )
        except ResearchServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    @router.post("/searches/{search_id}/cancel", response_model=ResearchCancelResponse)
    def cancel_research_search(
        search_id: UUID,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[ResearchService, Depends(get_research_service)],
    ) -> ResearchCancelResponse:
        try:
            return service.cancel_search(
                search_id=search_id,
                principal=principal,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
        except ResearchServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router
