import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_review_queue import inspect_review_queue
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.review import ReviewStatus


class InspectReviewQueueScriptTests(unittest.TestCase):
    def test_inspect_review_queue_lists_scoped_pending_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            payload = inspect_review_queue(
                sqlite_db=sqlite_path,
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                status=ReviewStatus.PENDING,
                run_id="local-phase-output-run",
            )

        self.assertEqual(200, payload["status_code"])
        self.assertEqual("review_queue_loaded", payload["reason"])
        self.assertEqual(1, len(payload["review_tasks"]))
        self.assertEqual(
            "review-local-phase-output-run",
            payload["review_tasks"][0]["review_id"],
        )
        self.assertEqual("pending", payload["review_tasks"][0]["status"])

    def test_inspect_review_queue_reports_unauthorized_principal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            payload = inspect_review_queue(
                sqlite_db=sqlite_path,
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="researcher-1",
                role=Role.RESEARCHER,
                status=ReviewStatus.PENDING,
                run_id="local-phase-output-run",
            )

        self.assertEqual(403, payload["status_code"])
        self.assertEqual("review_queue_not_authorized", payload["reason"])
        self.assertEqual([], payload["review_tasks"])

    def test_inspect_review_queue_script_can_be_executed_directly(self):
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
                / "inspect_review_queue.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                    "--user-id",
                    "reviewer-1",
                    "--role",
                    "reviewer",
                    "--status",
                    "pending",
                    "--run-id",
                    "local-phase-output-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(200, payload["status_code"])
        self.assertEqual("review_queue_loaded", payload["reason"])
        self.assertEqual("review-local-phase-output-run", payload["review_tasks"][0]["review_id"])


if __name__ == "__main__":
    unittest.main()
