import unittest

from src.vyu.authz import (
    Action,
    AuthorizationPolicy,
    Principal,
    ResourceScope,
    Role,
    WorkspaceMembership,
)


class ProductionAuthorizationTests(unittest.TestCase):
    def test_workspace_member_can_read_artifacts_in_assigned_scope(self):
        policy = AuthorizationPolicy()
        principal = Principal(
            user_id="user-1",
            memberships=(
                WorkspaceMembership(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.RESEARCHER,),
                ),
            ),
        )
        scope = ResourceScope(tenant_id="tenant-a", workspace_id="workspace-a")

        decision = policy.authorize(principal, Action.READ_ARTIFACT, scope)

        self.assertTrue(decision.allowed)
        self.assertEqual("role_allows_action", decision.reason)

    def test_workspace_member_cannot_read_artifacts_across_tenant_or_workspace(self):
        policy = AuthorizationPolicy()
        principal = Principal(
            user_id="user-1",
            memberships=(
                WorkspaceMembership(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.RESEARCHER,),
                ),
            ),
        )

        wrong_tenant = policy.authorize(
            principal,
            Action.READ_ARTIFACT,
            ResourceScope(tenant_id="tenant-b", workspace_id="workspace-a"),
        )
        wrong_workspace = policy.authorize(
            principal,
            Action.READ_ARTIFACT,
            ResourceScope(tenant_id="tenant-a", workspace_id="workspace-b"),
        )

        self.assertFalse(wrong_tenant.allowed)
        self.assertEqual("no_matching_scope", wrong_tenant.reason)
        self.assertFalse(wrong_workspace.allowed)
        self.assertEqual("no_matching_scope", wrong_workspace.reason)

    def test_reviewer_can_review_and_export_but_researcher_cannot_review(self):
        policy = AuthorizationPolicy()
        reviewer = Principal(
            user_id="reviewer-1",
            memberships=(
                WorkspaceMembership(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.REVIEWER,),
                ),
            ),
        )
        researcher = Principal(
            user_id="researcher-1",
            memberships=(
                WorkspaceMembership(
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                    roles=(Role.RESEARCHER,),
                ),
            ),
        )
        scope = ResourceScope(tenant_id="tenant-a", workspace_id="workspace-a")

        self.assertTrue(policy.authorize(reviewer, Action.REVIEW_OUTPUT, scope).allowed)
        self.assertTrue(policy.authorize(reviewer, Action.EXPORT_REPORT, scope).allowed)

        denied = policy.authorize(researcher, Action.REVIEW_OUTPUT, scope)
        self.assertFalse(denied.allowed)
        self.assertEqual("role_missing_action", denied.reason)

    def test_tenant_admin_can_manage_sources_across_tenant_workspaces_only(self):
        policy = AuthorizationPolicy()
        admin = Principal(
            user_id="admin-1",
            memberships=(
                WorkspaceMembership(
                    tenant_id="tenant-a",
                    workspace_id="*",
                    roles=(Role.TENANT_ADMIN,),
                ),
            ),
        )

        allowed = policy.authorize(
            admin,
            Action.MANAGE_SOURCES,
            ResourceScope(tenant_id="tenant-a", workspace_id="workspace-b"),
        )
        denied = policy.authorize(
            admin,
            Action.MANAGE_SOURCES,
            ResourceScope(tenant_id="tenant-b", workspace_id="workspace-a"),
        )

        self.assertTrue(allowed.allowed)
        self.assertFalse(denied.allowed)
        self.assertEqual("no_matching_scope", denied.reason)

    def test_require_raises_permission_error_for_denied_action(self):
        policy = AuthorizationPolicy()
        principal = Principal(user_id="user-1", memberships=())

        with self.assertRaises(PermissionError):
            policy.require(
                principal,
                Action.READ_ARTIFACT,
                ResourceScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            )


if __name__ == "__main__":
    unittest.main()
