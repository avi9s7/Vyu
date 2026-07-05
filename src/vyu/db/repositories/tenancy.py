from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.vyu.db.models.tenancy import Membership, Tenant, User, Workspace
from src.vyu.db.session import TenantScope


class TenancyRepositoryError(Exception):
    """Base tenancy repository error."""


class DuplicateRecordError(TenancyRepositoryError):
    """Raised when a unique constraint would be violated."""


@dataclass(frozen=True)
class TenantRecord:
    id: UUID
    slug: str
    name: str
    status: str


@dataclass(frozen=True)
class WorkspaceRecord:
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    status: str


@dataclass(frozen=True)
class UserRecord:
    id: UUID
    issuer: str
    subject: str
    email: str
    email_verified: bool
    active: bool


@dataclass(frozen=True)
class MembershipRecord:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    status: str


@dataclass(frozen=True)
class NewTenant:
    id: UUID
    slug: str
    name: str
    status: str = "active"


@dataclass(frozen=True)
class NewWorkspace:
    id: UUID
    tenant_id: UUID
    slug: str
    name: str
    status: str = "active"


@dataclass(frozen=True)
class IdentityUser:
    id: UUID
    issuer: str
    subject: str
    email: str
    email_verified: bool = False
    active: bool = True


@dataclass(frozen=True)
class NewMembership:
    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    status: str = "active"


class TenancyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_tenant(self, record: NewTenant) -> TenantRecord:
        row = Tenant(id=record.id, slug=record.slug, name=record.name, status=record.status)
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError("tenant already exists") from exc
        return TenantRecord(id=row.id, slug=row.slug, name=row.name, status=row.status)

    def add_workspace(self, record: NewWorkspace) -> WorkspaceRecord:
        row = Workspace(
            id=record.id,
            tenant_id=record.tenant_id,
            slug=record.slug,
            name=record.name,
            status=record.status,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError("workspace already exists") from exc
        return WorkspaceRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            slug=row.slug,
            name=row.name,
            status=row.status,
        )

    def upsert_user(self, record: IdentityUser) -> UserRecord:
        existing = self._session.scalar(
            select(User).where(User.issuer == record.issuer, User.subject == record.subject)
        )
        if existing is not None:
            if (
                existing.email != record.email
                or existing.email_verified != record.email_verified
                or existing.active != record.active
            ):
                raise DuplicateRecordError("user identity conflict")
            return UserRecord(
                id=existing.id,
                issuer=existing.issuer,
                subject=existing.subject,
                email=existing.email,
                email_verified=existing.email_verified,
                active=existing.active,
            )
        row = User(
            id=record.id,
            issuer=record.issuer,
            subject=record.subject,
            email=record.email,
            email_verified=record.email_verified,
            active=record.active,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError("user already exists") from exc
        return UserRecord(
            id=row.id,
            issuer=row.issuer,
            subject=row.subject,
            email=row.email,
            email_verified=row.email_verified,
            active=row.active,
        )

    def add_membership(self, record: NewMembership) -> MembershipRecord:
        row = Membership(
            id=record.id,
            tenant_id=record.tenant_id,
            workspace_id=record.workspace_id,
            user_id=record.user_id,
            role=record.role,
            status=record.status,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            raise DuplicateRecordError("membership already exists") from exc
        return MembershipRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            workspace_id=row.workspace_id,
            user_id=row.user_id,
            role=row.role,
            status=row.status,
        )

    def get_active_membership(
        self, *, user_id: UUID, scope: TenantScope
    ) -> MembershipRecord | None:
        row = self._session.scalar(
            select(Membership)
            .join(Tenant, Tenant.id == Membership.tenant_id)
            .join(Workspace, Workspace.id == Membership.workspace_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.user_id == user_id,
                Membership.tenant_id == scope.tenant_id,
                Membership.workspace_id == scope.workspace_id,
                Membership.status == "active",
                Tenant.status == "active",
                Workspace.status == "active",
                User.active.is_(True),
            )
        )
        if row is None:
            return None
        return MembershipRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            workspace_id=row.workspace_id,
            user_id=row.user_id,
            role=row.role,
            status=row.status,
        )
