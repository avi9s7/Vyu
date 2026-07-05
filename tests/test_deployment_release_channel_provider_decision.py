import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISION_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA,
    DeploymentReleaseChannelProviderDecisionRecord,
    build_deployment_release_channel_provider_decision_record,
    write_deployment_release_channel_provider_decision_record,
)


class DeploymentReleaseChannelProviderDecisionTests(unittest.TestCase):
    def test_provider_decision_approves_ready_preflight_for_proceed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_provider_preflight_fixture(root)
            record = build_deployment_release_channel_provider_decision_record(
                provider_preflight_path=path,
                root=root,
                decision="proceed",
                provider_planning_track="serverless_provider_requirements_review",
                operator_id="provider-operator",
                operator_role="deployment_operator",
                rationale="Provider planning can proceed from the local preflight.",
                decided_at="2026-06-15T06:00:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertIsInstance(record, DeploymentReleaseChannelProviderDecisionRecord)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_DECISION_SCHEMA, payload["schema_version"])
        self.assertEqual("approved", payload["status"])
        self.assertEqual("ready", payload["provider_preflight"]["status"])
        self.assertEqual("proceed", payload["decision"]["value"])
        self.assertEqual("serverless_provider_requirements_review", payload["decision"]["provider_planning_track"])
        self.assertEqual("local_provider_planning_decision_only", payload["planning_decision_scope"])
        self.assertEqual("serverless_function", payload["selected_target_family"])
        self.assertIsNone(payload["selected_target_provider"])
        self.assertEqual({}, payload["provider_configuration"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertTrue(checks["provider_preflight_status_ready"]["passed"])
        self.assertTrue(checks["provider_preflight_checks_passed"]["passed"])
        self.assertTrue(checks["proceed_requires_provider_planning_track"]["passed"])
        self.assertTrue(checks["no_target_provider_selected"]["passed"])
        self.assertEqual([], payload["blocking_reasons"])

    def test_provider_decision_blocks_when_preflight_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_provider_preflight_fixture(
                root,
                status="blocked",
                preflight_checks_passed=False,
                blocking_reasons=["selected_target_family_present"],
            )
            record = build_deployment_release_channel_provider_decision_record(
                provider_preflight_path=path,
                root=root,
                decision="proceed",
                provider_planning_track="serverless_provider_requirements_review",
                operator_id="provider-operator",
                operator_role="deployment_operator",
                rationale="Attempted proceed against blocked preflight.",
                decided_at="2026-06-15T06:05:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["provider_preflight_status_ready"]["passed"])
        self.assertFalse(checks["provider_preflight_checks_passed"]["passed"])
        self.assertFalse(checks["provider_preflight_blocking_reasons_absent"]["passed"])
        self.assertIn("provider_preflight_status_ready", payload["blocking_reasons"])

    def test_provider_decision_blocks_when_provider_details_are_already_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_provider_preflight_fixture(
                root,
                selected_provider="example-cloud",
                provider_configuration={"region": "example-region"},
            )
            record = build_deployment_release_channel_provider_decision_record(
                provider_preflight_path=path,
                root=root,
                decision="proceed",
                provider_planning_track="serverless_provider_requirements_review",
                operator_id="provider-operator",
                operator_role="deployment_operator",
                rationale="Provider details should block this local boundary.",
                decided_at="2026-06-15T06:10:00Z",
            )

        payload = record.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["no_target_provider_selected"]["passed"])
        self.assertFalse(checks["no_provider_configuration_recorded"]["passed"])

    def test_writer_and_command_write_provider_decision_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_provider_preflight_fixture(root)
            output = root / "outputs" / "deployment_release_channel_provider_decision.json"
            record = build_deployment_release_channel_provider_decision_record(
                provider_preflight_path=path,
                root=root,
                decision="proceed",
                provider_planning_track="serverless_provider_requirements_review",
                operator_id="provider-operator",
                operator_role="deployment_operator",
                rationale="Provider planning can proceed from the local preflight.",
                decided_at="2026-06-15T06:15:00Z",
            )
            write_deployment_release_channel_provider_decision_record(record, output)
            written = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/decide_deployment_release_channel_provider.py",
                    "--provider-preflight",
                    "outputs/deployment_release_channel_provider_preflight.json",
                    "--root",
                    str(root),
                    "--decision",
                    "proceed",
                    "--planning-track",
                    "serverless_provider_requirements_review",
                    "--operator-id",
                    "provider-operator",
                    "--operator-role",
                    "deployment_operator",
                    "--rationale",
                    "Provider planning can proceed from the local preflight.",
                    "--decided-at",
                    "2026-06-15T06:20:00Z",
                    "--next-action",
                    "Draft a provider-plan checklist in a future module.",
                    "--output",
                    str(output),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )
            command_payload = json.loads(proc.stdout)
            file_payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("approved", written["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("approved", command_payload["status"])
        self.assertEqual(["Draft a provider-plan checklist in a future module."], file_payload["next_actions"])


def _write_provider_preflight_fixture(
    root: Path,
    *,
    status: str = "ready",
    selected_family: str | None = "serverless_function",
    selected_provider: str | None = None,
    provider_configuration: dict[str, object] | None = None,
    preflight_checks_passed: bool = True,
    blocking_reasons: list[str] | None = None,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    provider_configuration = provider_configuration or {}
    blocking_reasons = blocking_reasons if blocking_reasons is not None else []
    checks = [
        {"name": "target_decision_status_selected", "passed": True, "detail": "selected"},
        {"name": "decision_value_choose", "passed": True, "detail": "choose"},
        {"name": "selected_target_family_present", "passed": selected_family is not None, "detail": str(selected_family)},
        {"name": "selected_target_family_in_candidates", "passed": selected_family in ["serverless_function", "container_service", "managed_job_or_worker"], "detail": str(selected_family)},
        {"name": "no_target_provider_selected", "passed": selected_provider is None, "detail": "selected_target_provider=None"},
        {"name": "no_provider_configuration_recorded", "passed": not provider_configuration, "detail": "provider_configuration={}"},
    ]
    if not preflight_checks_passed:
        checks.append({"name": "fixture_failed_preflight_check", "passed": False, "detail": "forced"})
    failed = sum(1 for check in checks if not check["passed"])
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA,
        "status": status,
        "created_at": "2026-06-15T05:30:00Z",
        "preflight_name": "local-release-channel-provider-planning-preflight",
        "target_decision_path": "outputs/deployment_release_channel_target_decision.json",
        "target_decision": {"sha256": "0" * 64, "status": "selected", "decision_id": "deployment-release-channel-target-fixture"},
        "planning_scope": "provider_planning_preflight_only",
        "selected_target_family": selected_family,
        "selected_target_provider": selected_provider,
        "provider_configuration": provider_configuration,
        "package": {"package_name": "vyu-local-serverless-entrypoint", "runtime": "python3.11", "handler": "apps.serverless.handler.handler"},
        "target_operator": {"id": "target-operator", "role": "deployment_operator"},
        "inherited_operator": {"id": "release-operator", "role": "deployment_operator"},
        "decision": {"value": "choose", "selected_target_family": selected_family, "rationale": "Fixture target decision."},
        "target_selection_scope": "local_target_family_review_only",
        "candidate_target_families": ["serverless_function", "container_service", "managed_job_or_worker"],
        "export_summary": {"sha256": "1" * 64, "status": "ready"},
        "evidence_hashes": {"evidence_index_sha256": "a" * 64},
        "evidence_counts": {"required_evidence_item_count": 8, "present_required_evidence_item_count": 8},
        "local_only_limits": ["no_artifact_transfer", "no_provider_configuration", "no_deployment"],
        "handoff_checklist": ["Review provider planning in a future module."],
        "planning_requirements": ["Provider planning must remain credential-free at this boundary."],
        "next_actions": ["Use this preflight as a decision input."],
        "blocking_reasons": blocking_reasons,
        "summary": {"passed": len(checks) - failed, "failed": failed, "total": len(checks)},
        "checks": checks,
    }
    path = outputs / "deployment_release_channel_provider_preflight.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_provider_preflight.json")


if __name__ == "__main__":
    unittest.main()
