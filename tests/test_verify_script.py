from __future__ import annotations

import unittest

from scripts.verify import Command, commands_for_scope


class VerifyScriptTests(unittest.TestCase):
    def test_backend_scope_contains_quality_and_test_commands(self) -> None:
        commands = commands_for_scope("backend", npm="npm")
        self.assertEqual(
            [
                Command("ruff", ("uv", "run", "ruff", "check", "src", "apps/serverless", "scripts", "tests")),
                Command("mypy", ("uv", "run", "mypy", "--follow-imports=skip")),
                Command("python-tests", ("uv", "run", "python", "-m", "unittest", "discover")),
            ],
            commands,
        )

    def test_frontend_scope_uses_clean_install_and_real_tests(self) -> None:
        commands = commands_for_scope("frontend", npm="npm.cmd")
        self.assertEqual(
            [
                Command("npm-ci", ("npm.cmd", "ci", "--prefix", "apps/web")),
                Command("frontend-typecheck", ("npm.cmd", "run", "typecheck", "--prefix", "apps/web")),
                Command("frontend-lint", ("npm.cmd", "run", "lint", "--prefix", "apps/web")),
                Command("frontend-tests", ("npm.cmd", "test", "--prefix", "apps/web")),
                Command("frontend-build", ("npm.cmd", "run", "build", "--prefix", "apps/web")),
            ],
            commands,
        )

    def test_integration_scope_runs_database_tests(self) -> None:
        commands = commands_for_scope("integration", npm="npm")
        self.assertEqual(
            [
                Command(
                    "postgres-integration",
                    (
                        "uv",
                        "run",
                        "pytest",
                        "tests/integration/db",
                        "tests/integration/ingestion",
                        "tests/integration/policy",
                        "tests/integration/connectors",
                        "-q",
                    ),
                ),
            ],
            commands,
        )

    def test_all_scope_orders_backend_before_frontend(self) -> None:
        names = [command.name for command in commands_for_scope("all", npm="npm")]
        self.assertEqual("ruff", names[0])
        self.assertEqual("postgres-integration", names[3])
        self.assertEqual("frontend-build", names[-1])


if __name__ == "__main__":
    unittest.main()
