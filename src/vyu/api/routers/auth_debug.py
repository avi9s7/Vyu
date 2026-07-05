from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.vyu.api.dependencies import get_db_session, get_request_principal
from src.vyu.auth.principal import RequestPrincipal


def create_auth_debug_router() -> APIRouter:
    router = APIRouter(prefix="/debug", tags=["debug"], include_in_schema=False)

    @router.get("/whoami")
    def whoami(
        principal: RequestPrincipal = Depends(get_request_principal),
    ) -> dict[str, str]:
        return {
            "user_id": str(principal.user_id),
            "tenant_id": str(principal.tenant_id),
            "workspace_id": str(principal.workspace_id),
            "role": principal.role,
            "authentication_method": principal.authentication_method,
        }

    @router.get("/tenant-resource/{resource_tenant_id}")
    def tenant_resource(
        resource_tenant_id: str,
        principal: RequestPrincipal = Depends(get_request_principal),
        session: Session = Depends(get_db_session),
    ) -> dict[str, str]:
        del session
        if resource_tenant_id != str(principal.tenant_id):
            from src.vyu.api.exceptions import ApiError

            raise ApiError(
                status_code=404,
                code="not_found",
                message="The requested resource was not found.",
            )
        return {"resource_id": str(uuid4()), "tenant_id": resource_tenant_id}

    return router
