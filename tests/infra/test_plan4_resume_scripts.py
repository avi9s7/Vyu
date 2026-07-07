from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_render_github_ci_vars_placeholder_mode() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_github_ci_vars.py"),
            "dev",
            "--placeholder",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "AWS_PLAN_ROLE_ARN" in result.stdout
    assert "123456789012" in result.stdout
    assert "vyu-dev-github-apply" in result.stdout


def test_infra_plan_skips_pilot_plan_role() -> None:
    workflow = (ROOT / ".github" / "workflows" / "infra-plan.yml").read_text(encoding="utf-8")
    assert "123456789012" in workflow
    assert "startsWith(vars.AWS_PLAN_ROLE_ARN" in workflow
