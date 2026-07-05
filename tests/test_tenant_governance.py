import tempfile
import unittest
from pathlib import Path

from src.vyu.authn import IdentityMapper, IdentityMappingConfig, IdentityMappingError
from src.vyu.authz import (
    AccessMode,
    MembershipGrant,
    MembershipGrantStatus,
    Role,
    TenantGovernanceRegistry,
    TenantRecord,
    TenantStatus,
    WorkspaceRecord,
    WorkspaceStatus,
)


class TenantGovernanceTests(unittest.TestCase):
    def test_active_workspace_grant_entitles_identity_and_narrows_claimed_role(self):
        registry = _registry(
            grants=(
                MembershipGrant(
                    grant_id="grant-reviewer",
                    user_id="user-123",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.REVIEWER,),
                ),
            )
        )
        mapper = _mapper(registry)

        decision = mapper.map_claims(
            _claims(groups=["vyu:reviewer", "vyu:workspace_admin"])
        )

        self.assertEqual(Role.REVIEWER, decision.mapped_identity.role)
        self.assertEqual(("grant-reviewer",), decision.mapped_identity.governed_grant_ids)
        self.assertEqual(("standard",), decision.mapped_identity.governed_access_modes)
        self.assertEqual(("vyu:reviewer",), decision.mapped_role_claims)

    def test_registry_denies_unregistered_workspace_suspended_tenant_and_bad_email_domain(self):
        registry = _registry(
            tenants=(
                TenantRecord(
                    tenant_id="tenant-a",
                    display_name="Tenant A",
                    allowed_email_domains=("example.com",),
                ),
                TenantRecord(
                    tenant_id="tenant-suspended",
                    display_name="Suspended",
                    status=TenantStatus.SUSPENDED,
                ),
            ),
            grants=(
                MembershipGrant(
                    grant_id="grant-a",
                    user_id="user-123",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.RESEARCHER,),
                ),
            ),
        )

        self.assertEqual(
            "workspace_not_registered",
            registry.evaluate_identity(
                user_id="user-123",
                email="user@example.com",
                tenant_id="tenant-a",
                workspace_id="workspace-b",
                requested_roles=(Role.RESEARCHER,),
            ).reason,
        )
        self.assertEqual(
            "tenant_not_active",
            registry.evaluate_identity(
                user_id="user-123",
                email="user@example.com",
                tenant_id="tenant-suspended",
                workspace_id="workspace-a",
                requested_roles=(Role.RESEARCHER,),
            ).reason,
        )
        self.assertEqual(
            "email_domain_not_allowed",
            registry.evaluate_identity(
                user_id="user-123",
                email="user@external.test",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                requested_roles=(Role.RESEARCHER,),
            ).reason,
        )

    def test_tenant_admin_wildcard_grant_can_map_wildcard_workspace(self):
        registry = _registry(
            grants=(
                MembershipGrant(
                    grant_id="grant-admin",
                    user_id="admin-1",
                    tenant_id="tenant-a",
                    workspace_id="*",
                    roles=(Role.TENANT_ADMIN,),
                ),
            )
        )
        mapper = _mapper(registry)

        decision = mapper.map_claims(
            {
                **_claims(subject="admin-1", groups=["vyu:tenant_admin"]),
                "vyu": {
                    "tenant_id": "tenant-a",
                    "workspace_id": "*",
                    "roles": ["vyu:tenant_admin"],
                },
            }
        )

        self.assertEqual(Role.TENANT_ADMIN, decision.mapped_identity.role)
        self.assertEqual("*", decision.mapped_identity.workspace_id)
        self.assertEqual(("grant-admin",), decision.mapped_identity.governed_grant_ids)

    def test_break_glass_grant_requires_reason_claim(self):
        registry = _registry(
            grants=(
                MembershipGrant(
                    grant_id="grant-break-glass",
                    user_id="user-123",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.WORKSPACE_ADMIN,),
                    access_mode=AccessMode.BREAK_GLASS,
                    reason="temporary incident response",
                ),
            )
        )
        mapper = _mapper(registry)

        with self.assertRaisesRegex(IdentityMappingError, "break_glass_reason_required"):
            mapper.map_claims(_claims(groups=["vyu:workspace_admin"]))

        decision = mapper.map_claims(
            {
                **_claims(groups=["vyu:workspace_admin"]),
                "vyu": {
                    "tenant_id": "tenant-a",
                    "workspace_id": "workspace-a",
                    "roles": ["vyu:workspace_admin"],
                    "break_glass_reason": "incident INC-123",
                },
            }
        )

        self.assertEqual(Role.WORKSPACE_ADMIN, decision.mapped_identity.role)
        self.assertEqual(("break_glass",), decision.mapped_identity.governed_access_modes)
        self.assertEqual("incident INC-123", decision.mapped_identity.break_glass_reason)

    def test_registry_round_trips_json_file_with_statuses_and_grants(self):
        registry = _registry(
            workspaces=(
                WorkspaceRecord(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    display_name="Workspace A",
                    status=WorkspaceStatus.SUSPENDED,
                    data_classification="internal_research",
                ),
            ),
            grants=(
                MembershipGrant(
                    grant_id="grant-expiring",
                    user_id="user-123",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.RESEARCHER, Role.REVIEWER),
                    status=MembershipGrantStatus.SUSPENDED,
                    expires_at="2026-07-01T00:00:00Z",
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tenant-governance.json"
            registry.write(path)
            loaded = TenantGovernanceRegistry.read(path)

        self.assertEqual(registry.to_json(), loaded.to_json())


def _registry(tenants=None, workspaces=None, grants=None):
    return TenantGovernanceRegistry(
        tenants=tenants
        or (
            TenantRecord(
                tenant_id="tenant-a",
                display_name="Tenant A",
                allowed_email_domains=("example.com",),
            ),
        ),
        workspaces=workspaces
        or (
            WorkspaceRecord(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                display_name="Workspace A",
            ),
        ),
        membership_grants=grants or (),
    )


def _mapper(registry):
    return IdentityMapper(
        IdentityMappingConfig(
            trusted_issuers=frozenset({"https://issuer.example"}),
            accepted_audiences=frozenset({"vyu-api"}),
            tenant_governance=registry,
        )
    )


def _claims(subject="user-123", groups=None):
    return {
        "iss": "https://issuer.example",
        "aud": "vyu-api",
        "sub": subject,
        "email": "user@example.com",
        "email_verified": True,
        "vyu": {
            "tenant_id": "tenant-a",
            "workspace_id": "workspace-a",
            "roles": groups or ["vyu:researcher"],
        },
    }


if __name__ == "__main__":
    unittest.main()
