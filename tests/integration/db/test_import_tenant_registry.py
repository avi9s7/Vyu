from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "config" / "tenant_governance.local.example.json"


def test_import_is_idempotent(postgres_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VYU_MIGRATION_DATABASE_URL", postgres_urls["migration"])
    monkeypatch.setenv("VYU_DATABASE_URL", postgres_urls["migration"])
    command = [
        "uv",
        "run",
        "python",
        "scripts/import_tenant_registry.py",
        "--registry",
        str(REGISTRY),
        "--apply",
    ]
    first = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    second = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    first_counts = json.loads(first.stdout.strip())
    second_counts = json.loads(second.stdout.strip())
    assert first_counts["tenants"] >= 1
    assert second_counts == {"tenants": 0, "workspaces": 0, "users": 0, "memberships": 0}


def test_dry_run_prints_counts_without_secrets(
    postgres_urls: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VYU_MIGRATION_DATABASE_URL", postgres_urls["migration"])
    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/import_tenant_registry.py",
            "--registry",
            str(REGISTRY),
            "--dry-run",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout.strip())
    assert payload["tenants"] >= 1
    assert "secret" not in completed.stdout.lower()
    assert "sha256" not in completed.stdout.lower()
