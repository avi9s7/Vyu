import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_production_store import inspect_production_store
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.connectors.health import (
    ConnectorHealthRecord,
    ConnectorHealthStatus,
    StagedConnectorValidationRecord,
    ValidationStage,
)
from src.vyu.evaluation import EvaluationRun
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import ReviewDecision, create_review_task, decide_review
from src.vyu.storage import (
    PrivacyApprovalRecord,
    ProductionScope,
    ProductionStorage,
    ReadinessCheckResultRecord,
)


class InspectProductionStoreTests(unittest.TestCase):
    def test_inspect_command_exports_manifest_evaluations_and_audit_events(self):
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
                / "inspect_production_store.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("local-phase-output-run", payload["artifact_manifest"]["run_id"])
        self.assertEqual("retrieval_baseline", payload["evaluation_runs"][0]["suite"])
        self.assertEqual(1, len(payload["review_tasks"]))
        self.assertEqual("review-local-phase-output-run", payload["review_tasks"][0]["review_id"])
        self.assertEqual("pending", payload["review_tasks"][0]["status"])
        self.assertEqual([], payload["privacy_approval_records"])
        self.assertEqual([], payload["readiness_check_results"])
        self.assertEqual("dummy_corpus", payload["connector_health_records"][0]["source_id"])
        self.assertEqual("ok", payload["connector_health_records"][0]["status"])
        self.assertEqual("pubmed", payload["connector_validation_records"][0]["source_id"])
        self.assertEqual("replay", payload["connector_validation_records"][0]["stage"])
        self.assertEqual(1, len(payload["evidence_methodology_run_records"]))
        self.assertEqual(5, len(payload["evidence_methodology_assessment_records"]))
        self.assertEqual([], payload["reviewer_evidence_rating_records"])
        self.assertEqual(1, len(payload["external_evidence_grading_request_records"]))
        self.assertEqual(1, len(payload["external_evidence_grading_response_records"]))
        self.assertEqual(1, len(payload["production_trust_score_records"]))
        self.assertEqual(1, len(payload["production_governance_box_records"]))
        self.assertEqual([], payload["reviewer_trust_score_override_records"])
        self.assertEqual(1, len(payload["external_governance_request_records"]))
        self.assertEqual(1, len(payload["external_governance_response_records"]))
        self.assertEqual(
            [
                "artifact_manifest_saved",
                "evaluation_run_saved",
                "phase_outputs_completed",
                "evidence_object_recorded",
                "retrieval_index_recorded",
                "retrieval_run_recorded",
                "production_research_memory_saved",
                "evidence_methodology_assessment_recorded",
                "evidence_methodology_assessment_recorded",
                "evidence_methodology_assessment_recorded",
                "evidence_methodology_assessment_recorded",
                "evidence_methodology_assessment_recorded",
                "evidence_methodology_run_recorded",
                "external_evidence_grading_request_recorded",
                "external_evidence_grading_response_recorded",
                "production_trust_score_recorded",
                "production_governance_box_recorded",
                "external_governance_request_recorded",
                "external_governance_response_recorded",
                "review_task_created",
                "connector_health_recorded",
                "connector_validation_recorded",
            ],
            [event["event_type"] for event in payload["audit_events"]],
        )

    def test_inspect_command_rejects_wrong_scope(self):
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
                / "inspect_production_store.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--sqlite-db",
                    str(sqlite_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "other_tenant",
                    "--workspace-id",
                    "local_workspace",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside the requested tenant/workspace scope", result.stderr)

    def test_inspect_function_filters_evaluation_runs_to_artifact_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            storage = ProductionStorage(sqlite_path)
            storage.save_evaluation_run(
                EvaluationRun(
                    run_id="other-eval",
                    suite="other_suite",
                    subject="other",
                    metrics={},
                    dataset_version="other",
                    artifact_manifest_path="outputs/other_manifest.json",
                )
            )

            payload = inspect_production_store(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual(1, len(payload["evaluation_runs"]))
        self.assertEqual("retrieval_baseline", payload["evaluation_runs"][0]["suite"])

    def test_inspect_function_exports_scoped_review_tasks_and_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            storage = ProductionStorage(sqlite_path)
            task = create_review_task(
                run_id="local-phase-output-run",
                governance_box=_governance_box(),
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                created_at="2026-06-14T00:00:00Z",
            )
            approved = decide_review(
                _reviewer_principal(),
                task,
                decision=ReviewDecision.APPROVE,
                comment="Reviewed for export.",
                decided_at="2026-06-14T00:05:00Z",
            )
            storage.record_review_task(
                task,
                audit_event_id="event-review-task-created",
                audit_created_at="2026-06-14T00:00:01Z",
            )
            storage.record_review_decision(
                approved,
                audit_event_id="event-review-decision-recorded",
                audit_created_at="2026-06-14T00:05:01Z",
            )

            payload = inspect_production_store(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual(1, len(payload["review_tasks"]))
        self.assertEqual("review-local-phase-output-run", payload["review_tasks"][0]["review_id"])
        self.assertEqual("approved", payload["review_tasks"][0]["status"])
        self.assertEqual("reviewer-1", payload["review_tasks"][0]["decision"]["reviewer_id"])

    def test_inspect_function_rejects_wrong_scope_for_review_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            storage.save_artifact_manifest(
                run_phase_manifest(
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )
            )
            task = create_review_task(
                run_id="run-001",
                governance_box=_governance_box(),
                tenant_id="tenant-b",
                workspace_id="workspace-a",
                created_at="2026-06-14T00:00:00Z",
            )
            storage.save_review_task(task)

            with self.assertRaises(PermissionError):
                inspect_production_store(
                    sqlite_db=sqlite_path,
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )

    def test_inspect_function_rejects_wrong_scope_for_connector_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            storage.save_artifact_manifest(
                run_phase_manifest(
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )
            )
            storage.save_connector_health_record(
                run_id="run-001",
                scope=ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                record=ConnectorHealthRecord(
                    source_id="dummy_corpus",
                    connector_name="DummyConnector",
                    status=ConnectorHealthStatus.OK,
                    checked_at="2026-06-14T00:00:00Z",
                    latency_ms=12,
                    details={},
                ),
            )
            storage.save_staged_connector_validation_record(
                run_id="run-001",
                scope=ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                record=StagedConnectorValidationRecord(
                    source_id="pubmed",
                    connector_name="PubMed",
                    stage=ValidationStage.REPLAY,
                    status=ConnectorHealthStatus.OK,
                    checked_at="2026-06-14T00:00:00Z",
                    query="VX-101",
                    limit=1,
                    document_count=1,
                    latency_ms=25,
                ),
            )

            with self.assertRaises(PermissionError):
                inspect_production_store(
                    sqlite_db=sqlite_path,
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )

    def test_inspect_function_exports_scoped_privacy_approval_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            storage = ProductionStorage(sqlite_path)
            record = _privacy_approval_record(
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            storage.record_privacy_approval(
                record,
                audit_event_id="event-privacy-approval",
                audit_created_at="2026-06-14T00:00:02Z",
            )

            payload = inspect_production_store(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual(1, len(payload["privacy_approval_records"]))
        self.assertEqual(
            "privacy-local-phase-output-run",
            payload["privacy_approval_records"][0]["approval_id"],
        )
        self.assertTrue(payload["privacy_approval_records"][0]["allowed"])

    def test_inspect_function_rejects_wrong_scope_for_privacy_approval_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            storage.save_artifact_manifest(
                run_phase_manifest(
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )
            )
            storage.save_privacy_approval_record(
                _privacy_approval_record(
                    run_id="run-001",
                    tenant_id="tenant-b",
                    workspace_id="workspace-a",
                )
            )

            with self.assertRaises(PermissionError):
                inspect_production_store(
                    sqlite_db=sqlite_path,
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )

    def test_inspect_function_exports_scoped_readiness_check_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            storage = ProductionStorage(sqlite_path)
            record = _readiness_check_result(
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )
            storage.record_readiness_check_result(
                record,
                audit_event_id="event-readiness-result",
                audit_created_at="2026-06-14T00:00:03Z",
            )

            payload = inspect_production_store(
                sqlite_db=sqlite_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
            )

        self.assertEqual(1, len(payload["readiness_check_results"]))
        self.assertEqual(
            "readiness-local-phase-output-run",
            payload["readiness_check_results"][0]["result_id"],
        )
        self.assertEqual("pass", payload["readiness_check_results"][0]["status"])

    def test_inspect_function_rejects_wrong_scope_for_readiness_check_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            storage.save_artifact_manifest(
                run_phase_manifest(
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )
            )
            storage.save_readiness_check_result(
                _readiness_check_result(
                    run_id="run-001",
                    tenant_id="tenant-b",
                    workspace_id="workspace-a",
                )
            )

            with self.assertRaises(PermissionError):
                inspect_production_store(
                    sqlite_db=sqlite_path,
                    run_id="run-001",
                    tenant_id="tenant-a",
                    workspace_id="workspace-a",
                )


def run_phase_manifest(run_id: str, tenant_id: str, workspace_id: str):
    from src.vyu.artifacts import ArtifactManifest

    return ArtifactManifest(
        run_id=run_id,
        environment="local",
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        corpus_version="synthetic-vx101-v1",
        index_version="bm25-local-v1",
        artifacts=[],
    )


def _governance_box() -> GovernanceBox:
    return GovernanceBox(
        question="Does VX-101 reduce migraine days?",
        sources_searched=["dummy_corpus"],
        search_run_at="2026-06-14T00:00:00Z",
        retrieved_count=5,
        included_count=5,
        excluded_count=0,
        evidence_mix={"reviewed": 4, "preprint": 1},
        conflicts=[],
        models={"generator": "deterministic_grounded_answer_v1"},
        policy_versions={"governance_policy": "governance_policy_v1"},
        human_review_required=True,
        human_review_reason="Preprint evidence is present",
        trust_score=TrustScore(
            overall=84,
            components={"citation_coverage": 100},
            warnings=["Preprint evidence is present"],
        ),
    )


def _reviewer_principal() -> Principal:
    return Principal(
        user_id="reviewer-1",
        memberships=(
            WorkspaceMembership(
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                roles=(Role.REVIEWER,),
            ),
        ),
    )


def _privacy_approval_record(
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> PrivacyApprovalRecord:
    return PrivacyApprovalRecord(
        approval_id=f"privacy-{run_id}",
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        purpose="patient_specific_recommendation",
        data_classification="ephi",
        decision_status="approved",
        allowed=True,
        reasons=("PHI/ePHI requires approved privacy clearance.",),
        missing_approvals=(),
        approvals=(
            {
                "approval_type": "privacy",
                "approved_by": "privacy-owner",
                "approved_at": "2026-06-14T00:00:00Z",
            },
        ),
        created_at="2026-06-14T00:00:01Z",
    )


def _readiness_check_result(
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> ReadinessCheckResultRecord:
    return ReadinessCheckResultRecord(
        result_id=f"readiness-{run_id}",
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        status="pass",
        checks=(
            {
                "name": "scoped_manifest_access",
                "passed": True,
                "message": "Manifest is readable within scope.",
            },
        ),
        artifact_manifest_path="outputs/artifact_manifest.json",
        run_summary_path="outputs/run_summary.json",
        created_at="2026-06-14T00:00:02Z",
    )


if __name__ == "__main__":
    unittest.main()
