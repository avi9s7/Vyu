from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

from src.vyu.model_gateway.config import (
    ModelGatewayConfigError,
    ModelGatewaySettings,
    validate_model_gateway_startup,
)
from src.vyu.model_gateway.secrets import (
    OpenAICredentials,
    SecretResolutionError,
    SecretResolver,
    SecretRotationRunbook,
)


class FakeSecretsManagerClient:
    def __init__(
        self,
        *,
        secrets: dict[str, dict[str, object]] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.secrets = secrets or {}
        self.errors = errors or {}
        self.calls: list[dict[str, object]] = []

    def get_secret_value(self, *, SecretId: str, VersionId: str | None = None) -> dict[str, object]:
        self.calls.append({"SecretId": SecretId, "VersionId": VersionId})
        if SecretId in self.errors:
            raise self.errors[SecretId]
        if SecretId not in self.secrets:
            raise RuntimeError("ResourceNotFoundException")
        payload = self.secrets[SecretId]
        if VersionId is not None and payload.get("VersionId") != VersionId:
            raise RuntimeError("ResourceNotFoundException")
        return payload


class ModelGatewayConfigTests(unittest.TestCase):
    def test_local_environment_allows_deterministic_defaults(self) -> None:
        settings = ModelGatewaySettings(env="local")
        validate_model_gateway_startup(settings)

    def test_staging_requires_provider_policy_and_prompt(self) -> None:
        settings = ModelGatewaySettings(
            env="staging",
            generation_provider="openai",
            generation_model="gpt-4.1-mini",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            model_policy_version="model_policy_v1",
            prompt_template_id="grounded_answer_v1",
            prompt_version="grounded_answer_v1.0",
            providers_config_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
        )
        with self.assertRaises(ModelGatewayConfigError) as ctx:
            validate_model_gateway_startup(settings)
        self.assertIn("SecretResolver is required", str(ctx.exception))

    def test_staging_rejects_fixture_adapter(self) -> None:
        settings = ModelGatewaySettings(
            env="staging",
            generation_provider="openai",
            generation_model="gpt-4.1-mini",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            model_policy_version="model_policy_v1",
            prompt_template_id="grounded_answer_v1",
            prompt_version="grounded_answer_v1.0",
            providers_config_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            enable_fixture_adapter=True,
        )
        with self.assertRaises(ModelGatewayConfigError) as ctx:
            validate_model_gateway_startup(settings)
        self.assertIn("Fixture adapters", str(ctx.exception))

    def test_staging_rejects_dimension_conflict(self) -> None:
        settings = ModelGatewaySettings(
            env="staging",
            generation_provider="openai",
            generation_model="gpt-4.1-mini",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            model_policy_version="model_policy_v1",
            prompt_template_id="grounded_answer_v1",
            prompt_version="grounded_answer_v1.0",
            providers_config_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
        )
        with self.assertRaises(ModelGatewayConfigError) as ctx:
            validate_model_gateway_startup(
                settings,
                resolver=_resolver_with_openai(),
                active_index_dimensions=[768],
            )
        self.assertIn("Embedding dimensions conflict", str(ctx.exception))

    def test_staging_validates_provider_credentials(self) -> None:
        settings = ModelGatewaySettings(
            env="staging",
            generation_provider="openai",
            generation_model="gpt-4.1-mini",
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            model_policy_version="model_policy_v1",
            prompt_template_id="grounded_answer_v1",
            prompt_version="grounded_answer_v1.0",
            providers_config_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
        )
        validate_model_gateway_startup(
            settings,
            resolver=_resolver_with_openai(),
            active_index_dimensions=[1536],
        )

    def test_safe_summary_never_includes_secret_arn_value(self) -> None:
        settings = ModelGatewaySettings(
            providers_config_secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
        )
        summary = settings.safe_summary()
        self.assertTrue(summary["providers_config_secret_arn_configured"])
        self.assertNotIn("arn:aws", json.dumps(summary))


class SecretResolverTests(unittest.TestCase):
    def test_resolves_openai_credentials_from_fake_client(self) -> None:
        secret_value = json.dumps({"OPENAI_API_KEY": "sk-live-test-key-abcdef"})
        client = FakeSecretsManagerClient(
            secrets={
                "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers": {
                    "SecretString": secret_value,
                    "VersionId": "version-1",
                }
            }
        )
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        credentials = resolver.credentials_for("openai")
        self.assertIsInstance(credentials, OpenAICredentials)
        self.assertEqual(credentials.api_key, "sk-live-test-key-abcdef")
        self.assertEqual(repr(credentials), "OpenAICredentials(api_key=<redacted>)")

    def test_missing_secret_raises_without_leaking_value(self) -> None:
        client = FakeSecretsManagerClient()
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("openai")
        message = str(ctx.exception)
        self.assertIn("unable to load provider secret", message)
        self.assertNotIn("sk-", message)

    def test_denied_secret_raises_without_leaking_value(self) -> None:
        client = FakeSecretsManagerClient(
            errors={
                "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers": RuntimeError(
                    "AccessDeniedException for sk-denied-secret-value"
                )
            }
        )
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("openai")
        message = str(ctx.exception)
        self.assertIn("unable to load provider secret", message)
        self.assertNotIn("sk-denied-secret-value", message)

    def test_malformed_secret_payload_raises(self) -> None:
        client = FakeSecretsManagerClient(
            secrets={
                "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers": {
                    "SecretString": "not-json",
                }
            }
        )
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("openai")
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_placeholder_secret_is_rejected(self) -> None:
        secret_value = json.dumps({"OPENAI_API_KEY": "sk-placeholder-replace-before-deploy"})
        client = FakeSecretsManagerClient(
            secrets={
                "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers": {
                    "SecretString": secret_value,
                }
            }
        )
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("openai")
        self.assertIn("placeholder", str(ctx.exception).lower())
        self.assertNotIn("sk-placeholder", str(ctx.exception))

    def test_rotated_secret_version_is_loaded_after_cache_invalidation(self) -> None:
        secret_arn = "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers"
        client = FakeSecretsManagerClient(
            secrets={
                secret_arn: {
                    "SecretString": json.dumps({"OPENAI_API_KEY": "sk-rotated-key-000000000000"}),
                    "VersionId": "version-2",
                }
            }
        )
        clock = _FakeClock()
        resolver = SecretResolver(
            secret_arn=secret_arn,
            client=client,
            cache_ttl_seconds=300,
            now=clock,
        )
        first = resolver.credentials_for("openai")
        client.secrets[secret_arn] = {
            "SecretString": json.dumps({"OPENAI_API_KEY": "sk-rotated-key-111111111111"}),
            "VersionId": "version-3",
        }
        second_before_refresh = resolver.credentials_for("openai")
        resolver.invalidate_cache()
        third = resolver.credentials_for("openai")

        self.assertEqual(first.api_key, "sk-rotated-key-000000000000")
        self.assertEqual(second_before_refresh.api_key, "sk-rotated-key-000000000000")
        self.assertEqual(third.api_key, "sk-rotated-key-111111111111")
        self.assertEqual(resolver.current_secret_version_id(), "version-3")

    def test_local_secret_file_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "providers.json"
            secret_path.write_text(
                json.dumps({"OPENAI_API_KEY": "sk-local-file-key-abcdef"}),
                encoding="utf-8",
            )
            resolver = SecretResolver(
                secret_arn="",
                local_secret_file=secret_path,
            )
            credentials = resolver.credentials_for("openai")
            self.assertEqual(credentials.api_key, "sk-local-file-key-abcdef")

    def test_secret_values_are_not_logged(self) -> None:
        secret_value = json.dumps({"OPENAI_API_KEY": "sk-log-leak-test-abcdef"})
        client = FakeSecretsManagerClient(
            secrets={
                "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers": {
                    "SecretString": secret_value,
                }
            }
        )
        resolver = SecretResolver(
            secret_arn="arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers",
            client=client,
        )
        with self.assertLogs("src.vyu.model_gateway.secrets", level="DEBUG") as captured:
            logging.getLogger("src.vyu.model_gateway.secrets").debug(
                "resolved credentials %s",
                resolver.credentials_for("openai"),
            )
        output = "\n".join(captured.output)
        self.assertIn("<redacted>", output)
        self.assertNotIn("sk-log-leak-test-abcdef", output)

    def test_rotation_runbook_steps_are_documented(self) -> None:
        runbook = SecretRotationRunbook(
            environment="staging",
            secret_id="vyu/staging/providers",
        )
        steps = runbook.steps()
        self.assertIn("ECS deployment", steps[2])
        self.assertIn("smoke", steps[3].lower())


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _resolver_with_openai() -> SecretResolver:
    secret_arn = "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers"
    client = FakeSecretsManagerClient(
        secrets={
            secret_arn: {
                "SecretString": json.dumps({"OPENAI_API_KEY": "sk-live-test-key-abcdef"}),
                "VersionId": "version-1",
            }
        }
    )
    return SecretResolver(secret_arn=secret_arn, client=client)


if __name__ == "__main__":
    unittest.main()
