from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PythonProjectConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_project_targets_python_313(self) -> None:
        self.assertEqual(">=3.13,<3.14", self.config["project"]["requires-python"])

    def test_build_backend_is_declared(self) -> None:
        self.assertEqual(
            "setuptools.build_meta",
            self.config["build-system"]["build-backend"],
        )

    def test_development_tools_are_declared(self) -> None:
        dependencies = "\n".join(self.config["dependency-groups"]["dev"])
        for required in ("pytest", "pytest-cov", "ruff", "mypy"):
            self.assertIn(required, dependencies)

    def test_static_analysis_targets_python_313(self) -> None:
        self.assertEqual("py313", self.config["tool"]["ruff"]["target-version"])
        self.assertEqual("3.13", self.config["tool"]["mypy"]["python_version"])

    def test_lock_file_exists(self) -> None:
        self.assertTrue((ROOT / "uv.lock").is_file())

    def test_api_and_queue_dependencies_are_declared(self) -> None:
        dependencies = "\n".join(self.config["project"]["dependencies"])
        for required in (
            "boto3",
            "cryptography",
            "fastapi",
            "httpx",
            "pyjwt",
            "uvicorn",
        ):
            self.assertIn(required, dependencies)


if __name__ == "__main__":
    unittest.main()
