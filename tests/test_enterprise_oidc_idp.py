import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from src.vyu.deployment import (
    AuthenticationError,
    DeploymentCompositionConfig,
    HttpJwksProvider,
    OidcJwksBearerTokenAuthenticator,
    OidcJwksConfig,
    build_deployment_runtime,
)


TEST_PRIVATE_JWK = {
    "kty": "RSA",
    "kid": "test-rs256-key",
    "alg": "RS256",
    "use": "sig",
    "n": "nN6LtXbobafV2A8PlxWszRhEzkwJ1OvP1QAm9ETe5QYywTfqqiOW_RNttQTpIpYzul0Oa8MUHfMHWaWnRhHveFMSJQ47KpQCti8MdGjGv0d35aZ43q7Z1vvp6SmEx2g8SQR5r2CXvnJKR3XZozEkY8l6SULM990i8rTK5LjmQfW4x9t2XSccJRuuP9-LrtqvPV5UglM7qD4mCH5LopKWBLviZ5fMhbBqOKBI1umdKeQXs1vC1aNESOobLRTTXCRsDbcSswxXk4SHQnvfXI9GOAHwQvMuz66GqxCJAhlQwaR7pi0x5GqQIUyn8dRjBlQm5_Lyk9PLUgwA4R29I8lqQw",
    "e": "AQAB",
    "d": "DK_xI72YwdmrsXxSWfleTv4x_m9m8ioaVpNbEzGIx4QvUbJIj_ct7I0IN_ZMNshoKaACHRQbieqQgx8jPscPk69ATe_vOBvddkeq3bVlsa3BlDjZGMWSh9E7E2kQvKIBEjTC9Ly-uR_8QvhUoF7Gny157vfwpPFlNLULneEYemgZXbZoTQElq2ryau6DJ9-0AOoQqeyfOTmxafEdf6hix0YKfN8mdUEJSofjzm7A0iiNpzYpQfrhknMdD4bGtwqnmW_uhWuCrDGE1mnlHZRRjsMj1hzYUv50MSh6YXabfxFZ5nnE43OKnCcjDMpmE7h-MCfhvJEwLJMHDMOe3Yir4Q",
}

PUBLIC_JWK = {
    key: value
    for key, value in TEST_PRIVATE_JWK.items()
    if key in {"kty", "kid", "alg", "use", "n", "e"}
}


