from __future__ import annotations

from fastapi import APIRouter, Depends

from src.vyu.api.dependencies import get_request_principal
from src.vyu.auth.principal import RequestPrincipal


def create_me_router() -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.get("/me")
    def me(principal: RequestPrincipal = Depends(get_request_principal)) -> dict[str, str]:
        return {
            "user_id": str(principal.user_id),
            "tenant_id": str(principal.tenant_id),
            "workspace_id": str(principal.workspace_id),
            "role": principal.role,
            "authentication_method": principal.authentication_method,
        }

    return router
