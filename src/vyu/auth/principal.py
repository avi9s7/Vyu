from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RequestPrincipal:
    user_id: UUID
    issuer: str
    subject: str
    email: str
    tenant_id: UUID
    workspace_id: UUID
    role: str
    authentication_method: str
