import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.backup_production_store import (
    export_production_backup,
    restore_production_backup,
)
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.connectors.health import (
    ConnectorHealthRecord,
    ConnectorHealthStatus,
    StagedConnectorValidationRecord,
    ValidationStage,
)
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import ReviewDecision, create_review_task, decide_review
from src.vyu.storage import (
    PRODUCTION_SCHEMA_VERSION,
    PrivacyApprovalRecord,
    ProductionScope,
    ProductionStorage,
    ReadinessCheckResultRecord,
)


class ProductionBackupTests(unittest.TestCase):
    def test_exports_and_restores_production_store_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)

            restored_storage = ProductionStorage(restored_sqlite_path)
            manifest = restored_storage.get_artifact_manifest_for_scope(
                "local-phase-output-run",
                ProductionScope(
                    tenant_id="local_tenant",
                    workspace_id="local_workspace",
                ),
            )
            evaluation_runs = restored_storage.list_evaluation_runs(
                suite="retrieval_baseline"
            )
            audit_events = restored_storage.list_audit_events(
                run_id="local-phase-output-run"
            )
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

            self.assertEqual(1, export_payload["artifact_manifest_count"])
            self.assertEqual(1, export_payload["evaluation_run_count"])
            self.assertEqual(1, export_payload["connector_health_record_count"])
            self.assertEqual(1, export_payload["connector_validation_record_count"])
            self.assertEqual(1, export_payload["review_task_count"])
            self.assertEqual(0, export_payload["privacy_approval_record_count"])
            self.assertEqual(0, export_payload["readiness_check_result_count"])
            self.assertEqual(1, export_payload["evidence_methodology_run_record_count"])
            self.assertEqual(5, export_payload["evidence_methodology_assessment_record_count"])
            self.assertEqual(0, export_payload["reviewer_evidence_rating_record_count"])
            self.assertEqual(1, export_payload["external_evidence_grading_request_record_count"])
            self.assertEqual(1, export_payload["external_evidence_grading_response_record_count"])
            self.assertEqual(1, export_payload["production_trust_score_record_count"])
            self.assertEqual(1, export_payload["production_governance_box_record_count"])
            self.assertEqual(0, export_payload["reviewer_trust_score_override_record_count"])
            self.assertEqual(1, export_payload["external_governance_request_record_count"])
            self.assertEqual(1, export_payload["external_governance_response_record_count"])
            self.assertEqual(22, export_payload["audit_event_count"])
            self.assertEqual(export_payload, restore_payload["restored_counts"])
            self.assertEqual("synthetic-vx101-v1", manifest.corpus_version)
            self.assertEqual(1, len(evaluation_runs))
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
                [event.event_type for event in audit_events],
            )
            self.assertEqual(1, backup["backup_schema_version"])
            self.assertEqual(PRODUCTION_SCHEMA_VERSION, backup["production_schema_version"])
            self.assertEqual(
                "baseline_production_schema",
                backup["production_migrations"][0]["name"],
            )
            self.assertEqual(
                "local-phase-output-run",
                backup["artifact_manifests"][0]["run_id"],
            )
            self.assertEqual(
                "review-local-phase-output-run",
                backup["review_tasks"][0]["review_id"],
            )

    def test_backup_includes_and_restores_review_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            task = create_review_task(
                run_id="run-001",
                governance_box=_governance_box(),
                tenant_id="tenant-a",
                workspace_id="workspace-a",
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

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)
            restored_storage = ProductionStorage(restored_sqlite_path)
            restored_tasks = restored_storage.list_review_tasks_for_scope(
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                run_id="run-001",
            )
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(1, export_payload["review_task_count"])
        self.assertEqual(1, restore_payload["restored_counts"]["review_task_count"])
        self.assertEqual([approved.to_json()], [item.to_json() for item in restored_tasks])
        self.assertEqual("review-run-001", backup["review_tasks"][0]["review_id"])

    def test_backup_includes_and_restores_connector_health_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            health = ConnectorHealthRecord(
                source_id="dummy_corpus",
                connector_name="DummyConnector",
                status=ConnectorHealthStatus.OK,
                checked_at="2026-06-14T00:00:00Z",
                latency_ms=12,
                details={"document_count": 5},
            )
            validation = StagedConnectorValidationRecord(
                source_id="pubmed",
                connector_name="PubMed",
                stage=ValidationStage.REPLAY,
                status=ConnectorHealthStatus.OK,
                checked_at="2026-06-14T00:00:00Z",
                query="VX-101",
                limit=1,
                document_count=1,
                latency_ms=25,
            )
            storage.record_connector_health(
                run_id="run-001",
                scope=scope,
                record=health,
                audit_event_id="event-connector-health",
                audit_created_at="2026-06-14T00:00:01Z",
            )
            storage.record_staged_connector_validation(
                run_id="run-001",
                scope=scope,
                record=validation,
                audit_event_id="event-connector-validation",
                audit_created_at="2026-06-14T00:00:02Z",
            )

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)
            restored_storage = ProductionStorage(restored_sqlite_path)
            restored_health = restored_storage.list_connector_health_records_for_scope(
                scope,
                run_id="run-001",
            )
            restored_validation = (
                restored_storage.list_staged_connector_validation_records_for_scope(
                    scope,
                    run_id="run-001",
                )
            )
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(1, export_payload["connector_health_record_count"])
        self.assertEqual(1, export_payload["connector_validation_record_count"])
        self.assertEqual(
            1,
            restore_payload["restored_counts"]["connector_health_record_count"],
        )
        self.assertEqual(
            1,
            restore_payload["restored_counts"]["connector_validation_record_count"],
        )
        self.assertEqual([health.to_json()], [item.to_json() for item in restored_health])
        self.assertEqual(
            [validation.to_json()],
            [item.to_json() for item in restored_validation],
        )
        self.assertEqual("dummy_corpus", backup["connector_health_records"][0]["source_id"])
        self.assertEqual("pubmed", backup["connector_validation_records"][0]["source_id"])

    def test_backup_includes_and_restores_privacy_approval_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            record = _privacy_approval_record(
                run_id="run-001",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
            )
            storage.record_privacy_approval(
                record,
                audit_event_id="event-privacy-approval",
                audit_created_at="2026-06-14T00:00:02Z",
            )

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)
            restored_storage = ProductionStorage(restored_sqlite_path)
            restored_records = restored_storage.list_privacy_approval_records_for_scope(
                scope,
                run_id="run-001",
            )
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(1, export_payload["privacy_approval_record_count"])
        self.assertEqual(
            1,
            restore_payload["restored_counts"]["privacy_approval_record_count"],
        )
        self.assertEqual([record.to_json()], [item.to_json() for item in restored_records])
        self.assertEqual(
            "privacy-run-001",
            backup["privacy_approval_records"][0]["approval_id"],
        )

    def test_backup_includes_and_restores_readiness_check_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            record = _readiness_check_result(
                run_id="run-001",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
            )
            storage.record_readiness_check_result(
                record,
                audit_event_id="event-readiness-result",
                audit_created_at="2026-06-14T00:00:03Z",
            )

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)
            restored_storage = ProductionStorage(restored_sqlite_path)
            restored_records = restored_storage.list_readiness_check_results_for_scope(
                scope,
                run_id="run-001",
            )
            backup = json.loads(backup_path.read_text(encoding="utf-8"))

        self.assertEqual(1, export_payload["readiness_check_result_count"])
        self.assertEqual(
            1,
            restore_payload["restored_counts"]["readiness_check_result_count"],
        )
        self.assertEqual([record.to_json()], [item.to_json() for item in restored_records])
        self.assertEqual(
            "readiness-run-001",
            backup["readiness_check_results"][0]["result_id"],
        )

    def test_backup_script_exports_and_restores_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "backup_production_store.py"
            )

            export_result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "export",
                    "--sqlite-db",
                    str(sqlite_path),
                    "--backup",
                    str(backup_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            restore_result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "restore",
                    "--backup",
                    str(backup_path),
                    "--sqlite-db",
                    str(restored_sqlite_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            backup_exists = backup_path.is_file()
            restored_sqlite_exists = restored_sqlite_path.is_file()

        self.assertEqual(0, export_result.returncode, export_result.stderr)
        self.assertEqual(0, restore_result.returncode, restore_result.stderr)
        self.assertTrue(backup_exists)
        self.assertTrue(restored_sqlite_exists)
        self.assertEqual("exported", json.loads(export_result.stdout)["status"])
        self.assertEqual("restored", json.loads(restore_result.stdout)["status"])
    def test_backup_includes_and_restores_research_mcp_records(self):
        from src.vyu.research_mcp import (
            ResearchScope,
            ResearchSearchPlanner,
            ResearchToolDefinition,
            ResearchToolRegistry,
            ToolCallAuditRecord,
            ToolCallReplayRecord,
        )
        from src.vyu.sources import ProductionSourceRecord, SourceRegistry

        source_registry = SourceRegistry([
            ProductionSourceRecord(
                source_id="pubmed",
                display_name="PubMed",
                source_type="public_literature",
                owner="National Library of Medicine",
                license_or_terms="NLM/NCBI usage terms",
                allowed_uses=["literature_search"],
                access_policy="tenant:tenant-a:workspace:workspace-a",
                approval_status="approved",
                approved_by="production-review-board",
                approved_at="2026-06-13T00:00:00Z",
            )
        ])
        tool_registry = ResearchToolRegistry([
            ResearchToolDefinition(
                tool_id="pubmed.search",
                display_name="PubMed Search",
                source_id="pubmed",
                connector_name="pubmed",
                approved=True,
                max_results=1,
            )
        ])
        plan = ResearchSearchPlanner(tool_registry, source_registry).plan(
            "VX-101 migraine",
            run_id="run-001",
            scope=ResearchScope(tenant_id="tenant-a", workspace_id="workspace-a", user_id="user-a"),
            max_steps=1,
        )
        step = plan.steps[0]
        call = ToolCallAuditRecord(
            call_id="mcp-call-001",
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            tenant_id=plan.scope.tenant_id,
            workspace_id=plan.scope.workspace_id,
            user_id=plan.scope.user_id,
            tool_id=step.tool_id,
            source_id=step.source_id,
            connector_name=step.connector_name,
            action=step.action,
            query=step.query,
            request_hash="req-hash",
            result_hash="res-hash",
            result_count=1,
            result_document_ids=("PUBMED-123",),
            status="ok",
            created_at="2026-06-18T00:00:01Z",
        )
        replay = ToolCallReplayRecord(
            request_hash=call.request_hash,
            result_hash=call.result_hash,
            request_payload={
                "run_id": call.run_id,
                "plan_id": call.plan_id,
                "scope": {
                    "tenant_id": call.tenant_id,
                    "workspace_id": call.workspace_id,
                    "user_id": call.user_id,
                },
                "tool_id": call.tool_id,
                "source_id": call.source_id,
                "connector_name": call.connector_name,
                "action": call.action,
                "request": {"query": call.query, "limit": 1, "filters": {}},
            },
            result_payload={
                "source": call.source_id,
                "request": {"query": call.query, "limit": 1, "filters": {}},
                "documents": [],
                "passages": [],
            },
            created_at="2026-06-18T00:00:02Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"
            backup_path = root / "production_backup.json"
            restored_sqlite_path = root / "restored.sqlite"
            storage = ProductionStorage(sqlite_path)
            storage.initialize()
            storage.save_research_mcp_plan(plan)
            storage.save_research_mcp_tool_call(call)
            storage.save_research_mcp_replay_record(replay)

            export_payload = export_production_backup(sqlite_path, backup_path)
            restore_payload = restore_production_backup(backup_path, restored_sqlite_path)
            restored_storage = ProductionStorage(restored_sqlite_path)
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            restored_plans = restored_storage.list_research_mcp_plans_for_scope(scope, run_id="run-001")
            restored_calls = restored_storage.list_research_mcp_tool_calls_for_scope(scope, run_id="run-001")
            restored_replays = restored_storage.list_research_mcp_replay_records_for_scope(scope, run_id="run-001")

        self.assertEqual(1, export_payload["research_mcp_plan_count"])
        self.assertEqual(1, export_payload["research_mcp_tool_call_count"])
        self.assertEqual(1, export_payload["research_mcp_replay_record_count"])
        self.assertEqual(1, restore_payload["restored_counts"]["research_mcp_plan_count"])
        self.assertEqual([plan.to_json()], [item.to_json() for item in restored_plans])
        self.assertEqual([call.to_json()], [item.to_json() for item in restored_calls])
        self.assertEqual([replay.to_json()], [item.to_json() for item in restored_replays])


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
                tenant_id="tenant-a",
                workspace_id="workspace-a",
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
