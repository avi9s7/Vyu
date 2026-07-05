import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA,
    DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA,
    DeploymentReleaseChannelProviderPreflight,
    build_deployment_release_channel_provider_preflight,
    write_deployment_release_channel_provider_preflight,
)


class DeploymentReleaseChannelProviderPreflightTests(unittest.TestCase):
    def test_provider_preflight_is_ready_for_selected_target_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_target_decision_fixture(root)
            preflight = build_deployment_release_channel_provider_preflight(
                target_decision_path=path,
                root=root,
                preflight_name="local-release-channel-provider-planning-preflight",
                created_at="2026-06-15T05:30:00Z",
            )

        payload = preflight.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertIsInstance(preflight, DeploymentReleaseChannelProviderPreflight)
        self.assertEqual(DEPLOYMENT_RELEASE_CHANNEL_PROVIDER_PREFLIGHT_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("provider_planning_preflight_only", payload["planning_scope"])
        self.assertEqual("serverless_function", payload["selected_target_family"])
        self.assertIsNone(payload["selected_target_provider"])
        self.assertEqual({}, payload["provider_configuration"])
        self.assertEqual("selected", payload["target_decision"]["status"])
        self.assertEqual("choose", payload["decision"]["value"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertEqual("target-operator", payload["target_operator"]["id"])
        self.assertEqual("a" * 64, payload["evidence_hashes"]["evidence_index_sha256"])
        self.assertGreaterEqual(payload["summary"]["planning_requirement_count"], 6)
        self.assertEqual([], payload["blocking_reasons"])
        self.assertTrue(checks["target_decision_status_selected"]["passed"])
        self.assertTrue(checks["target_decision_checks_passed"]["passed"])
        self.assertTrue(checks["decision_value_choose"]["passed"])
        self.assertTrue(checks["selected_target_family_in_candidates"]["passed"])
        self.assertTrue(checks["no_provider_configuration_recorded"]["passed"])

    def test_provider_preflight_blocks_for_deferred_target_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_target_decision_fixture(root, status="deferred", decision_value="defer", selected_family=None)
            preflight = build_deployment_release_channel_provider_preflight(
                target_decision_path=path,
                root=root,
                created_at="2026-06-15T05:35:00Z",
            )

        payload = preflight.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["target_decision_status_selected"]["passed"])
        self.assertFalse(checks["decision_value_choose"]["passed"])
        self.assertFalse(checks["selected_target_family_present"]["passed"])

    def test_provider_preflight_blocks_when_provider_configuration_is_already_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_target_decision_fixture(
                root,
                selected_provider="example-cloud",
                provider_configuration={"region": "example-region"},
            )
            preflight = build_deployment_release_channel_provider_preflight(
                target_decision_path=path,
                root=root,
                created_at="2026-06-15T05:40:00Z",
            )

        payload = preflight.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["no_target_provider_selected"]["passed"])
        self.assertFalse(checks["no_provider_configuration_recorded"]["passed"])

    def test_writer_and_command_write_provider_preflight_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _write_target_decision_fixture(root)
            output = root / "outputs" / "deployment_release_channel_provider_preflight.json"
            preflight = build_deployment_release_channel_provider_preflight(
                target_decision_path=path,
                root=root,
                created_at="2026-06-15T05:45:00Z",
            )
            write_deployment_release_channel_provider_preflight(preflight, output)
            written = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_channel_provider_preflight.py",
                    "--target-decision",
                    "outputs/deployment_release_channel_target_decision.json",
                    "--root",
                    str(root),
                    "--preflight-name",
                    "local-release-channel-provider-planning-preflight",
                    "--created-at",
                    "2026-06-15T05:50:00Z",
                    "--planning-requirement",
                    "Identity boundary reviewed before provider planning.",
                    "--next-action",
                    "Draft provider-specific plan in a future module.",
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

        self.assertEqual("ready", written["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("ready", command_payload["status"])
        self.assertEqual(["Identity boundary reviewed before provider planning."], file_payload["planning_requirements"])
        self.assertEqual(["Draft provider-specific plan in a future module."], file_payload["next_actions"])


def _write_target_decision_fixture(
    root: Path,
    *,
    status: str = "selected",
    decision_value: str = "choose",
    selected_family: str | None = "serverless_function",
    selected_provider: str | None = None,
    provider_configuration: dict[str, object] | None = None,
) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    provider_configuration = provider_configuration or {}
    passed = status == "selected" and decision_value == "choose" and selected_family is not None and selected_provider is None and not provider_configuration
    payload = {
        "schema_version": DEPLOYMENT_RELEASE_CHANNEL_TARGET_DECISION_SCHEMA,
        "status": status,
        "decision_id": "deployment-release-channel-target-fixture",
        "decided_at": "2026-06-15T05:00:00Z",
        "target_readiness_path": "outputs/deployment_release_channel_target_readiness.json",
        "target_readiness": {"sha256": "0" * 64, "status": "ready"},
        "package": {"package_name": "vyu-local-serverless-entrypoint", "runtime": "python3.11", "handler": "apps.serverless.handler.handler"},
        "inherited_operator": {"id": "release-operator", "role": "deployment_operator"},
        "operator": {"id": "target-operator", "role": "deployment_operator"},
        "decision": {"value": decision_value, "selected_target_family": selected_family, "rationale": "Fixture rationale."},
        "target_selection_scope": "local_target_family_review_only",
        "candidate_target_families": ["serverless_function", "container_service", "managed_job_or_worker"],
        "selected_target_provider": selected_provider,
        "provider_configuration": provider_configuration,
        "export_summary": {"sha256": "1" * 64, "status": "ready"},
        "evidence_hashes": {"evidence_index_sha256": "a" * 64},
        "evidence_counts": {"required_evidence_item_count": 8, "present_required_evidence_item_count": 8},
        "local_only_limits": ["no_artifact_transfer", "no_provider_configuration", "no_deployment"],
        "handoff_checklist": ["Choose one deployment target family in a future module."],
        "next_actions": ["Use this decision as a future planning input."],
        "blocking_reasons": [] if passed else ["target_decision_status_selected"],
        "summary": {"passed": 21 if passed else 20, "failed": 0 if passed else 1, "total": 21},
        "checks": [
            {"name": "target_readiness_status_ready", "passed": True, "detail": "ready"},
            {"name": "choose_requires_candidate_target_family", "passed": selected_family in ["serverless_function", "container_service", "managed_job_or_worker"], "detail": str(selected_family)},
            {"name": "no_target_provider_selected", "passed": selected_provider is None, "detail": "selected_target_provider=None"},
            {"name": "no_provider_configuration_recorded", "passed": not provider_configuration, "detail": "provider_configuration={}"},
        ],
    }
    path = outputs / "deployment_release_channel_target_decision.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Path("outputs/deployment_release_channel_target_decision.json")


if __name__ == "__main__":
    unittest.main()
