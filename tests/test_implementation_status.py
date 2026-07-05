from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "production" / "IMPLEMENTATION_STATUS.md"


class ImplementationStatusTests(unittest.TestCase):
    def test_status_document_contains_all_plans_and_truthful_states(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        for plan_number in range(1, 11):
            self.assertIn(f"| {plan_number} |", text)
        self.assertIn("not_started", text)
        self.assertIn("in_progress", text)
        self.assertIn("staging_verified", text)
        self.assertIn("complete", text)

    def test_status_document_rejects_local_artifacts_as_production_evidence(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        self.assertIn("Local JSON and SQLite artifacts are not production evidence", text)


if __name__ == "__main__":
    unittest.main()