class EnterpriseOidcIdpTests(unittest.TestCase):
    def test_oidc_authenticator_validates_external_rs256_jwt_from_jwks_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            jwks_path = _write_jwks(tmp)
            authenticator = _oidc_authenticator(jwks_path=jwks_path, now=1_000)
            token = _rs256_jwt(_claims(exp=1_100))

            claims = authenticator.authenticate({"Authorization": f"Bearer {token}"})

            self.assertEqual("https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example", claims["iss"])
            self.assertEqual("vyu-api-client", claims["aud"])
            self.assertEqual("user-123", claims["sub"])

    def test_oidc_authenticator_rejects_bad_signature_audience_and_token_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            authenticator = _oidc_authenticator(
                jwks_path=_write_jwks(tmp),
                now=1_000,
                required_token_use="id",
            )
            valid = _rs256_jwt(_claims(exp=1_100, token_use="id"))
            tampered = valid.rsplit(".", 1)[0] + ".invalid-signature"
            cases = [
                ({"Authorization": f"Bearer {tampered}"}, "signature"),
                (
                    {"Authorization": f"Bearer {_rs256_jwt({**_claims(exp=1_100), 'aud': 'other-client'})}"},
                    "audience",
                ),
                (
                    {"Authorization": f"Bearer {_rs256_jwt(_claims(exp=1_100, token_use='access'))}"},
                    "token_use",
                ),
                ({"Authorization": f"Bearer {_rs256_jwt(_claims(exp=900, token_use='id'))}"}, "expired"),
            ]

            for headers, message in cases:
                with self.subTest(message=message):
                    with self.assertRaisesRegex(AuthenticationError, message):
                        authenticator.authenticate(headers)

    def test_oidc_authenticator_accepts_cognito_access_token_client_id_when_aud_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            authenticator = _oidc_authenticator(jwks_path=_write_jwks(tmp), now=1_000)
            claims = _claims(exp=1_100)
            claims.pop("aud")
            claims["client_id"] = "vyu-api-client"
            token = _rs256_jwt(claims)

            mapped_claims = authenticator.authenticate({"Authorization": f"Bearer {token}"})

            self.assertEqual("vyu-api-client", mapped_claims["aud"])

    def test_http_jwks_provider_resolves_discovery_and_caches_keys(self):
        calls = []

        def fetch_json(uri, timeout):
            calls.append((uri, timeout))
            if uri.endswith("/.well-known/openid-configuration"):
                return {"jwks_uri": "https://issuer.example/keys"}
            return {"keys": [PUBLIC_JWK]}

        provider = HttpJwksProvider(
            jwks_uri=None,
            discovery_uri="https://issuer.example/.well-known/openid-configuration",
            cache_ttl_seconds=100,
            fetch_timeout_seconds=1.5,
            clock=lambda: 10,
            fetch_json=fetch_json,
        )

        self.assertEqual((PUBLIC_JWK,), provider.keys())
        self.assertEqual((PUBLIC_JWK,), provider.keys())
        self.assertEqual(
            [
                ("https://issuer.example/.well-known/openid-configuration", 1.5),
                ("https://issuer.example/keys", 1.5),
            ],
            calls,
        )

    def test_deployment_runtime_uses_oidc_jwks_authenticator_for_serverless_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            jwks_path = _write_jwks(tmp)
            bundle = build_deployment_runtime(
                DeploymentCompositionConfig(
                    sqlite_db_path=Path(tmp) / "production.sqlite",
                    phase_output_dir=Path(tmp),
                    token_issuer="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
                    token_audience="vyu-api-client",
                    auth_mode="oidc_jwks",
                    oidc_jwks_path=jwks_path,
                    token_leeway_seconds=30,
                )
            )
            now = int(time.time())
            token = _rs256_jwt(_claims(exp=now + 300, iat=now - 30))

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
            self.assertEqual("review_queue_loaded", payload["reason"])

    def test_composition_config_validates_oidc_jwks_settings_without_hs256_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            jwks_path = _write_jwks(tmp)
            config = DeploymentCompositionConfig.from_mapping(
                {
                    "VYU_SQLITE_DB": str(Path(tmp) / "production.sqlite"),
                    "VYU_PHASE_OUTPUT_DIR": tmp,
                    "VYU_AUTH_MODE": "oidc_jwks",
                    "VYU_TOKEN_ISSUER": "https://issuer.example",
                    "VYU_TOKEN_AUDIENCE": "vyu-api-client",
                    "VYU_OIDC_JWKS_FILE": str(jwks_path),
                    "VYU_OIDC_REQUIRED_TOKEN_USE": "id",
                    "VYU_OIDC_JWKS_CACHE_TTL_SECONDS": "60",
                }
            )

            self.assertEqual("oidc_jwks", config.auth_mode)
            self.assertEqual(jwks_path, config.oidc_jwks_path)
            self.assertEqual("id", config.oidc_required_token_use)
            self.assertEqual("", config.hs256_secret)
            config.validate()


def _oidc_authenticator(jwks_path, now, required_token_use=None):
    return OidcJwksBearerTokenAuthenticator(
        OidcJwksConfig(
            issuer="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
            audience="vyu-api-client",
            jwks_path=Path(jwks_path),
            leeway_seconds=0,
            required_token_use=required_token_use,
        ),
        clock=lambda: now,
    )


def _write_jwks(tmp):
    path = Path(tmp) / "jwks.json"
    path.write_text(json.dumps({"keys": [PUBLIC_JWK]}), encoding="utf-8")
    return path


def _claims(exp, iat=900, token_use=None):
    claims = {
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
        "aud": "vyu-api-client",
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
    if token_use is not None:
        claims["token_use"] = token_use
    return claims


def _rs256_jwt(payload, header=None):
    header = header or {"alg": "RS256", "typ": "JWT", "kid": "test-rs256-key"}
    encoded_header = _b64(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = _rs256_sign(signing_input, TEST_PRIVATE_JWK)
    return f"{encoded_header}.{encoded_payload}.{_b64(signature)}"


def _rs256_sign(signing_input, jwk):
    modulus = _jwk_int(jwk["n"])
    private_exponent = _jwk_int(jwk["d"])
    key_size = (modulus.bit_length() + 7) // 8
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
    padding_length = key_size - len(digest_info) - 3
    encoded_message = b"\x00\x01" + (b"\xff" * padding_length) + b"\x00" + digest_info
    signature_int = pow(int.from_bytes(encoded_message, "big"), private_exponent, modulus)
    return signature_int.to_bytes(key_size, "big")


def _jwk_int(value):
    padding = "=" * (-len(value) % 4)
    return int.from_bytes(base64.urlsafe_b64decode((value + padding).encode("ascii")), "big")


def _b64(payload):
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
