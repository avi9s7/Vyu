import base64
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from src.vyu.authz import (
    ApiKeyRecord,
    MembershipGrant,
    Role,
    ServiceAccountRecord,
    TenantGovernanceRegistry,
    TenantRecord,
    WorkspaceRecord,
    hash_api_key_secret,
)
from src.vyu.deployment import (
    DeploymentCompositionConfig,
    DeploymentCompositionError,
    DeploymentHttpRequest,
    build_deployment_runtime,
)


class TenantGovernanceProductionOperationTests(unittest.TestCase):
    def test_required_tenant_governance_fails_closed_without_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _composition_config(tmp, require_tenant_governance=True)
            with self.assertRaisesRegex(DeploymentCompositionError, "Tenant governance"):
                build_deployment_runtime(config)

    def test_deployment_runtime_enforces_registry_and_audits_identity_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _write_registry(tmp)
            bundle = build_deployment_runtime(
                _composition_config(
                    tmp,
                    registry_path=registry_path,
                    require_tenant_governance=True,
                )
            )
            token = _jwt(_claims(role=["vyu:reviewer", "vyu:workspace_admin"]))

            response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers={
                        "authorization": f"Bearer {token}",
                        "x-vyu-request-id": "request-governed",
                    },
                    query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
                )
            )

            self.assertEqual(200, response.status_code)
            self.assertEqual("review_queue_loaded", response.body["reason"])
            events = bundle.storage.list_audit_events(event_type="identity_access_decision")
            self.assertEqual(1, len(events))
            payload = events[0].payload
            self.assertTrue(payload["allowed"])
            self.assertEqual("reviewer", payload["identity"]["role"])
            self.assertEqual(["grant-reviewer"], payload["identity"]["governed_grant_ids"])

    def test_deployment_runtime_denies_claimed_workspace_without_active_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _write_registry(tmp)
            bundle = build_deployment_runtime(
                _composition_config(
                    tmp,
                    registry_path=registry_path,
                    require_tenant_governance=True,
                )
            )
            token = _jwt(_claims(workspace_id="workspace-b"))

            response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers={"authorization": f"Bearer {token}"},
                    query={"tenant_id": "tenant-a", "workspace_id": "workspace-b"},
                )
            )

            self.assertEqual(401, response.status_code)
            self.assertEqual("identity_mapping_failed", response.body["reason"])
            self.assertIn("workspace_not_registered", response.body["error"]["detail"])
            events = bundle.storage.list_audit_events(event_type="identity_access_decision")
            self.assertEqual(1, len(events))
            self.assertFalse(events[0].payload["allowed"])

    def test_api_key_authenticates_service_account_through_same_governance_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _write_registry(tmp)
            bundle = build_deployment_runtime(
                _composition_config(
                    tmp,
                    registry_path=registry_path,
                    require_tenant_governance=True,
                    api_key_auth_enabled=True,
                )
            )

            response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers={"x-vyu-api-key": "local-api-secret"},
                    query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
                )
            )
            bad_response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers={"x-vyu-api-key": "bad-secret"},
                    query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
                )
            )

            self.assertEqual(200, response.status_code)
            self.assertEqual("review_queue_loaded", response.body["reason"])
            self.assertEqual(401, bad_response.status_code)
            self.assertEqual("auth_token_invalid", bad_response.body["reason"])

    def test_tenant_admin_routes_operate_registry_without_returning_api_key_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _write_registry(tmp)
            bundle = build_deployment_runtime(
                _composition_config(
                    tmp,
                    registry_path=registry_path,
                    require_tenant_governance=True,
                    api_key_auth_enabled=True,
                )
            )
            admin_token = _jwt(_claims(subject="admin-1", role="vyu:tenant_admin", workspace_id="*"))

            service_account_response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="PUT",
                    path="/v1/admin/service-accounts/svc:new",
                    headers={"authorization": f"Bearer {admin_token}"},
                    json_body={
                        "tenant_id": "tenant-a",
                        "display_name": "New Integration",
                        "allowed_scopes": ["review_queue:read"],
                    },
                )
            )
            key_response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="PUT",
                    path="/v1/admin/api-keys/new-key",
                    headers={"authorization": f"Bearer {admin_token}"},
                    json_body={
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                        "service_account_id": "svc:new",
                        "roles": ["reviewer"],
                        "secret": "new-secret",
                    },
                )
            )
            grant_response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="PUT",
                    path="/v1/admin/membership-grants/new-service-grant",
                    headers={"authorization": f"Bearer {admin_token}"},
                    json_body={
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                        "user_id": "svc:new",
                        "roles": ["reviewer"],
                    },
                )
            )

            self.assertEqual(200, service_account_response.status_code)
            self.assertEqual(200, key_response.status_code)
            self.assertEqual(200, grant_response.status_code)
            api_key_payload = key_response.body["data"]["api_key"]
            self.assertEqual("<redacted>", api_key_payload["secret_hash"])
            self.assertNotIn("new-secret", json.dumps(key_response.body))

            api_key_response = bundle.deployment_adapter.handle(
                DeploymentHttpRequest(
                    method="GET",
                    path="/v1/review-queue",
                    headers={"x-vyu-api-key": "new-secret"},
                    query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
                )
            )
            self.assertEqual(200, api_key_response.status_code)

            admin_events = bundle.storage.list_audit_events(event_type="tenant_governance_admin_action")
            self.assertEqual(3, len(admin_events))


