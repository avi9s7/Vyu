from __future__ import annotations

import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_MODULE = ROOT / "infra" / "terraform" / "modules" / "data"
VERIFY_RESTORE = ROOT / "scripts" / "verify_restore.py"
DATABASE_RESTORE_RUNBOOK = ROOT / "docs" / "production" / "runbooks" / "database-restore.md"


def _read_module_tf(module_dir: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(module_dir.glob("*.tf")))


def test_rds_automated_backups_and_pitr_retention_enabled() -> None:
    content = (DATA_MODULE / "rds.tf").read_text(encoding="utf-8")
    assert "backup_retention_period" in content
    assert "copy_tags_to_snapshot" in content


def test_pilot_recovery_targets_are_declared() -> None:
    locals_tf = (DATA_MODULE / "locals.tf").read_text(encoding="utf-8")
    outputs_tf = (DATA_MODULE / "outputs.tf").read_text(encoding="utf-8")
    assert "pilot_recovery_targets" in locals_tf
    assert "rpo_minutes = 15" in locals_tf
    assert "rto_hours   = 4" in locals_tf
    assert 'output "pilot_recovery_targets"' in outputs_tf


def test_s3_versioning_and_lifecycle_recovery_are_enabled() -> None:
    content = _read_module_tf(DATA_MODULE)
    assert 'resource "aws_s3_bucket_versioning" "application"' in content
    assert 'status = "Enabled"' in content
    assert 'resource "aws_s3_bucket_lifecycle_configuration" "application"' in content
    assert "noncurrent_version_expiration" in content


def test_verify_restore_script_contract() -> None:
    content = VERIFY_RESTORE.read_text(encoding="utf-8")
    for marker in (
        "verify_migration_revision",
        "verify_fixture_hashes",
        "verify_tenant_isolation",
        "verify_audit_presence",
        "verify_absent_after_restore",
        "verify_s3_object_versions",
        "VYU_VERIFY_RESTORE_DATABASE_URL",
    ):
        assert marker in content


def test_restore_fingerprints_are_deterministic() -> None:
    from scripts.verify_restore import load_restore_manifest, research_fingerprint, tenant_fingerprint

    assert tenant_fingerprint(slug="restore-fixture", name="Restore Fixture Tenant") == tenant_fingerprint(
        slug="restore-fixture",
        name="Restore Fixture Tenant",
    )
    assert research_fingerprint(question="fixture question") == research_fingerprint(
        question="fixture question"
    )
    with pytest.raises(Exception):
        load_restore_manifest('{"expected_migration_revision":"0003"}')


def test_database_restore_runbook_documents_rpo_rto_and_real_restore() -> None:
    content = DATABASE_RESTORE_RUNBOOK.read_text(encoding="utf-8")
    assert "RPO" in content
    assert "RTO" in content
    assert "restore-db-instance-to-point-in-time" in content
    assert "verify_restore.py" in content
    assert "not** a restore test" in content


def test_terraform_validate_dev_environment() -> None:
    init = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "init", "-backend=false"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert init.returncode == 0, init.stderr

    validate = subprocess.run(
        ["terraform", "-chdir=infra/terraform/environments/dev", "validate"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validate.returncode == 0, validate.stderr
