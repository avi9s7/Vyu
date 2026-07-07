from __future__ import annotations

import json
import unittest

from tests.unit.model_gateway.test_config import FakeSecretsManagerClient
from src.vyu.model_gateway.secrets import (
    AnthropicCredentials,
    AzureOpenAICredentials,
    GoogleCredentials,
    SecretResolutionError,
    SecretResolver,
)


class SecretProviderMappingTests(unittest.TestCase):
    def test_anthropic_credentials(self) -> None:
        resolver = _resolver(
            {"ANTHROPIC_API_KEY": "sk-ant-api03-live-test-key-abcdef"},
        )
        credentials = resolver.credentials_for("anthropic")
        self.assertIsInstance(credentials, AnthropicCredentials)

    def test_azure_openai_credentials(self) -> None:
        resolver = _resolver(
            {
                "AZURE_OPENAI_API_KEY": "azure-live-key-abcdef",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT": "gpt-4.1-mini",
            },
        )
        credentials = resolver.credentials_for("azure_openai")
        self.assertIsInstance(credentials, AzureOpenAICredentials)
        self.assertEqual(credentials.deployment, "gpt-4.1-mini")

    def test_google_credentials(self) -> None:
        resolver = _resolver({"GOOGLE_API_KEY": "google-live-key-abcdef"})
        credentials = resolver.credentials_for("google")
        self.assertIsInstance(credentials, GoogleCredentials)

    def test_unsupported_provider_raises(self) -> None:
        resolver = _resolver({"OPENAI_API_KEY": "sk-live-test-key-abcdef"})
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("unknown")
        self.assertIn("unsupported provider", str(ctx.exception))

    def test_missing_required_key_raises(self) -> None:
        resolver = _resolver({})
        with self.assertRaises(SecretResolutionError) as ctx:
            resolver.credentials_for("openai")
        self.assertIn("missing provider credential", str(ctx.exception))
        self.assertNotIn("sk-", str(ctx.exception))


def _resolver(payload: dict[str, str]) -> SecretResolver:
    secret_arn = "arn:aws:secretsmanager:us-east-1:123:secret:vyu/staging/providers"
    client = FakeSecretsManagerClient(
        secrets={secret_arn: {"SecretString": json.dumps(payload)}}
    )
    return SecretResolver(secret_arn=secret_arn, client=client)


if __name__ == "__main__":
    unittest.main()
