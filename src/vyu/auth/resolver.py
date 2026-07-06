from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from src.vyu.auth.principal import RequestPrincipal
from src.vyu.auth.tokens import VerifiedToken
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.db.repositories.tenancy import IdentityUser, TenancyRepository
from src.vyu.db.session import TenantScope


class AuthorizationError(Exception):
    """Raised when membership or scope authorization fails."""


class PrincipalResolver:
    def resolve(
        self,
        verified: VerifiedToken,
        session: Session,
        *,
        request_id: str,
        trace_id: str,
    ) -> RequestPrincipal:
        tenant_id = UUID(verified.tenant_id)
        workspace_id = UUID(verified.workspace_id)
        scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
        apply_tenant_scope(session, tenant_id=tenant_id, workspace_id=workspace_id)
        tenancy = TenancyRepository(session)
        user = tenancy.upsert_user(
            IdentityUser(
                id=uuid4(),
                issuer=verified.issuer,
                subject=verified.subject,
                email=verified.email,
                email_verified=verified.email_verified,
            )
        )
        membership = tenancy.get_active_membership(user_id=user.id, scope=scope)
        audit = AuditRepository(session)
        if membership is None:
            audit.append(
                NewAuditEvent(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    workspace_id=workspace_id,
                    actor_type="user",
                    actor_id=verified.subject,
                    request_id=request_id,
                    trace_id=trace_id,
                    event_type="identity_access_decision",
                    resource_type="membership",
                    resource_id=f"{verified.tenant_id}:{verified.workspace_id}",
                    outcome="denied",
                    payload_sha256="0" * 64,
                    details={
                        "reason": "inactive_membership",
                        "claimed_roles": list(verified.claimed_roles),
                    },
                )
            )
            raise AuthorizationError("Active membership is required.")
        effective_role = membership.role
        audit.append(
            NewAuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_type="user",
                actor_id=verified.subject,
                request_id=request_id,
                trace_id=trace_id,
                event_type="identity_access_decision",
                resource_type="membership",
                resource_id=str(membership.id),
                outcome="allowed",
                payload_sha256="0" * 64,
                details={
                    "role": effective_role,
                    "claimed_roles": list(verified.claimed_roles),
                },
            )
        )
        return RequestPrincipal(
            user_id=user.id,
            issuer=verified.issuer,
            subject=verified.subject,
            email=verified.email,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            role=effective_role,
            authentication_method=verified.authentication_method,
        )


def apply_tenant_scope(
    session: Session,
    *,
    tenant_id: UUID,
    workspace_id: UUID,
) -> None:
    session.execute(
        text("SELECT set_config('app.tenant_id', :value, true)"),
        {"value": str(tenant_id)},
    )
    session.execute(
        text("SELECT set_config('app.workspace_id', :value, true)"),
        {"value": str(workspace_id)},
    )


def apply_principal_scope(session: Session, principal: RequestPrincipal) -> None:
    apply_tenant_scope(
        session,
        tenant_id=principal.tenant_id,
        workspace_id=principal.workspace_id,
    )


def open_scoped_session(
    factory: sessionmaker[Session],
    principal: RequestPrincipal,
) -> Session:
    session = factory()
    apply_principal_scope(session, principal)
    return session
