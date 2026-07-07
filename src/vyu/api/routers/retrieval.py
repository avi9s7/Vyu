from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.api.exceptions import ApiError
from src.vyu.api.schemas.retrieval import (
    CreateIndexBuildRequest,
    IndexBuildCreatedResponse,
    IndexRecordListResponse,
    ResearchEvidenceListResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.retrieval.service import RetrievalService, RetrievalServiceError


def get_retrieval_service(request: Request) -> RetrievalService:
    service = request.app.state.retrieval_service
    assert isinstance(service, RetrievalService)
    return service


def create_admin_retrieval_router() -> APIRouter:
    router = APIRouter(prefix="/admin/retrieval", tags=["retrieval-admin"])

    @router.post("/indexes/build", status_code=202, response_model=IndexBuildCreatedResponse)
    def build_retrieval_index(
        body: CreateIndexBuildRequest,
        request: Request,
        response: Response,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[RetrievalService, Depends(get_retrieval_service)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> IndexBuildCreatedResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise ApiError(
                status_code=400,
                code="missing_idempotency_key",
                message="Idempotency-Key header is required.",
            )
        try:
            result = service.create_index_build(
                body=body,
                principal=principal,
                idempotency_key=idempotency_key.strip(),
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
        except RetrievalServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc
        response.status_code = 202
        created: IndexBuildCreatedResponse = result
        return created

    @router.get("/indexes", response_model=IndexRecordListResponse)
    def list_retrieval_indexes(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[RetrievalService, Depends(get_retrieval_service)],
        status: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> IndexRecordListResponse:
        del principal
        try:
            indexes: IndexRecordListResponse = service.list_indexes(
                session=session,
                status=status,
                limit=limit,
            )
            return indexes
        except RetrievalServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router


def create_research_evidence_router() -> APIRouter:
    router = APIRouter(prefix="/research", tags=["research"])

    @router.get("/searches/{search_id}/evidence", response_model=ResearchEvidenceListResponse)
    def list_research_search_evidence(
        search_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[RetrievalService, Depends(get_retrieval_service)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> ResearchEvidenceListResponse:
        del principal, cursor
        try:
            evidence: ResearchEvidenceListResponse = service.get_research_evidence(
                search_id=search_id,
                session=session,
                cursor=None,
                limit=limit,
            )
            return evidence
        except RetrievalServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router
