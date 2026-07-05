import base64
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DeploymentCompositionConfig,
    DeploymentCompositionError,
    DeploymentRuntimeBundle,
    SequentialRequestIdFactory,
    build_deployment_runtime,
)
from src.vyu.storage import PRODUCTION_SCHEMA_VERSION


class DeploymentCompositionTests(unittest.TestCase):
    def test_config_from_mapping_requires_explicit_values_and_parses_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = DeploymentCompositionConfig.from_mapping(
                {
                    "VYU_SQLITE_DB": str(Path(tmp) / "production.sqlite"),
                    "VYU_PHASE_OUTPUT_DIR": str(Path(tmp) / "outputs"),
                    "VYU_TOKEN_ISSUER": "https://issuer.example",
                    "VYU_TOKEN_AUDIENCE": "vyu-api",
                    "VYU_HS256_SECRET": "test-secret",
                    "VYU_TOKEN_LEEWAY_SECONDS": "5",
                    "VYU_UNAUTHENTICATED_PATHS": "/v1/health,/v1/status",
                    "VYU_INITIALIZE_STORAGE": "false",
                    "VYU_REQUIRE_EMAIL_VERIFIED": "true",
                    "VYU_REQUEST_ID_PREFIX": "local-api",
                    "VYU_SERVERLESS_DEFAULT_REQUEST_ID": "local-serverless",
                    "VYU_SERVERLESS_EXTRA_RESPONSE_HEADERS": "x-env=local,x-app=vyu",
                }
            )

        self.assertEqual(5, config.token_leeway_seconds)
        self.assertEqual(("/v1/health", "/v1/status"), config.unauthenticated_paths)
        self.assertFalse(config.initialize_storage)
        self.assertTrue(config.require_email_verified)
        self.assertEqual("local-api", config.request_id_prefix)
        self.assertEqual("local-serverless", config.serverless_default_request_id)
        self.assertEqual(
            {"x-env": "local", "x-app": "vyu"},
            config.serverless_extra_response_headers,
        )

    def test_config_from_mapping_fails_when_required_values_are_missing(self):
        with self.assertRaisesRegex(DeploymentCompositionError, "VYU_HS256_SECRET"):
            DeploymentCompositionConfig.from_mapping(
                {
                    "VYU_SQLITE_DB": "outputs/production.sqlite",
                    "VYU_PHASE_OUTPUT_DIR": "outputs",
                    "VYU_TOKEN_ISSUER": "https://issuer.example",
                    "VYU_TOKEN_AUDIENCE": "vyu-api",
                }
            )

    def test_sequential_request_id_factory_is_deterministic(self):
        factory = SequentialRequestIdFactory("unit")

        self.assertEqual("unit-000001", factory())
        self.assertEqual("unit-000002", factory())

    def test_build_runtime_initializes_storage_and_wires_health_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _config(tmp)
            bundle = build_deployment_runtime(config)

            response = bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/health",
                    "headers": {},
                }
            )

            self.assertIsInstance(bundle, DeploymentRuntimeBundle)
            self.assertEqual(PRODUCTION_SCHEMA_VERSION, bundle.storage.get_schema_version())
            self.assertEqual(200, response["statusCode"])
            payload = json.loads(response["body"])
            self.assertEqual("service_healthy", payload["reason"])
            self.assertEqual("local-deployment", response["headers"]["x-vyu-deployment-target"])

    def test_composed_runtime_authenticates_and_maps_identity_for_review_queue(self):
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_deployment_runtime(_config(tmp))
            token = _jwt(_claims(exp=now + 300, iat=now - 30))

            response = bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/review-queue",
                    "headers": {"authorization": f"Bearer {token}"},
                    "queryStringParameters": {
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                        "status": "pending",
                    },
                }
            )

            self.assertEqual(200, response["statusCode"])
            payload = json.loads(response["body"])
            self.assertEqual("ok", payload["status"])
            self.assertEqual("review_queue_loaded", payload["reason"])
            self.assertEqual([], payload["data"]["review_tasks"])

    def test_composed_runtime_rejects_untrusted_tokens_before_route_dispatch(self):
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            bundle = build_deployment_runtime(_config(tmp))
            token = _jwt(
                {**_claims(exp=now + 300, iat=now - 30), "iss": "https://evil.example"}
            )

            response = bundle.serverless_handler.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/review-queue",
                    "headers": {"authorization": f"Bearer {token}"},
                    "queryStringParameters": {
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                    },
                }
            )

            self.assertEqual(401, response["statusCode"])
            payload = json.loads(response["body"])
            self.assertEqual("auth_token_invalid", payload["reason"])
            self.assertEqual("error", payload["status"])

    def test_build_runtime_validates_config_before_creating_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = DeploymentCompositionConfig(
                sqlite_db_path=Path(tmp) / "production.sqlite",
                phase_output_dir=Path(tmp),
                token_issuer="https://issuer.example",
                token_audience="vyu-api",
                hs256_secret="",
            )
            with self.assertRaisesRegex(DeploymentCompositionError, "hs256_secret"):
                build_deployment_runtime(config)


def _config(tmp):
    return DeploymentCompositionConfig(
        sqlite_db_path=Path(tmp) / "production.sqlite",
        phase_output_dir=Path(tmp),
        token_issuer="https://issuer.example",
        token_audience="vyu-api",
        hs256_secret="test-secret",
        token_leeway_seconds=30,
        request_id_prefix="unit-request",
        serverless_extra_response_headers={"x-vyu-deployment-target": "local-deployment"},
    )


def _claims(exp, iat):
    return {
        "iss": "https://issuer.example",
        "aud": "vyu-api",
        "sub": "user-123",
        "exp": exp,
        "iat": iat,
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


if __name__ == "__main__":
    unittest.main()
