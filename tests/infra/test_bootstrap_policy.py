from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "infra" / "terraform" / "bootstrap"


def test_bootstrap_stack_declares_remote_state_primitives() -> None:
    main_tf = (BOOTSTRAP / "main.tf").read_text(encoding="utf-8")
    for fragment in (
        'resource "aws_s3_bucket" "terraform_state"',
        'resource "aws_s3_bucket_versioning" "terraform_state"',
        'resource "aws_s3_bucket_public_access_block" "terraform_state"',
        'resource "aws_dynamodb_table" "terraform_lock"',
        'resource "aws_kms_key" "terraform_state"',
    ):
        assert fragment in main_tf, f"bootstrap main.tf missing {fragment}"


def test_bootstrap_outputs_expose_backend_settings() -> None:
    outputs_tf = (BOOTSTRAP / "outputs.tf").read_text(encoding="utf-8")
    for name in (
        "state_bucket_name",
        "lock_table_name",
        "state_kms_key_arn",
        "backend_hcl_snippet",
    ):
        assert f'output "{name}"' in outputs_tf, f"bootstrap outputs.tf missing {name}"


def test_bootstrap_readme_documents_operator_flow() -> None:
    readme = (BOOTSTRAP / "README.md").read_text(encoding="utf-8")
    assert "terraform apply" in readme
    assert "sync_backend_hcl_from_bootstrap.ps1" in readme
