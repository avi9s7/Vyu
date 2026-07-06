#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError


class ConfigureSecretsError(Exception):
    """Raised when secret configuration is rejected."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Put a Secrets Manager value for an approved VYU secret container.",
    )
    parser.add_argument("--environment", required=True)
    parser.add_argument("--secret-id", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--value-stdin",
        action="store_true",
        help="Read the secret payload from standard input.",
    )
    source.add_argument(
        "--json-file",
        type=Path,
        help="Read a JSON object from a file.",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region override. Defaults to the session default.",
    )
    return parser.parse_args(argv)


def _load_secret_payload(args: argparse.Namespace) -> str:
    if args.value_stdin:
        payload = sys.stdin.read()
    else:
        assert args.json_file is not None
        payload = args.json_file.read_text(encoding="utf-8")
    json.loads(payload)
    return payload


def _verify_environment_tags(client: Any, *, secret_id: str, environment: str) -> None:
    try:
        response = client.describe_secret(SecretId=secret_id)
    except ClientError as exc:
        raise ConfigureSecretsError(f"Unable to describe secret: {exc}") from exc

    tags = {tag["Key"]: tag["Value"] for tag in response.get("Tags", [])}
    tagged_environment = tags.get("Environment")
    if tagged_environment != environment:
        raise ConfigureSecretsError(
            "Secret Environment tag does not match requested environment."
        )


def configure_secret(
    *,
    environment: str,
    secret_id: str,
    payload: str,
    region: str | None = None,
) -> dict[str, str]:
    client = boto3.client("secretsmanager", region_name=region)
    _verify_environment_tags(client, secret_id=secret_id, environment=environment)
    response = client.put_secret_value(SecretId=secret_id, SecretString=payload)
    return {
        "arn": response["ARN"],
        "version_id": response["VersionId"],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if len(sys.argv) > 1 and any(not arg.startswith("-") for arg in sys.argv[1:]):
        print("Plaintext secret values on the command line are not allowed.", file=sys.stderr)
        return 2

    try:
        payload = _load_secret_payload(args)
        result = configure_secret(
            environment=args.environment,
            secret_id=args.secret_id,
            payload=payload,
            region=args.region,
        )
    except (ConfigureSecretsError, json.JSONDecodeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
