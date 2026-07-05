import tempfile
import unittest
from pathlib import Path

from src.vyu.artifacts import ArtifactManifest, ArtifactRecord
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
from src.vyu.review import (
    ReviewDecision,
    ReviewStatus,
    create_review_task,
    decide_review,
)
from src.vyu.storage.production import (
    BASELINE_MIGRATION_NAME,
    CONNECTOR_HEALTH_MIGRATION_NAME,
    EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME,
    EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME,
    GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME,
    PRODUCTION_SCHEMA_VERSION,
    ProductionAuditEvent,
    PrivacyApprovalRecord,
    PRIVACY_APPROVAL_MIGRATION_NAME,
    ProductionScope,
    ProductionStorage,
    ReadinessCheckResultRecord,
    READINESS_RESULT_MIGRATION_NAME,
    RESEARCH_MCP_MIGRATION_NAME,
    REVIEW_TASKS_MIGRATION_NAME,
)


class ProductionStorageTests(unittest.TestCase):
    def test_initialize_records_current_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()

            schema_version = storage.get_schema_version()

        self.assertEqual(PRODUCTION_SCHEMA_VERSION, schema_version)

    def test_initialize_records_migration_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()

            migrations = storage.list_migrations()

        self.assertEqual(9, len(migrations))
        self.assertEqual(1, migrations[0]["version"])
        self.assertEqual(BASELINE_MIGRATION_NAME, migrations[0]["name"])
        self.assertTrue(migrations[0]["applied_at"])
        self.assertEqual(2, migrations[1]["version"])
        self.assertEqual(REVIEW_TASKS_MIGRATION_NAME, migrations[1]["name"])
        self.assertTrue(migrations[1]["applied_at"])
        self.assertEqual(3, migrations[2]["version"])
        self.assertEqual(CONNECTOR_HEALTH_MIGRATION_NAME, migrations[2]["name"])
        self.assertTrue(migrations[2]["applied_at"])
        self.assertEqual(4, migrations[3]["version"])
        self.assertEqual(PRIVACY_APPROVAL_MIGRATION_NAME, migrations[3]["name"])
        self.assertTrue(migrations[3]["applied_at"])
        self.assertEqual(5, migrations[4]["version"])
        self.assertEqual(READINESS_RESULT_MIGRATION_NAME, migrations[4]["name"])
        self.assertTrue(migrations[4]["applied_at"])
        self.assertEqual(6, migrations[5]["version"])
        self.assertEqual(EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME, migrations[5]["name"])
        self.assertTrue(migrations[5]["applied_at"])
        self.assertEqual(7, migrations[6]["version"])
        self.assertEqual(EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME, migrations[6]["name"])
        self.assertTrue(migrations[6]["applied_at"])
        self.assertEqual(8, migrations[7]["version"])
        self.assertEqual(GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME, migrations[7]["name"])
        self.assertTrue(migrations[7]["applied_at"])
        self.assertEqual(9, migrations[8]["version"])
        self.assertEqual(RESEARCH_MCP_MIGRATION_NAME, migrations[8]["name"])
        self.assertTrue(migrations[8]["applied_at"])

    def test_persists_and_loads_artifact_manifest_by_run_id(self):
        manifest = ArtifactManifest(
            run_id="run-001",
            environment="staging",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            corpus_version="corpus-v1",
            index_version="index-v1",
            artifacts=[
                ArtifactRecord(
                    phase="phase4",
                    path="phase4/grounded_answer.json",
                    artifact_type="grounded_answer",
                    source_ids=["pubmed"],
                    checksum_sha256="abc123",
                )
            ],
            sources=[{"source_id": "pubmed", "approval_status": "approved"}],
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_artifact_manifest(manifest)
            loaded = storage.get_artifact_manifest("run-001")

        self.assertEqual(manifest.to_json(), loaded.to_json())

    def test_persists_and_queries_evaluation_runs_by_suite(self):
        run = EvaluationRun(
            run_id="eval-001",
            suite="retrieval_baseline",
            subject="bm25",
            metrics={"recall_at_10": 0.75},
            dataset_version="golden-v1",
            artifact_manifest_path="outputs/artifact_manifest.json",
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_evaluation_run(run)
            loaded = storage.list_evaluation_runs(suite="retrieval_baseline")

        self.assertEqual([run.to_json()], [item.to_json() for item in loaded])

    def test_replaces_manifest_for_same_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_artifact_manifest(_manifest("index-v1"))
            storage.save_artifact_manifest(_manifest("index-v2"))

            loaded = storage.get_artifact_manifest("run-001")

        self.assertEqual("index-v2", loaded.index_version)

    def test_appends_and_queries_audit_events_by_run_id_and_type(self):
        event = ProductionAuditEvent(
            event_id="event-001",
            run_id="run-001",
            event_type="artifact_manifest_saved",
            payload={"artifact_count": 2},
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.append_audit_event(event)

            by_run = storage.list_audit_events(run_id="run-001")
            by_type = storage.list_audit_events(event_type="artifact_manifest_saved")

        self.assertEqual([event.to_json()], [item.to_json() for item in by_run])
        self.assertEqual([event.to_json()], [item.to_json() for item in by_type])

    def test_audit_events_are_append_only_for_duplicate_event_ids(self):
        event = ProductionAuditEvent(
            event_id="event-001",
            run_id="run-001",
            event_type="artifact_manifest_saved",
            payload={},
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.append_audit_event(event)
            with self.assertRaises(ValueError):
                storage.append_audit_event(event)

    def test_scoped_manifest_read_requires_matching_tenant_and_workspace(self):
        manifest = ArtifactManifest(
            run_id="run-001",
            environment="staging",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            corpus_version="corpus-v1",
            index_version="index-v1",
            artifacts=[],
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_artifact_manifest(manifest)

            allowed = storage.get_artifact_manifest_for_scope(
                "run-001",
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
            )

            with self.assertRaises(PermissionError):
                storage.get_artifact_manifest_for_scope(
                    "run-001",
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                )

        self.assertEqual(manifest.to_json(), allowed.to_json())

    def test_scoped_audit_event_query_requires_matching_manifest_scope(self):
        manifest = ArtifactManifest(
            run_id="run-001",
            environment="staging",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            corpus_version="corpus-v1",
            index_version="index-v1",
            artifacts=[],
        )
        event = ProductionAuditEvent(
            event_id="event-001",
            run_id="run-001",
            event_type="artifact_manifest_saved",
            payload={},
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_artifact_manifest(manifest)
            storage.append_audit_event(event)

            allowed = storage.list_audit_events_for_scope(
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                run_id="run-001",
            )

            with self.assertRaises(PermissionError):
                storage.list_audit_events_for_scope(
                    ProductionScope(tenant_id="tenant-a", workspace_id="workspace-b"),
                    run_id="run-001",
                )

        self.assertEqual([event.to_json()], [item.to_json() for item in allowed])

    def test_records_review_task_with_audit_event(self):
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_review_task(
                task,
                audit_event_id="event-review-task-created",
                audit_created_at="2026-06-14T00:00:01Z",
            )

            loaded = storage.get_review_task("review-run-001")
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="review_task_created",
            )

        self.assertEqual(task.to_json(), loaded.to_json())
        self.assertEqual(1, len(events))
        self.assertEqual("review-run-001", events[0].payload["review_id"])
        self.assertEqual("pending", events[0].payload["status"])

    def test_records_review_decision_with_audit_event(self):
        reviewer = _reviewer_principal()
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )
        approved = decide_review(
            reviewer,
            task,
            decision=ReviewDecision.APPROVE,
            comment="Reviewed for export.",
            decided_at="2026-06-14T00:05:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
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

            loaded = storage.get_review_task("review-run-001")
            events = storage.list_audit_events(run_id="run-001")

        self.assertEqual(ReviewStatus.APPROVED.value, loaded.status.value)
        self.assertEqual(approved.to_json(), loaded.to_json())
        self.assertEqual(
            ["review_task_created", "review_decision_recorded"],
            [event.event_type for event in events],
        )
        self.assertEqual("reviewer-1", events[1].payload["reviewer_id"])
        self.assertEqual("approve", events[1].payload["decision"])

    def test_scoped_review_task_reads_require_matching_tenant_and_workspace(self):
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_review_task(
                task,
                audit_event_id="event-review-task-created",
                audit_created_at="2026-06-14T00:00:01Z",
            )

            allowed = storage.list_review_tasks_for_scope(
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                run_id="run-001",
            )

            with self.assertRaises(PermissionError):
                storage.list_review_tasks_for_scope(
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                    run_id="run-001",
                )

        self.assertEqual([task.to_json()], [item.to_json() for item in allowed])

    def test_records_connector_health_with_audit_event(self):
        record = ConnectorHealthRecord(
            source_id="dummy_corpus",
            connector_name="DummyConnector",
            status=ConnectorHealthStatus.OK,
            checked_at="2026-06-14T00:00:00Z",
            latency_ms=12,
            details={"document_count": 5},
        )
        scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_connector_health(
                run_id="run-001",
                scope=scope,
                record=record,
                audit_event_id="event-connector-health",
                audit_created_at="2026-06-14T00:00:01Z",
            )

            loaded = storage.list_connector_health_records_for_scope(
                scope,
                run_id="run-001",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="connector_health_recorded",
            )

        self.assertEqual([record.to_json()], [item.to_json() for item in loaded])
        self.assertEqual(1, len(events))
        self.assertEqual("dummy_corpus", events[0].payload["source_id"])
        self.assertEqual("ok", events[0].payload["status"])

    def test_records_staged_connector_validation_with_audit_event(self):
        record = StagedConnectorValidationRecord(
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
        scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_staged_connector_validation(
                run_id="run-001",
                scope=scope,
                record=record,
                audit_event_id="event-connector-validation",
                audit_created_at="2026-06-14T00:00:01Z",
            )

            loaded = storage.list_staged_connector_validation_records_for_scope(
                scope,
                run_id="run-001",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="connector_validation_recorded",
            )

        self.assertEqual([record.to_json()], [item.to_json() for item in loaded])
        self.assertEqual(1, len(events))
        self.assertEqual("pubmed", events[0].payload["source_id"])
        self.assertEqual("replay", events[0].payload["stage"])

    def test_scoped_connector_reads_require_matching_tenant_and_workspace(self):
        health = ConnectorHealthRecord(
            source_id="dummy_corpus",
            connector_name="DummyConnector",
            status=ConnectorHealthStatus.OK,
            checked_at="2026-06-14T00:00:00Z",
            latency_ms=12,
            details={},
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

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_connector_health(
                run_id="run-001",
                scope=ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                record=health,
                audit_event_id="event-connector-health",
                audit_created_at="2026-06-14T00:00:01Z",
            )
            storage.record_staged_connector_validation(
                run_id="run-001",
                scope=ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                record=validation,
                audit_event_id="event-connector-validation",
                audit_created_at="2026-06-14T00:00:02Z",
            )

            with self.assertRaises(PermissionError):
                storage.list_connector_health_records_for_scope(
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                    run_id="run-001",
                )
            with self.assertRaises(PermissionError):
                storage.list_staged_connector_validation_records_for_scope(
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                    run_id="run-001",
                )

    def test_records_privacy_approval_with_audit_event(self):
        record = PrivacyApprovalRecord(
            approval_id="privacy-run-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
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
                {
                    "approval_type": "security",
                    "approved_by": "security-owner",
                    "approved_at": "2026-06-14T00:00:00Z",
                },
            ),
            created_at="2026-06-14T00:00:01Z",
        )
        scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_privacy_approval(
                record,
                audit_event_id="event-privacy-approval",
                audit_created_at="2026-06-14T00:00:02Z",
            )

            loaded = storage.list_privacy_approval_records_for_scope(
                scope,
                run_id="run-001",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="privacy_approval_recorded",
            )

        self.assertEqual([record.to_json()], [item.to_json() for item in loaded])
        self.assertEqual(1, len(events))
        self.assertEqual("privacy-run-001", events[0].payload["approval_id"])
        self.assertEqual("approved", events[0].payload["decision_status"])
        self.assertTrue(events[0].payload["allowed"])

    def test_scoped_privacy_approval_reads_require_matching_tenant_and_workspace(self):
        record = PrivacyApprovalRecord(
            approval_id="privacy-run-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            purpose="model_provider_call",
            data_classification="phi",
            decision_status="blocked",
            allowed=False,
            reasons=("PHI/ePHI cannot be sent to a model provider without provider-specific approval.",),
            missing_approvals=("model_provider",),
            approvals=(),
            created_at="2026-06-14T00:00:01Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_privacy_approval_record(record)

            with self.assertRaises(PermissionError):
                storage.list_privacy_approval_records_for_scope(
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                    run_id="run-001",
                )

    def test_records_readiness_check_result_with_audit_event(self):
        record = ReadinessCheckResultRecord(
            result_id="readiness-run-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
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
        scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_readiness_check_result(
                record,
                audit_event_id="event-readiness-result",
                audit_created_at="2026-06-14T00:00:03Z",
            )

            loaded = storage.list_readiness_check_results_for_scope(
                scope,
                run_id="run-001",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="readiness_check_result_recorded",
            )

        self.assertEqual([record.to_json()], [item.to_json() for item in loaded])
        self.assertEqual(1, len(events))
        self.assertEqual("readiness-run-001", events[0].payload["result_id"])
        self.assertEqual("pass", events[0].payload["status"])
        self.assertEqual(1, events[0].payload["check_count"])
        self.assertEqual([], events[0].payload["failed_checks"])

    def test_scoped_readiness_check_results_require_matching_tenant_and_workspace(self):
        record = ReadinessCheckResultRecord(
            result_id="readiness-run-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            status="fail",
            checks=(
                {
                    "name": "artifact_checksums_present",
                    "passed": False,
                    "message": "Artifacts missing checksums: phase4/answer.json",
                },
            ),
            artifact_manifest_path="outputs/artifact_manifest.json",
            run_summary_path="outputs/run_summary.json",
            created_at="2026-06-14T00:00:02Z",
        )

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.save_readiness_check_result(record)

            with self.assertRaises(PermissionError):
                storage.list_readiness_check_results_for_scope(
                    ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                    run_id="run-001",
                )

    def test_records_research_mcp_plan_tool_call_and_replay_with_scope(self):
        from src.vyu.research_mcp import (
            ResearchScope,
            ResearchSearchPlanner,
            ResearchToolDefinition,
            ResearchToolRegistry,
            ToolCallAuditRecord,
            ToolCallReplayRecord,
        )
        from src.vyu.research_mcp.audit import ProductionReplayStore, ProductionToolCallAuditSink
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
        record = ToolCallAuditRecord(
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
            request_hash=record.request_hash,
            result_hash=record.result_hash,
            request_payload={
                "run_id": record.run_id,
                "plan_id": record.plan_id,
                "scope": {
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "user_id": record.user_id,
                },
                "tool_id": record.tool_id,
                "source_id": record.source_id,
                "connector_name": record.connector_name,
                "action": record.action,
                "request": {"query": record.query, "limit": 1, "filters": {}},
            },
            result_payload={
                "source": record.source_id,
                "request": {"query": record.query, "limit": 1, "filters": {}},
                "documents": [],
                "passages": [],
            },
            created_at="2026-06-18T00:00:02Z",
        )
        scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")

        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "vyu.db")
            storage.initialize()
            storage.record_research_mcp_plan(
                plan,
                audit_event_id="event-plan",
                audit_created_at="2026-06-18T00:00:00Z",
            )
            ProductionToolCallAuditSink(storage).append(record)
            ProductionReplayStore(storage, scope).append(replay)

            plans = storage.list_research_mcp_plans_for_scope(scope, run_id="run-001")
            calls = storage.list_research_mcp_tool_calls_for_scope(scope, run_id="run-001")
            replay_records = storage.list_research_mcp_replay_records_for_scope(scope, run_id="run-001")
            readiness = storage.research_mcp_readiness_for_scope(scope, run_id="run-001")
            audit_events = storage.list_audit_events(run_id="run-001")

            with self.assertRaises(PermissionError):
                storage.get_research_mcp_replay_record(
                    record.request_hash,
                    scope=ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a"),
                )

        self.assertEqual([plan.to_json()], [item.to_json() for item in plans])
        self.assertEqual([record.to_json()], [item.to_json() for item in calls])
        self.assertEqual([replay.to_json()], [item.to_json() for item in replay_records])
        self.assertEqual({"plan_ok": True, "tool_call_ok": True, "replay_ok": True}, readiness)
        self.assertEqual(
            ["research_mcp_plan_recorded", "research_mcp_tool_call_recorded"],
            [event.event_type for event in audit_events],
        )


def _manifest(index_version: str) -> ArtifactManifest:
    return ArtifactManifest(
        run_id="run-001",
        environment="local",
        tenant_id="local_tenant",
        workspace_id="local_workspace",
        corpus_version="synthetic-vx101-v1",
        index_version=index_version,
        artifacts=[],
    )


def _governance_box(human_review_required: bool) -> GovernanceBox:
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
        human_review_required=human_review_required,
        human_review_reason=(
            "Preprint evidence is present"
            if human_review_required
            else "No POC governance warnings"
        ),
        trust_score=TrustScore(
            overall=84 if human_review_required else 92,
            components={"citation_coverage": 100},
            warnings=["Preprint evidence is present"] if human_review_required else [],
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


if __name__ == "__main__":
    unittest.main()