def _write_registry(tmp: str) -> Path:
    path = Path(tmp) / "tenant-governance.json"
    registry = TenantGovernanceRegistry(
        tenants=(
            TenantRecord(
                tenant_id="tenant-a",
                display_name="Tenant A",
                allowed_email_domains=("example.com",),
            ),
        ),
        workspaces=(
            WorkspaceRecord(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                display_name="Workspace A",
            ),
        ),
        membership_grants=(
            MembershipGrant(
                grant_id="grant-reviewer",
                user_id="user-123",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(Role.REVIEWER,),
            ),
            MembershipGrant(
                grant_id="grant-admin",
                user_id="admin-1",
                tenant_id="tenant-a",
                workspace_id="*",
                roles=(Role.TENANT_ADMIN,),
            ),
            MembershipGrant(
                grant_id="grant-service",
                user_id="svc:local",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(Role.REVIEWER,),
            ),
        ),
        service_accounts=(
            ServiceAccountRecord(
                service_account_id="svc:local",
                tenant_id="tenant-a",
                display_name="Local Service",
            ),
        ),
        api_keys=(
            ApiKeyRecord(
                key_id="local-key",
                service_account_id="svc:local",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(Role.REVIEWER,),
                secret_hash=hash_api_key_secret("local-api-secret"),
            ),
        ),
    )
    registry.write(path)
    return path


def _composition_config(
    tmp: str,
    registry_path: Path | None = None,
    require_tenant_governance: bool = False,
    api_key_auth_enabled: bool = False,
) -> DeploymentCompositionConfig:
    return DeploymentCompositionConfig(
        sqlite_db_path=Path(tmp) / "production.sqlite",
        phase_output_dir=Path(tmp) / "outputs",
        token_issuer="https://issuer.example",
        token_audience="vyu-api",
        hs256_secret="test-secret",
        token_leeway_seconds=30,
        request_id_prefix="prod-id-test",
        tenant_governance_registry_path=registry_path,
        require_tenant_governance=require_tenant_governance,
        api_key_auth_enabled=api_key_auth_enabled,
    )


def _claims(subject="user-123", role="vyu:reviewer", workspace_id="workspace-a"):
    now = int(time.time())
    return {
        "iss": "https://issuer.example",
        "aud": "vyu-api",
        "sub": subject,
        "exp": now + 300,
        "iat": now - 30,
        "email": f"{subject}@example.com",
        "email_verified": True,
        "vyu": {
            "tenant_id": "tenant-a",
            "workspace_id": workspace_id,
            "roles": role if isinstance(role, list) else [role],
        },
    }


def _jwt(payload, header=None, secret="test-secret"):
    header = header or {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


def _b64(payload):
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
