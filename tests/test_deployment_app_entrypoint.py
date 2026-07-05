import base64
import hashlib
import hmac
import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.vyu.deployment import (
    DEPLOYMENT_ENV_FILE_ENV_VAR,
    DeploymentAppEntrypointError,
    DeploymentAppEntrypointConfig,
    DeploymentServerlessAppEntrypoint,
    create_serverless_app_from_env_file,
    operator_env_file_from_environ,
)


class DeploymentAppEntrypointTests(unittest.TestCase):
    def test_app_entrypoint_loads_operator_config_and_delegates_authenticated_event(self):
        now = int(time.time())
        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(tmp, secret="entrypoint-secret")
            app = create_serverless_app_from_env_file(env_file)
            token = _jwt(_claims(exp=now + 300, iat=now - 30), secret="entrypoint-secret")

            response = app.handle(
                {
                    "httpMethod": "GET",
                    "path": "/v1/review-queue",
                    "headers": {
                        "authorization": f"Bearer {token}",
                        "x-vyu-request-id": "entrypoint-request-1",
                    },
                    "queryStringParameters": {
                        "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a",
                        "status": "pending",
                    },
                }
            )

        self.assertIsInstance(app, DeploymentServerlessAppEntrypoint)
        self.assertEqual(200, response["statusCode"])
        self.assertEqual("entrypoint-request-1", response["headers"]["x-vyu-request-id"])
        payload = json.loads(response["body"])
        self.assertEqual("review_queue_loaded", payload["reason"])
        self.assertEqual([], payload["data"]["review_tasks"])

    def test_app_entrypoint_caches_runtime_between_requests_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(tmp, secret="entrypoint-secret")
            app = create_serverless_app_from_env_file(env_file)

            first = app.handle({"httpMethod": "GET", "path": "/v1/health", "headers": {}})
            env_file.write_text(
                env_file.read_text(encoding="utf-8").replace(
                    "entrypoint-secret",
                    "__REPLACE_WITH_LOCAL_SECRET__",
                ),
                encoding="utf-8",
            )
            second = app.handle({"httpMethod": "GET", "path": "/v1/health", "headers": {}})
            app.clear_cached_runtime()
            third = app.handle({"httpMethod": "GET", "path": "/v1/health", "headers": {}})

        self.assertEqual(200, first["statusCode"])
        self.assertEqual(200, second["statusCode"])
        self.assertEqual(500, third["statusCode"])
        self.assertEqual("deployment_entrypoint_config_error", json.loads(third["body"])["reason"])
        self.assertNotIn("__REPLACE_WITH_LOCAL_SECRET__", third["body"])

    def test_app_entrypoint_can_disable_runtime_cache_for_local_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(tmp, secret="entrypoint-secret")
            app = create_serverless_app_from_env_file(env_file, cache_runtime=False)

            first = app.handle({"httpMethod": "GET", "path": "/v1/health", "headers": {}})
            env_file.write_text(
                env_file.read_text(encoding="utf-8").replace(
                    "entrypoint-secret",
                    "__REPLACE_WITH_LOCAL_SECRET__",
                ),
                encoding="utf-8",
            )
            second = app.handle({"httpMethod": "GET", "path": "/v1/health", "headers": {}})

        self.assertEqual(200, first["statusCode"])
        self.assertEqual(500, second["statusCode"])
        self.assertEqual("deployment_entrypoint_config_error", json.loads(second["body"])["reason"])

    def test_operator_env_file_from_environ_requires_explicit_path(self):
        with self.assertRaisesRegex(DeploymentAppEntrypointError, DEPLOYMENT_ENV_FILE_ENV_VAR):
            operator_env_file_from_environ({})

        self.assertEqual(
            Path("config/deployment.local.env"),
            operator_env_file_from_environ(
                {DEPLOYMENT_ENV_FILE_ENV_VAR: "config/deployment.local.env"}
            ),
        )

    def test_config_rejects_blank_default_request_id(self):
        with self.assertRaisesRegex(DeploymentAppEntrypointError, "default_request_id"):
            DeploymentAppEntrypointConfig(
                operator_env_file=Path("config/deployment.local.env"),
                default_request_id=" ",
            ).validate()

    def test_packaged_serverless_handler_uses_env_file_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = _write_env_file(tmp, secret="entrypoint-secret")
            module = importlib.import_module("apps.serverless.handler")
            module.reset_cached_app_for_tests()
            with patch.dict(os.environ, {DEPLOYMENT_ENV_FILE_ENV_VAR: str(env_file)}, clear=True):
                response = module.handler(
                    {
                        "httpMethod": "GET",
                        "path": "/v1/health",
                        "headers": {"x-vyu-request-id": "packaged-request-1"},
                    },
                    context=object(),
                )
            module.reset_cached_app_for_tests()

        self.assertEqual(200, response["statusCode"])
        payload = json.loads(response["body"])
        self.assertEqual("service_healthy", payload["reason"])
        self.assertEqual("packaged-request-1", response["headers"]["x-vyu-request-id"])

    def test_packaged_serverless_handler_fails_closed_when_env_var_missing(self):
        module = importlib.import_module("apps.serverless.handler")
        module.reset_cached_app_for_tests()
        with patch.dict(os.environ, {}, clear=True):
            response = module.handler(
                {
                    "httpMethod": "GET",
                    "path": "/v1/health",
                    "headers": {"x-vyu-request-id": "missing-config-request"},
                }
            )
        module.reset_cached_app_for_tests()

        self.assertEqual(500, response["statusCode"])
        self.assertEqual("missing-config-request", response["headers"]["x-vyu-request-id"])
        payload = json.loads(response["body"])
        self.assertEqual("deployment_entrypoint_config_error", payload["reason"])
        self.assertNotIn("VYU_HS256_SECRET", response["body"])


def _write_env_file(tmp, secret="entrypoint-secret"):
    root = Path(tmp)
    env_file = root / "deployment.env"
    env_file.write_text(
        "\n".join(
            [
                f"VYU_SQLITE_DB={root / 'production.sqlite'}",
                f"VYU_PHASE_OUTPUT_DIR={root / 'outputs'}",
                "VYU_TOKEN_ISSUER=https://issuer.example",
                "VYU_TOKEN_AUDIENCE=vyu-api",
                f"VYU_HS256_SECRET={secret}",
                "VYU_TENANT_ID=tenant-a",
                "VYU_WORKSPACE_ID=workspace-a",
                "VYU_USER_ID=reviewer-1",
                "VYU_ROLE=vyu:reviewer",
                "VYU_REQUEST_ID_PREFIX=entrypoint-test",
                "VYU_SERVERLESS_DEFAULT_REQUEST_ID=entrypoint-default",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


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


def _jwt(payload, secret="entrypoint-secret", header=None):
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
