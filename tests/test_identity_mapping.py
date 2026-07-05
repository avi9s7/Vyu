import unittest

from src.vyu.authn import (
    IdentityMapper,
    IdentityMappingConfig,
    IdentityMappingError,
)
from src.vyu.authz import Role
from src.vyu.entrypoints.report_export_routes import ReportExportRouteResponse
from src.vyu.entrypoints.review_queue_routes import ReviewQueueRouteResponse
from src.vyu.entrypoints.service_routes import ServiceRouteRequest, ServiceRouteRuntime


class IdentityMappingTests(unittest.TestCase):
    def test_maps_trusted_claims_to_internal_service_headers(self):
        mapper = _mapper()

        decision = mapper.map_claims(_claims(groups=["vyu:researcher", "vyu:reviewer"]))
        headers = decision.to_service_headers()

        self.assertEqual("user-123", headers["x-vyu-user-id"])
        self.assertEqual("tenant-a", headers["x-vyu-tenant-id"])
        self.assertEqual("workspace-a", headers["x-vyu-workspace-id"])
        self.assertEqual("reviewer", headers["x-vyu-role"])
        self.assertEqual(Role.REVIEWER, decision.mapped_identity.role)
        self.assertEqual(("vyu:reviewer",), decision.mapped_role_claims)

    def test_accepts_nested_claim_paths_and_prefers_highest_mapped_role(self):
        mapper = _mapper(
            IdentityMappingConfig(
                trusted_issuers=frozenset({"https://issuer.example"}),
                accepted_audiences=frozenset({"vyu-api"}),
                tenant_id_claim="org.tenant",
                workspace_id_claim="org.workspace",
                role_claims=("realm.roles",),
            )
        )

        decision = mapper.map_claims(
            {
                "iss": "https://issuer.example",
                "aud": ["other", "vyu-api"],
                "sub": "user-456",
                "org": {"tenant": "tenant-b", "workspace": "*"},
                "realm": {"roles": ["reviewer", "workspace_admin", "unknown"]},
            }
        )

        self.assertEqual(Role.WORKSPACE_ADMIN, decision.mapped_identity.role)
        self.assertEqual(("workspace_admin",), decision.mapped_role_claims)
        self.assertEqual(("unknown",), decision.ignored_role_claims)


    def test_maps_cognito_native_group_and_custom_attributes(self):
        mapper = _mapper()

        decision = mapper.map_claims(
            {
                "iss": "https://issuer.example",
                "aud": "vyu-api",
                "sub": "cognito-user-1",
                "email": "researcher@example.com",
                "email_verified": True,
                "custom:vyu_tenant_id": "tenant-cognito",
                "custom:vyu_workspace_id": "workspace-cognito",
                "cognito:groups": ["researcher", "reviewer"],
            }
        )

        self.assertEqual("tenant-cognito", decision.mapped_identity.tenant_id)
        self.assertEqual("workspace-cognito", decision.mapped_identity.workspace_id)
        self.assertEqual(Role.REVIEWER, decision.mapped_identity.role)
        self.assertEqual(("reviewer",), decision.mapped_role_claims)

    def test_maps_comma_separated_cognito_custom_role_claim(self):
        mapper = _mapper()

        decision = mapper.map_claims(
            {
                "iss": "https://issuer.example",
                "aud": "vyu-api",
                "sub": "cognito-user-2",
                "email": "admin@example.com",
                "email_verified": True,
                "custom:vyu_tenant_id": "tenant-cognito",
                "custom:vyu_workspace_id": "workspace-cognito",
                "custom:vyu_roles": "researcher, workspace_admin",
            }
        )

        self.assertEqual(Role.WORKSPACE_ADMIN, decision.mapped_identity.role)
        self.assertEqual(("workspace_admin",), decision.mapped_role_claims)

    def test_rejects_untrusted_issuer_audience_and_missing_roles(self):
        mapper = _mapper()

        with self.assertRaisesRegex(IdentityMappingError, "Untrusted issuer"):
            mapper.map_claims({**_claims(), "iss": "https://evil.example"})
        with self.assertRaisesRegex(IdentityMappingError, "Audience claim"):
            mapper.map_claims({**_claims(), "aud": "other-api"})
        with self.assertRaisesRegex(IdentityMappingError, "No trusted role"):
            mapper.map_claims(_claims(groups=["external:guest"]))

    def test_can_require_verified_email(self):
        mapper = _mapper(
            IdentityMappingConfig(
                trusted_issuers=frozenset({"https://issuer.example"}),
                accepted_audiences=frozenset({"vyu-api"}),
                require_email_verified=True,
            )
        )

        with self.assertRaisesRegex(IdentityMappingError, "Email verification"):
            mapper.map_claims({**_claims(), "email_verified": False})

    def test_service_runtime_maps_claims_before_delegating(self):
        review_runtime = _ReviewQueueStub()
        runtime = ServiceRouteRuntime(
            review_queue_runtime=review_runtime,
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "mapped-request",
            identity_mapper=_mapper(),
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/review-queue",
                headers={
                    "x-vyu-user-id": "client-spoof",
                    "x-vyu-request-id": "request-claims",
                },
                identity_claims=_claims(groups=["vyu:reviewer"]),
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("ok", response.body["status"])
        delegated_headers = review_runtime.requests[0].headers
        self.assertEqual("user-123", delegated_headers["x-vyu-user-id"])
        self.assertEqual("tenant-a", delegated_headers["x-vyu-tenant-id"])
        self.assertEqual("workspace-a", delegated_headers["x-vyu-workspace-id"])
        self.assertEqual("reviewer", delegated_headers["x-vyu-role"])
        self.assertEqual("request-claims", delegated_headers["x-vyu-request-id"])

    def test_service_runtime_rejects_unmappable_claims_before_delegating(self):
        review_runtime = _ReviewQueueStub()
        runtime = ServiceRouteRuntime(
            review_queue_runtime=review_runtime,
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "mapped-request",
            identity_mapper=_mapper(),
        )

        response = runtime.handle(
            ServiceRouteRequest(
                method="GET",
                path="/v1/review-queue",
                headers={},
                identity_claims={**_claims(), "aud": "wrong-api"},
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )

        self.assertEqual(401, response.status_code)
        self.assertEqual("identity_mapping_failed", response.body["reason"])
        self.assertIn("Audience claim", response.body["error"]["detail"])
        self.assertEqual([], review_runtime.requests)


def _mapper(config=None):
    return IdentityMapper(
        config
        or IdentityMappingConfig(
            trusted_issuers=frozenset({"https://issuer.example"}),
            accepted_audiences=frozenset({"vyu-api"}),
        )
    )


def _claims(groups=None):
    return {
        "iss": "https://issuer.example",
        "aud": "vyu-api",
        "sub": "user-123",
        "email": "user@example.com",
        "email_verified": True,
        "vyu": {
            "tenant_id": "tenant-a",
            "workspace_id": "workspace-a",
            "roles": groups or ["vyu:researcher"],
        },
    }


class _ReviewQueueStub:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return ReviewQueueRouteResponse(
            status_code=200,
            body={"request_id": request.headers["x-vyu-request-id"], "reason": "ok"},
        )


class _ReportExportStub:
    def handle(self, request):
        return ReportExportRouteResponse(status_code=200, body={"reason": "ok"})


if __name__ == "__main__":
    unittest.main()
