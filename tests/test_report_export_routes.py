import tempfile
import unittest
from pathlib import Path

from scripts.record_review_decision import record_review_decision
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Role
from src.vyu.entrypoints import (
    PhaseOutputReportArtifactStore,
    ReportExportRouteRequest,
    ReportExportRouteRuntime,
)
from src.vyu.review import ReviewDecision
from src.vyu.storage import ProductionStorage


class ReportExportRouteTests(unittest.TestCase):
    def test_post_report_export_route_exports_approved_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for route export.",
                decided_at="2026-06-15T00:05:00Z",
            )
            storage = ProductionStorage(sqlite_path)
            runtime = ReportExportRouteRuntime(
                storage=storage,
                artifact_store=PhaseOutputReportArtifactStore(output_dir),
                audit_event_id_factory=lambda _run_id, event_type: f"route-{event_type}",
                audit_created_at="2026-06-15T00:06:00Z",
            )

            response = runtime.handle(
                ReportExportRouteRequest(
                    method="POST",
                    path="/v1/report-exports",
                    headers=_headers(Role.REVIEWER),
                    json_body={
                        "review_id": "review-local-phase-output-run",
                        "report_type": "research_report",
                    },
                )
            )
            events = storage.list_audit_events(
                run_id="local-phase-output-run",
                event_type="report_export_decision_recorded",
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("report-export-route", response.body["request_id"])
        self.assertEqual("local-phase-output-run", response.body["run_id"])
        self.assertTrue(response.body["export"]["allowed"])
        self.assertEqual("export_allowed", response.body["export"]["reason"])
        self.assertIn("Research Report", response.body["export"]["content"])
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual("route-report_export_decision_recorded", events[-1].event_id)
        self.assertTrue(events[-1].payload["allowed"])

    def test_post_report_export_route_returns_forbidden_for_unauthorized_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            record_review_decision(
                sqlite_db=sqlite_path,
                review_id="review-local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                user_id="reviewer-1",
                role=Role.REVIEWER,
                decision=ReviewDecision.APPROVE,
                comment="Evidence reviewed for route export.",
                decided_at="2026-06-15T00:05:00Z",
            )
            runtime = ReportExportRouteRuntime(
                storage=ProductionStorage(sqlite_path),
                artifact_store=PhaseOutputReportArtifactStore(output_dir),
            )

            response = runtime.handle(
                ReportExportRouteRequest(
                    method="POST",
                    path="/v1/report-exports",
                    headers=_headers(Role.RESEARCHER),
                    json_body={
                        "review_id": "review-local-phase-output-run",
                        "report_type": "research_report",
                    },
                )
            )

        self.assertEqual(403, response.status_code)
        self.assertFalse(response.body["export"]["allowed"])
        self.assertEqual("export_not_authorized", response.body["export"]["reason"])

    def test_route_runtime_reports_bad_request_for_missing_body_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            runtime = ReportExportRouteRuntime(
                storage=ProductionStorage(sqlite_path),
                artifact_store=PhaseOutputReportArtifactStore(output_dir),
            )

            response = runtime.handle(
                ReportExportRouteRequest(
                    method="POST",
                    path="/v1/report-exports",
                    headers=_headers(Role.REVIEWER),
                    json_body={"report_type": "research_report"},
                )
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("route_bad_request", response.body["reason"])
        self.assertIn("review_id", response.body["detail"])

    def test_route_runtime_reports_unknown_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(root=root, output_dir=output_dir, sqlite_path=sqlite_path)
            runtime = ReportExportRouteRuntime(
                storage=ProductionStorage(sqlite_path),
                artifact_store=PhaseOutputReportArtifactStore(output_dir),
            )

            response = runtime.handle(
                ReportExportRouteRequest(
                    method="POST",
                    path="/v1/unknown",
                    headers=_headers(Role.REVIEWER),
                    json_body={
                        "review_id": "review-local-phase-output-run",
                        "report_type": "research_report",
                    },
                )
            )

        self.assertEqual(404, response.status_code)
        self.assertEqual("route_not_found", response.body["reason"])


def _headers(role: Role) -> dict[str, str]:
    return {
        "x-vyu-user-id": f"{role.value}-user",
        "x-vyu-role": role.value,
        "x-vyu-tenant-id": "local_tenant",
        "x-vyu-workspace-id": "local_workspace",
    }


if __name__ == "__main__":
    unittest.main()
