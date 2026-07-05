from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MUST_BE_IGNORED = (
    ".env",
    ".env.local",
    "config/deployment.local.env",
    "apps/web/node_modules/example.js",
    "apps/web/.next/BUILD_ID",
    ".pytest_cache/example",
    ".mypy_cache/example",
    ".ruff_cache/example",
    "htmlcov/index.html",
    ".coverage",
    "outputs/production.sqlite",
    "logs/application.log",
    "infra/terraform/environments/dev/terraform.tfstate",
    "infra/terraform/environments/dev/.terraform/provider.lock",
    "Additional_scripts_patch_v16/reference.patch",
    "Front End Screenshots/reference.png",
)

MUST_NOT_BE_IGNORED = (
    ".env.example",
    "config/deployment.local.example.env",
    "apps/web/package-lock.json",
    "uv.lock",
)


def check_ignore(path: str) -> int:
    completed = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode


class RepositoryHygieneTests(unittest.TestCase):
    def test_local_generated_and_secret_paths_are_ignored(self) -> None:
        failures = [path for path in MUST_BE_IGNORED if check_ignore(path) != 0]
        self.assertEqual([], failures, f"Paths must be ignored: {failures}")

    def test_examples_and_lock_files_are_not_ignored(self) -> None:
        failures = [path for path in MUST_NOT_BE_IGNORED if check_ignore(path) == 0]
        self.assertEqual([], failures, f"Paths must remain trackable: {failures}")

    def test_repository_metadata_files_exist(self) -> None:
        for relative_path in (
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
            ".python-version",
            ".nvmrc",
        ):
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_runtime_major_versions_are_pinned(self) -> None:
        self.assertEqual("3.13", (ROOT / ".python-version").read_text().strip())
        self.assertEqual("24", (ROOT / ".nvmrc").read_text().strip())

    def test_no_forbidden_path_is_tracked(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        tracked = completed.stdout.decode("utf-8").split("\0")
        forbidden_fragments = (
            "/node_modules/",
            "/.next/",
            "terraform.tfstate",
            ".env.local",
            "deployment.local.env",
        )
        failures = [
            path
            for path in tracked
            if any(fragment in f"/{path}" for fragment in forbidden_fragments)
        ]
        self.assertEqual([], failures, f"Forbidden tracked paths: {failures}")

    def test_ci_workflow_has_read_only_default_permissions_and_two_jobs(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("backend:", workflow)
        self.assertIn("frontend:", workflow)
        self.assertIn("uv sync --all-groups --frozen", workflow)
        self.assertIn("npm ci", workflow)
        mutable = re.findall(r"uses:\s+[^\s]+@v\d", workflow)
        self.assertEqual([], mutable, f"Actions must use immutable SHAs: {mutable}")


if __name__ == "__main__":
    unittest.main()
