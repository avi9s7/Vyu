from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from src.vyu.db.models.tenancy import User
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.db.repositories.tenancy import (
    DuplicateRecordError,
    IdentityUser,
    NewMembership,
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings

ALLOWED_ROLES = {"viewer", "researcher", "reviewer", "admin", "operator"}
ALLOWED_STATUSES = {"active", "suspended", "revoked"}
NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c9")


@dataclass(frozen=True)
class ImportCounts:
    tenants: int = 0
    workspaces: int = 0
    users: int = 0
    memberships: int = 0


def slug_uuid(kind: str, slug: str) -> UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{slug}")


def load_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for tenant in payload.get("tenants", []):
        if tenant.get("status") not in ALLOWED_STATUSES:
            raise ValueError(f"invalid tenant status: {tenant.get('tenant_id')}")
    for workspace in payload.get("workspaces", []):
        if workspace.get("status") not in ALLOWED_STATUSES:
            raise ValueError(f"invalid workspace status: {workspace.get('workspace_id')}")
    for grant in payload.get("membership_grants", []):
        roles = grant.get("roles") or []
        if not roles or any(role not in ALLOWED_ROLES for role in roles):
            raise ValueError(f"invalid membership roles: {grant.get('grant_id')}")
        if grant.get("status") not in ALLOWED_STATUSES:
            raise ValueError(f"invalid membership status: {grant.get('grant_id')}")
    return payload


def import_registry(*, registry: dict[str, Any], apply: bool) -> ImportCounts:
    if not apply:
        return ImportCounts(
            tenants=len(registry.get("tenants", [])),
            workspaces=len(registry.get("workspaces", [])),
            users=len({grant["user_id"] for grant in registry.get("membership_grants", [])}),
            memberships=len(registry.get("membership_grants", [])),
        )

    settings = DatabaseSettings()
    factory = build_session_factory(
        build_engine(
            DatabaseSettings(
                database_url=settings.migration_database_url,
                migration_database_url=settings.migration_database_url,
            )
        )
    )
    counts = ImportCounts()
    tenant_ids: dict[str, UUID] = {}
    workspace_ids: dict[str, UUID] = {}
    user_ids: dict[str, UUID] = {}

    with factory.begin() as session:
        tenancy = TenancyRepository(session)
        for tenant in registry.get("tenants", []):
            tenant_uuid = slug_uuid("tenant", tenant["tenant_id"])
            tenant_ids[tenant["tenant_id"]] = tenant_uuid
            try:
                tenancy.add_tenant(
                    NewTenant(
                        id=tenant_uuid,
                        slug=tenant["tenant_id"],
                        name=tenant["display_name"],
                        status=tenant["status"],
                    )
                )
                counts = ImportCounts(**{**counts.__dict__, "tenants": counts.tenants + 1})
            except DuplicateRecordError:
                pass

        for workspace in registry.get("workspaces", []):
            tenant_uuid = tenant_ids[workspace["tenant_id"]]
            workspace_uuid = slug_uuid("workspace", workspace["workspace_id"])
            workspace_ids[workspace["workspace_id"]] = workspace_uuid

        for grant in registry.get("membership_grants", []):
            user_slug = grant["user_id"]
            if user_slug not in user_ids:
                user_ids[user_slug] = slug_uuid("user", user_slug)

    for workspace in registry.get("workspaces", []):
        tenant_uuid = tenant_ids[workspace["tenant_id"]]
        workspace_uuid = workspace_ids[workspace["workspace_id"]]
        scope = TenantScope(tenant_id=tenant_uuid, workspace_id=workspace_uuid)
        with transaction(factory, scope=scope) as session:
            tenancy = TenancyRepository(session)
            try:
                tenancy.add_workspace(
                    NewWorkspace(
                        id=workspace_uuid,
                        tenant_id=tenant_uuid,
                        slug=workspace["workspace_id"],
                        name=workspace["display_name"],
                        status=workspace["status"],
                    )
                )
                counts = ImportCounts(
                    **{**counts.__dict__, "workspaces": counts.workspaces + 1}
                )
            except DuplicateRecordError:
                pass

    with factory.begin() as session:
        tenancy = TenancyRepository(session)
        for user_slug, user_uuid in user_ids.items():
            existing = session.scalar(select(User).where(User.id == user_uuid))
            try:
                tenancy.upsert_user(
                    IdentityUser(
                        id=user_uuid,
                        issuer="https://governance.local/import",
                        subject=user_slug,
                        email=f"{user_slug}@import.local",
                    )
                )
                if existing is None:
                    counts = ImportCounts(**{**counts.__dict__, "users": counts.users + 1})
            except DuplicateRecordError as exc:
                raise ValueError(f"user identity conflict: {user_slug}") from exc

    for grant in registry.get("membership_grants", []):
        tenant_uuid = tenant_ids[grant["tenant_id"]]
        workspace_uuid = workspace_ids[grant["workspace_id"]]
        user_uuid = user_ids[grant["user_id"]]
        scope = TenantScope(tenant_id=tenant_uuid, workspace_id=workspace_uuid)
        with transaction(factory, scope=scope) as session:
            tenancy = TenancyRepository(session)
            audit = AuditRepository(session)
            try:
                tenancy.add_membership(
                    NewMembership(
                        id=slug_uuid("membership", grant["grant_id"]),
                        tenant_id=tenant_uuid,
                        workspace_id=workspace_uuid,
                        user_id=user_uuid,
                        role=grant["roles"][0],
                        status=grant["status"],
                    )
                )
                counts = ImportCounts(
                    **{**counts.__dict__, "memberships": counts.memberships + 1}
                )
                audit.append(
                    NewAuditEvent(
                        id=uuid.uuid4(),
                        tenant_id=tenant_uuid,
                        workspace_id=workspace_uuid,
                        actor_type="system",
                        actor_id="import_tenant_registry",
                        request_id=f"import-{grant['grant_id']}",
                        event_type="governance.membership.imported",
                        resource_type="membership",
                        resource_id=grant["grant_id"],
                        outcome="success",
                        payload_sha256="0" * 64,
                    )
                )
            except DuplicateRecordError:
                continue

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import tenant governance registry.")
    parser.add_argument("--registry", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    registry = load_registry(args.registry)
    counts = import_registry(registry=registry, apply=args.apply)
    print(
        json.dumps(
            {
                "tenants": counts.tenants,
                "workspaces": counts.workspaces,
                "users": counts.users,
                "memberships": counts.memberships,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
