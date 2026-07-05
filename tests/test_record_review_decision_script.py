import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.record_review_decision import record_review_decision
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.review import ReviewDecision
from src.vyu.storage import ProductionStorage


class RecordReviewDecisionScriptTests(unittest.TestCase):
    def test_record_review_decision_approves_task_and_audits_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            payload = record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for export.",
                decided_at="2026-06-15T00:05:00Z",
            )
            storage = ProductionStorage(sqlite_path)
            task = storage.get_review_task("review-local-phase-output-run")
            events = storage.list_audit_events(
                run_id="local-phase-output-run",
                event_type="review_decision_recorded",
            )

        self.assertEqual(200, payload["status_code"])
        self.assertEqual("review_decision_recorded", payload["reason"])
        self.assertEqual("approved", payload["review_task"]["status"])
        self.assertEqual("approved", task.status.value)
        self.assertEqual("reviewer-1", task.decision.reviewer_id)
        self.assertEqual(1, len(events))
        self.assertEqual("approve", events[0].payload["decision"])

    def test_record_review_decision_rejects_unauthorized_researcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            payload = record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="researcher-1",
                role=Role.RESEARCHER,
                decision=ReviewDecision.APPROVE,
                comment="Trying to approve.",
                decided_at="2026-06-15T00:05:00Z",
            )
            storage = ProductionStorage(sqlite_path)
            task = storage.get_review_task("review-local-phase-output-run")
            events = storage.list_audit_events(
                run_id="local-phase-output-run",
                event_type="review_decision_recorded",
            )

        self.assertEqual(403, payload["status_code"])
        self.assertEqual("review_decision_not_authorized", payload["reason"])
        self.assertIsNone(payload["review_task"])
        self.assertEqual("pending", task.status.value)
        self.assertEqual([], events)

    def test_record_review_decision_script_can_be_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "record_review_decision.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--review-id",
                    "review-local-phase-output-run",
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                    "--user-id",
                    "reviewer-1",
                    "--role",
                    "reviewer",
                    "--decision",
                    "reject",
                    "--comment",
                    "Evidence not sufficient for export.",
                    "--decided-at",
                    "2026-06-15T00:06:00Z",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            storage = ProductionStorage(sqlite_path)
            task = storage.get_review_task("review-local-phase-output-run")

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(200, payload["status_code"])
        self.assertEqual("rejected", payload["review_task"]["status"])
        self.assertEqual("rejected", task.status.value)


if __name__ == "__main__":
    unittest.main()
