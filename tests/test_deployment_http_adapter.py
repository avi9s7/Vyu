import base64
import hashlib
import hmac
import json
import unittest

from src.vyu.authn import IdentityMapper, IdentityMappingConfig
from src.vyu.deployment import (
    AuthenticationError,
    BearerTokenConfig,
    DeploymentHttpRequest,
    Hs256BearerTokenAuthenticator,
    ServiceDeploymentHttpAdapter,
)
from src.vyu.entrypoints.report_export_routes import ReportExportRouteResponse
from src.vyu.entrypoints.review_queue_routes import ReviewQueueRouteResponse
from src.vyu.entrypoints.service_routes import ServiceRouteRuntime


class DeploymentHttpAdapterTests(unittest.TestCase):
    def test_authenticator_validates_hs256_token_and_returns_claims(self):
        authenticator = _authenticator(now=1_000)
        token = _jwt(_claims(exp=1_100))

        claims = authenticator.authenticate({"authorization": f"Bearer {token}"})

        self.assertEqual("https://issuer.example", claims["iss"])
        self.assertEqual("vyu-api", claims["aud"])
        self.assertEqual("user-123", claims["sub"])

    def test_authenticator_rejects_missing_bad_or_untrusted_tokens(self):
        authenticator = _authenticator(now=1_000)
        valid = _jwt(_claims(exp=1_100))
        tampered = valid.rsplit(".", 1)[0] + ".invalid-signature"
        bad_algorithm = _jwt(_claims(exp=1_100), header={"alg": "none"})

        cases = [
            ({}, "Missing Authorization"),
            ({"authorization": "Basic abc"}, "Bearer scheme"),
            ({"authorization": f"Bearer {tampered}"}, "signature"),
            ({"authorization": f"Bearer {bad_algorithm}"}, "algorithm"),
            (
                {
                    "authorization": (
                        f"Bearer {_jwt({**_claims(exp=1_100), 'iss': 'https://evil.example'})}"
                    )
                },
                "issuer",
            ),
            (
                {"authorization": f"Bearer {_jwt({**_claims(exp=1_100), 'aud': 'other-api'})}"},
                "audience",
            ),
            ({"authorization": f"Bearer {_jwt(_claims(exp=900))}"}, "expired"),
            (
                {"authorization": f"Bearer {_jwt({**_claims(exp=1_100), 'nbf': 1_200})}"},
                "not valid yet",
            ),
        ]

        for headers, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(AuthenticationError, message):
                    authenticator.authenticate(headers)

    def test_deployment_adapter_allows_health_without_bearer_token(self):
        service = _ServiceStub()
        adapter = ServiceDeploymentHttpAdapter(
            service_runtime=service,
            authenticator=_authenticator(now=1_000),
            request_id_factory=lambda: "request-health",
        )

        response = adapter.handle(DeploymentHttpRequest(method="GET", path="/v1/health"))

        self.assertEqual(200, response.status_code)
        self.assertEqual("request-health", response.body["request_id"])
        self.assertEqual({}, service.requests[0].identity_claims)

    def test_deployment_adapter_authenticates_and_passes_claims_to_service_runtime(self):
        review_runtime = _ReviewQueueStub()
        service = ServiceRouteRuntime(
            review_queue_runtime=review_runtime,
            report_export_runtime=_ReportExportStub(),
            request_id_factory=lambda: "service-request",
            identity_mapper=_identity_mapper(),
        )
        adapter = ServiceDeploymentHttpAdapter(
            service_runtime=service,
            authenticator=_authenticator(now=1_000),
            request_id_factory=lambda: "adapter-request",
        )
        token = _jwt(_claims(exp=1_100))

        response = adapter.handle(
            DeploymentHttpRequest(
                method="GET",
                path="/v1/review-queue",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-vyu-user-id": "spoofed-client-user",
                    "x-vyu-request-id": "request-123",
                },
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )

        self.assertEqual(200, response.status_code)
        delegated_headers = review_runtime.requests[0].headers
        self.assertEqual("user-123", delegated_headers["x-vyu-user-id"])
        self.assertEqual("tenant-a", delegated_headers["x-vyu-tenant-id"])
        self.assertEqual("workspace-a", delegated_headers["x-vyu-workspace-id"])
        self.assertEqual("reviewer", delegated_headers["x-vyu-role"])
        self.assertEqual("request-123", delegated_headers["x-vyu-request-id"])

    def test_deployment_adapter_fails_closed_before_service_runtime_on_bad_token(self):
        service = _ServiceStub()
        adapter = ServiceDeploymentHttpAdapter(
            service_runtime=service,
            authenticator=_authenticator(now=1_000),
            request_id_factory=lambda: "request-auth",
        )

        response = adapter.handle(
            DeploymentHttpRequest(
                method="GET",
                path="/v1/review-queue",
                headers={"authorization": "Bearer bad.token"},
                query={"tenant_id": "tenant-a", "workspace_id": "workspace-a"},
            )
        )

        self.assertEqual(401, response.status_code)
        self.assertEqual("auth_token_invalid", response.body["reason"])
        self.assertEqual([], service.requests)


def _authenticator(now):
    return Hs256BearerTokenAuthenticator(
        BearerTokenConfig(
            issuer="https://issuer.example",
            audience="vyu-api",
            hs256_secret="test-secret",
            leeway_seconds=0,
        ),
        clock=lambda: now,
    )


def _identity_mapper():
    return IdentityMapper(
        IdentityMappingConfig(
            trusted_issuers=frozenset({"https://issuer.example"}),
            accepted_audiences=frozenset({"vyu-api"}),
        )
    )


def _claims(exp):
    return {
        "iss": "https://issuer.example",
        "aud": "vyu-api",
        "sub": "user-123",
        "exp": exp,
        "iat": 900,
        "email": "user@example.com",
        "email_verified": True,
        "vyu": {
            "tenant_id": "tenant-a",
            "workspace_id": "workspace-a",
            "roles": ["vyu:reviewer"],
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


class _ServiceStub:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return ReviewQueueRouteResponse(
            status_code=200,
            body={
                "request_id": request.headers["x-vyu-request-id"],
                "audit_correlation_id": request.headers["x-vyu-audit-correlation-id"],
                "status": "ok",
                "reason": "stub_ok",
                "data": {},
            },
        )


class _ReviewQueueStub:
    def __init__(self):
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        return ReviewQueueRouteResponse(status_code=200, body={"reason": "ok"})


class _ReportExportStub:
    def handle(self, request):
        return ReportExportRouteResponse(status_code=200, body={"reason": "ok"})


if __name__ == "__main__":
    unittest.main()
