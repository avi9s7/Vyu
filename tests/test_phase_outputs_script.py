import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from scripts.run_phase_outputs import run_phase_outputs
from src.vyu.storage import ProductionScope, ProductionStorage
from src.vyu.sources import ProductionSourceRecord, SourceRegistry


class PhaseOutputsScriptTests(unittest.TestCase):
    def test_run_phase_outputs_persists_phase_2_through_7_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            output_dir = root / "outputs"

            manifest = run_phase_outputs(root=root, output_dir=output_dir)

            expected_files = {
                "artifact_manifest.json",
                "run_summary.json",
                "evaluation/runs.jsonl",
                "phase2/connector_search_result.json",
                "phase2/connector_audit.jsonl",
                "phase3/evidence_object_manifest.json",
                "phase3/production_research_memory.json",
                "phase3/production_retrieval_run.json",
                "phase3/retrieval_hits.json",
                "phase3/retrieval_index_manifest.json",
                "phase3/retrieval_metrics.json",
                "phase4/evidence_context.json",
                "phase4/grounded_answer.json",
                "phase4/citation_validation.json",
                "phase5/governance_audit_record.json",
                "phase5/evidence_methodology_assessments.json",
                "phase5/evidence_methodology_run.json",
                "phase5/external_evidence_grading_request.json",
                "phase5/external_evidence_grading_response.json",
                "phase5/production_trust_score_record.json",
                "phase5/production_governance_box_record.json",
                "phase5/external_governance_request.json",
                "phase5/external_governance_response.json",
                "phase6/deep_dive_result.json",
                "phase6/evidence_brief.md",
                "phase6/research_report.md",
                "phase6/policy_output.md",
                "phase7/research_trajectory.json",
                "phase7/workflow_comparison.json",
                "phase7/adoption_report.md",
            }

            self.assertEqual(expected_files, set(manifest["artifacts"]))
            for relative_path in expected_files:
                self.assertTrue((output_dir / relative_path).is_file(), relative_path)

            search_result = json.loads(
                (output_dir / "phase2/connector_search_result.json").read_text(encoding="utf-8")
            )
            self.assertEqual("dummy", search_result["source"])
            self.assertGreaterEqual(search_result["document_count"], 1)

            metrics = json.loads(
                (output_dir / "phase3/retrieval_metrics.json").read_text(encoding="utf-8")
            )
            self.assertIn("recall_at_10", metrics)

            answer = json.loads(
                (output_dir / "phase4/grounded_answer.json").read_text(encoding="utf-8")
            )
            self.assertEqual("Does VX-101 reduce migraine days?", answer["question"])
            self.assertFalse(answer["abstained"])

            adoption_report = (output_dir / "phase7/adoption_report.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("RAG-Gym-Style Workflow Adoption Report", adoption_report)

            artifact_manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("local", artifact_manifest["environment"])
            self.assertEqual("hybrid-local-v1", artifact_manifest["index_version"])
            self.assertEqual(len(expected_files) - 2, len(artifact_manifest["artifacts"]))

            registry_lines = (output_dir / "evaluation/runs.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(1, len(registry_lines))
            registry_record = json.loads(registry_lines[0])
            self.assertEqual("retrieval_baseline", registry_record["suite"])
            self.assertEqual("outputs/artifact_manifest.json", registry_record["artifact_manifest_path"])

            run_summary = json.loads(
                (output_dir / "run_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual("local-phase-output-run", run_summary["run_id"])
            self.assertEqual(len(expected_files) - 2, run_summary["artifact_count"])
            self.assertEqual("hybrid-local-v1", run_summary["index_version"])
            self.assertIn("recall_at_10", run_summary["evaluation_metric_names"])
            self.assertIn(
                "--run-summary outputs/run_summary.json",
                run_summary["readiness_command"],
            )

    def test_run_phase_outputs_can_persist_production_storage_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            sqlite_path = root / "production.sqlite"

            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                sqlite_path=sqlite_path,
            )

            storage = ProductionStorage(sqlite_path)
            manifest = storage.get_artifact_manifest("local-phase-output-run")
            scoped_manifest = storage.get_artifact_manifest_for_scope(
                "local-phase-output-run",
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
            )
            evaluation_runs = storage.list_evaluation_runs(suite="retrieval_baseline")
            audit_events = storage.list_audit_events(run_id="local-phase-output-run")
            health_records = storage.list_connector_health_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            validation_records = (
                storage.list_staged_connector_validation_records_for_scope(
                    ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                    run_id="local-phase-output-run",
                )
            )
            review_tasks = storage.list_review_tasks_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            methodology_assessments = storage.list_evidence_methodology_assessment_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            methodology_runs = storage.list_evidence_methodology_run_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            external_requests = storage.list_external_evidence_grading_request_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            external_responses = storage.list_external_evidence_grading_response_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            trust_scores = storage.list_production_trust_score_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            governance_boxes = storage.list_production_governance_box_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            external_governance_requests = storage.list_external_governance_request_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )
            external_governance_responses = storage.list_external_governance_response_records_for_scope(
                ProductionScope(tenant_id="local_tenant", workspace_id="local_workspace"),
                run_id="local-phase-output-run",
            )

            with self.assertRaises(PermissionError):
                storage.get_artifact_manifest_for_scope(
                    "local-phase-output-run",
                    ProductionScope(tenant_id="other_tenant", workspace_id="local_workspace"),
                )

        self.assertEqual("synthetic-vx101-v1", manifest.corpus_version)
        self.assertEqual(manifest.to_json(), scoped_manifest.to_json())
        self.assertEqual(1, len(evaluation_runs))
        self.assertEqual("bm25", evaluation_runs[0].subject)
        self.assertEqual(1, len(health_records))
        self.assertEqual("ok", health_records[0].status.value)
        self.assertEqual(1, len(validation_records))
        self.assertEqual("replay", validation_records[0].stage.value)
        self.assertEqual(1, len(review_tasks))
        self.assertEqual("review-local-phase-output-run", review_tasks[0].review_id)
        self.assertEqual("pending", review_tasks[0].status.value)
        self.assertTrue(review_tasks[0].reason)
        self.assertEqual(5, len(methodology_assessments))
        self.assertEqual(1, len(methodology_runs))
        self.assertEqual(1, len(external_requests))
        self.assertEqual(1, len(external_responses))
        self.assertEqual(1, len(trust_scores))
        self.assertEqual(1, len(governance_boxes))
        self.assertEqual(1, len(external_governance_requests))
        self.assertEqual(1, len(external_governance_responses))
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

    def test_run_phase_outputs_can_append_audit_events_on_repeated_sqlite_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sqlite_path = root / "production.sqlite"

            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )
            run_phase_outputs(
                root=root,
                output_dir=root / "outputs",
                sqlite_path=sqlite_path,
            )

            storage = ProductionStorage(sqlite_path)
            audit_events = storage.list_audit_events(run_id="local-phase-output-run")

        self.assertEqual(44, len(audit_events))
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

    def test_run_phase_outputs_embeds_approved_source_registry_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            registry_path = root / "source_registry.json"
            SourceRegistry(
                [
                    _approved_source("dummy_corpus", ["artifact_generation"]),
                    _approved_source("golden_questions", ["artifact_generation"]),
                ]
            ).write(registry_path)

            run_phase_outputs(
                root=root,
                output_dir=output_dir,
                source_registry_path=registry_path,
            )

            run_summary = json.loads(
                (output_dir / "run_summary.json").read_text(encoding="utf-8")
            )
            artifact_manifest = json.loads(
                (output_dir / "artifact_manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(2, run_summary["source_count"])
        self.assertEqual(
            ["dummy_corpus", "golden_questions"],
            [source["source_id"] for source in artifact_manifest["sources"]],
        )
        self.assertEqual(
            "approved",
            artifact_manifest["sources"][0]["approval_status"],
        )

    def test_run_phase_outputs_rejects_unapproved_registry_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "source_registry.json"
            SourceRegistry(
                [
                    ProductionSourceRecord(
                        source_id="dummy_corpus",
                        display_name="Dummy Corpus",
                        source_type="public_literature",
                        owner="Vyu",
                        license_or_terms="Synthetic local fixture",
                        allowed_uses=["artifact_generation"],
                        approval_status="draft",
                    ),
                    _approved_source("golden_questions", ["artifact_generation"]),
                ]
            ).write(registry_path)

            with self.assertRaises(PermissionError):
                run_phase_outputs(
                    root=root,
                    output_dir=root / "outputs",
                    source_registry_path=registry_path,
                )

    def test_run_phase_outputs_script_can_be_executed_directly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_phase_outputs.py"

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--root",
                    str(root),
                    "--output-dir",
                    str(root / "outputs"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((root / "outputs" / "phase7" / "adoption_report.md").is_file())


def _approved_source(source_id: str, allowed_uses: list[str]) -> ProductionSourceRecord:
    return ProductionSourceRecord(
        source_id=source_id,
        display_name=source_id.replace("_", " ").title(),
        source_type="public_literature",
        owner="Vyu",
        license_or_terms="Synthetic local fixture",
        allowed_uses=allowed_uses,
        approval_status="approved",
        approved_by="production-review-board",
        approved_at="2026-06-13T00:00:00Z",
    )


if __name__ == "__main__":
    unittest.main()
