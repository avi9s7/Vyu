import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA,
    DeploymentReleaseChannelTargetDecisionRecord,
    build_deployment_release_channel_target_decision_record,
    write_deployment_release_channel_target_decision_record,
)


class DeploymentReleaseChannelTargetDecisionTests(unittest.TestCase):
    def test_target_decision_selects_candidate_family_for_ready_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_readiness_path = _write_target_readiness_fixture(root)

            record = build_deployment_release_channel_target_decision_record(
                target_readiness_path=target_readiness_path,
                root=root,
                decision="choose",
                selected_target_family="serverless_function",
                operator_id="target-operator",
                operator_role="deployment_operator",
                rationale="Serverless function matches the current package handler boundary.",
                decided_at="2026-06-15T05:00:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(record, DeploymentReleaseChannelTargetDecisionRecord)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA, payload["schema_version"])
        self.assertEqual("selected", payload["status"])
        self.assertEqual("choose", payload["decision"]["value"])
        self.assertEqual("serverless_function", payload["decision"]["selected_target_family"])
        self.assertIsNone(payload["selected_target_provider"])
        self.assertEqual({}, payload["provider_configuration"])
        self.assertEqual("local_target_family_review_only", payload["target_selection_scope"])
        self.assertRegex(payload["target_readiness"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("ready", payload["target_readiness"]["status"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("release-operator", payload["inherited_operator"]["id"])
        self.assertEqual("a" * 64, payload["evidence_hashes"]["evidence_index_sha256"])
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["target_readiness_status_ready"]["passed"])
        self.assertTrue(checks["target_readiness_checks_passed"]["passed"])
        self.assertTrue(checks["choose_requires_candidate_target_family"]["passed"])
        self.assertTrue(checks["no_target_provider_selected"]["passed"])
        self.assertTrue(checks["no_provider_configuration_recorded"]["passed"])
        self.assertTrue(checks["next_actions_present"]["passed"])

    def test_target_decision_blocks_unknown_target_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_readiness_path = _write_target_readiness_fixture(root)

            record = build_deployment_release_channel_target_decision_record(
                target_readiness_path=target_readiness_path,
                root=root,
                decision="choose",
                selected_target_family="bare_metal_cluster",
                operator_id="target-operator",
                operator_role="deployment_operator",
                rationale="Attempting an unsupported target family.",
                decided_at="2026-06-15T05:05:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["choose_requires_candidate_target_family"]["passed"])
        self.assertIn("choose_requires_candidate_target_family", payload["blocking_reasons"])

    def test_target_decision_defers_without_selected_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_readiness_path = _write_target_readiness_fixture(root)

            record = build_deployment_release_channel_target_decision_record(
                target_readiness_path=target_readiness_path,
                root=root,
                decision="defer",
                operator_id="target-operator",
                operator_role="deployment_operator",
                rationale="Target selection is deferred pending security review.",
                decided_at="2026-06-15T05:10:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("deferred", payload["status"])
        self.assertIsNone(payload["decision"]["selected_target_family"])
        self.assertTrue(checks["block_or_defer_requires_no_selected_target_family"]["passed"])

    def test_writer_and_command_write_target_decision_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_readiness_path = _write_target_readiness_fixture(root)
            output_path = root / "outputs" / "deployment_release_channel_target_decision.json"

            record = build_deployment_release_channel_target_decision_record(
                target_readiness_path=target_readiness_path,
                root=root,
                decision="choose",
                selected_target_family="container_service",
                operator_id="target-operator",
                operator_role="deployment_operator",
                rationale="Container service is selected for the next planning boundary.",
                decided_at="2026-06-15T05:15:00Z",
            )
            write_deployment_release_channel_target_decision_record(record, output_path)
            written_payload = json.loads(output_path.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/decide_deployment_release_channel_target.py",
                    "--target-readiness",
                    "outputs/deployment_release_channel_target_readiness.json",
                    "--root",
                    str(root),
                    "--decision",
                    "choose",
                    "--target-family",
                    "serverless_function",
                    "--operator-id",
                    "target-operator",
                    "--operator-role",
                    "deployment_operator",
                    "--rationale",
                    "Serverless function selected for provider planning.",
                    "--decided-at",
                    "2026-06-15T05:20:00Z",
                    "--next-action",
                    "Plan provider-specific configuration in a future module.",
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            command_payload = json.loads(proc.stdout)
            file_payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual("selected", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("selected", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T05:20:00Z", file_payload["decided_at"])
        self.assertEqual("serverless_function", file_payload["decision"]["selected_target_family"])
        self.assertEqual(["Plan provider-specific configuration in a future module."], file_payload["next_actions"])


def _write_target_readiness_fixture(
    root: Path,
    *,
    status: str = "ready",
    failed_check: bool = False,
    selected_provider: str | None = None,
    provider_configuration: dict[str, object] | None = None,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    passed = status == "ready" and not failed_check and selected_provider is None and not provider_configuration
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_TARGET_READINESS_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T04:45:00Z",
        "readiness_name": "local-release-channel-target-readiness",
        "export_summary_path": "outputs/deployment_release_channel_export_summary.json",
        "export_summary": {
            "path": "outputs/deployment_release_channel_export_summary.json",
            "sha256": "0" * 64,
            "readable": True,
            "json_valid": True,
            "schema_version": 1,
            "status": "ready",
            "created_at": "2026-06-15T04:30:00Z",
            "summary_name": "local-release-channel-evidence-export-summary",
        },
        "target_selection_scope": "local_target_family_review_only",
        "selected_target_provider": selected_provider,
        "provider_configuration": provider_configuration or {},
        "candidate_target_families": ["serverless_function", "container_service", "managed_job_or_worker"],
        "handoff_checklist": ["Choose one deployment target family in a future module."],
        "package": {
            "package_name": "vyu-local-serverless-entrypoint",
            "runtime": "python3.11",
            "handler": "apps.serverless.handler.handler",
        },
        "operator": {"id": "release-operator", "role": "deployment_operator"},
        "evidence_hashes": {
            "evidence_index_sha256": "a" * 64,
            "publication_manifest_sha256": "b" * 64,
        },
        "evidence_counts": {
            "required_evidence_item_count": 8,
            "present_required_evidence_item_count": 8,
        },
        "export_review_checklist": ["Verify evidence index hash before target selection."],
        "export_blocking_reasons": [],
        "local_only_limits": ["no_artifact_transfer", "no_provider_configuration", "no_deployment"],
        "blocking_reasons": [] if passed else ["target_readiness_status_ready"],
        "summary": {
            "passed": 17 if passed else 16,
            "failed": 0 if passed else 1,
            "total": 17,
            "candidate_target_family_count": 3,
            "handoff_checklist_item_count": 1,
            "required_evidence_item_count": 8,
            "present_required_evidence_item_count": 8,
        },
        "checks": [
            {"name": "export_summary_status_ready", "passed": status == "ready", "detail": status},
            {"name": "evidence_index_hash_bound", "passed": not failed_check, "detail": "evidence_index.sha256"},
            {"name": "no_target_provider_selected", "passed": selected_provider is None, "detail": "selected_target_provider=None"},
            {"name": "no_provider_configuration_recorded", "passed": not provider_configuration, "detail": "provider_configuration={}"},
        ],
    }
    path = outputs / "deployment_release_channel_target_readiness.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_target_readiness.json")


if __name__ == "__main__":
    unittest.main()
