from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.api.exceptions import ApiError
from src.vyu.api.schemas.evidence_documents import (
    DocumentDetailResponse,
    DocumentEventListResponse,
    DocumentListResponse,
    DocumentVersionDetail,
    DocumentVersionListResponse,
    IngestionJobDetailResponse,
    ReprocessDocumentRequest,
    ReprocessDocumentResponse,
    RetentionRequest,
    RetentionRequestResponse,
)
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.ingestion.library import EvidenceLibraryError, EvidenceLibraryService
from src.vyu.ingestion.settings import IngestionSettings


def get_evidence_library_service(request: Request) -> EvidenceLibraryService:
    service = request.app.state.evidence_library_service
    assert isinstance(service, EvidenceLibraryService)
    return service


def get_ingestion_settings(request: Request) -> IngestionSettings:
    settings = request.app.state.ingestion_settings
    assert isinstance(settings, IngestionSettings)
    return settings


def create_evidence_documents_router() -> APIRouter:
    router = APIRouter(prefix="/evidence-documents", tags=["evidence-documents"])

    @router.get("", response_model=DocumentListResponse)
    def list_evidence_documents(
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
        source_id: Annotated[str | None, Query()] = None,
        status: Annotated[str | None, Query()] = None,
        media_type: Annotated[str | None, Query()] = None,
        created_after: Annotated[datetime | None, Query()] = None,
        created_before: Annotated[datetime | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> DocumentListResponse:
        try:
            return service.list_documents(
                principal=principal,
                session=session,
                source_id=source_id,
                status=status,
                media_type=media_type,
                created_after=created_after,
                created_before=created_before,
                cursor=cursor,
                limit=limit,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.get("/{document_id}", response_model=DocumentDetailResponse)
    def get_evidence_document(
        document_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
    ) -> DocumentDetailResponse:
        try:
            return service.get_document(
                principal=principal,
                session=session,
                document_id=document_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.get("/{document_id}/versions", response_model=DocumentVersionListResponse)
    def list_evidence_document_versions(
        document_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
    ) -> DocumentVersionListResponse:
        try:
            return service.list_versions(
                principal=principal,
                session=session,
                document_id=document_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.get(
        "/{document_id}/versions/{version_id}",
        response_model=DocumentVersionDetail,
    )
    def get_evidence_document_version(
        document_id: UUID,
        version_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
    ) -> DocumentVersionDetail:
        try:
            return service.get_version(
                principal=principal,
                session=session,
                document_id=document_id,
                version_id=version_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.get("/{document_id}/events", response_model=DocumentEventListResponse)
    def list_evidence_document_events(
        document_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> DocumentEventListResponse:
        try:
            return service.list_document_events(
                principal=principal,
                session=session,
                document_id=document_id,
                cursor=cursor,
                limit=limit,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.post(
        "/{document_id}/reprocess",
        status_code=202,
        response_model=ReprocessDocumentResponse,
    )
    def reprocess_evidence_document(
        document_id: UUID,
        body: ReprocessDocumentRequest,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> ReprocessDocumentResponse:
        if not idempotency_key or not idempotency_key.strip():
            raise ApiError(
                status_code=400,
                code="missing_idempotency_key",
                message="Idempotency-Key header is required.",
            )
        try:
            return service.reprocess_document(
                principal=principal,
                session=session,
                document_id=document_id,
                body=body,
                idempotency_key=idempotency_key.strip(),
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    @router.post(
        "/{document_id}/retention-request",
        response_model=RetentionRequestResponse,
    )
    def request_document_retention(
        document_id: UUID,
        body: RetentionRequest,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
    ) -> RetentionRequestResponse:
        try:
            return service.request_retention(
                principal=principal,
                session=session,
                document_id=document_id,
                body=body,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    return router


def create_ingestion_jobs_router() -> APIRouter:
    router = APIRouter(prefix="/ingestion-jobs", tags=["ingestion-jobs"])

    @router.get("/{job_id}", response_model=IngestionJobDetailResponse)
    def get_ingestion_job(
        job_id: UUID,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[EvidenceLibraryService, Depends(get_evidence_library_service)],
    ) -> IngestionJobDetailResponse:
        try:
            return service.get_ingestion_job(
                principal=principal,
                session=session,
                job_id=job_id,
            )
        except EvidenceLibraryError as exc:
            raise _api_error(exc) from exc

    return router


def _api_error(exc: EvidenceLibraryError) -> ApiError:
    return ApiError(status_code=exc.status_code, code=exc.code, message=exc.message)
