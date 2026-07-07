from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "docs" / "production" / "PLAN4_OPERATOR_HANDOFF.md"


def test_plan4_operator_handoff_documents_blockers_and_resume_steps() -> None:
    content = HANDOFF.read_text(encoding="utf-8")
    for fragment in (
        "## 1. What is already implemented",
        "## 2. Where work stopped",
        "## 4. Inputs required from you",
        "## 5. Step-by-step resume sequence",
        "aws sts get-caller-identity",
        "render_github_ci_vars.py",
        "verify_restore.py",
    ):
        assert fragment in content, f"PLAN4_OPERATOR_HANDOFF.md missing: {fragment}"


def test_plan4_secret_examples_exist() -> None:
    secrets_dir = ROOT / "infra" / "terraform" / "bootstrap" / "secrets"
    assert (secrets_dir / "database-connection.example.txt").is_file()
    assert (secrets_dir / "providers.example.json").is_file()
