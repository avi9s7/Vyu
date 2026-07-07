from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.api.exceptions import ApiError
from src.vyu.api.schemas.uploads import PresignUploadRequest, PresignUploadResponse
from src.vyu.auth.principal import RequestPrincipal
from src.vyu.ingestion.service import IngestionService, IngestionServiceError


def get_ingestion_service(request: Request) -> IngestionService:
    service = request.app.state.ingestion_service
    assert isinstance(service, IngestionService)
    return service


def create_uploads_router() -> APIRouter:
    router = APIRouter(prefix="/uploads", tags=["uploads"])

    @router.post("/presign", status_code=201, response_model=PresignUploadResponse)
    def create_presigned_upload(
        body: PresignUploadRequest,
        request: Request,
        principal: Annotated[RequestPrincipal, Depends(get_request_principal)],
        session: Annotated[Session, Depends(get_db_session)],
        service: Annotated[IngestionService, Depends(get_ingestion_service)],
    ) -> PresignUploadResponse:
        try:
            return service.create_presigned_upload(
                body=body,
                principal=principal,
                request_id=request.state.request_id,
                trace_id=request.state.trace_id,
                session=session,
            )
        except IngestionServiceError as exc:
            raise ApiError(
                status_code=exc.status_code,
                code=exc.code,
                message=exc.message,
            ) from exc

    return router
