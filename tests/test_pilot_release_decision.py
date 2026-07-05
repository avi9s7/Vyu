import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PilotReleaseDecisionTests(unittest.TestCase):
    def test_approves_pilot_release_when_bundle_and_required_attestations_are_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            output_path = root / "release_decision.json"
            bundle = _bundle(status="ready_for_pilot_review")
            bundle_path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            _write_jsonl(
                attestations_path,
                [
                    _attestation("privacy_owner", "approve", "2026-06-15T00:30:00Z", bundle_hash),
                    _attestation("security_owner", "approve", "2026-06-15T00:35:00Z", bundle_hash),
                ],
            )
            module = _release_module()

            payload = module.build_pilot_release_decision(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                output_path=output_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                required_approver_roles=["privacy_owner", "security_owner"],
                decided_at="2026-06-15T00:40:00Z",
            )
            written = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload, written)
        self.assertEqual("approved_for_pilot", payload["status"])
        self.assertEqual([], payload["blocking_reasons"])
        self.assertEqual(
            ["privacy_owner", "security_owner"],
            payload["attestations"]["approved_roles"],
        )
        self.assertEqual([], payload["attestations"]["missing_roles"])
        self.assertEqual(bundle_hash, payload["bundle"]["sha256"])

    def test_blocks_when_required_attestation_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            output_path = root / "release_decision.json"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            _write_jsonl(
                attestations_path,
                [_attestation("privacy_owner", "approve", "2026-06-15T00:30:00Z", bundle_hash)],
            )
            module = _release_module()

            payload = module.build_pilot_release_decision(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                output_path=output_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                required_approver_roles=["privacy_owner", "security_owner"],
                decided_at="2026-06-15T00:40:00Z",
            )

        self.assertEqual("blocked", payload["status"])
        self.assertIn("required_attestation_missing:security_owner", payload["blocking_reasons"])
        self.assertEqual(["security_owner"], payload["attestations"]["missing_roles"])

    def test_blocks_when_latest_required_attestation_requests_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            output_path = root / "release_decision.json"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            _write_jsonl(
                attestations_path,
                [
                    _attestation("privacy_owner", "approve", "2026-06-15T00:30:00Z", bundle_hash),
                    _attestation("security_owner", "approve", "2026-06-15T00:35:00Z", bundle_hash),
                    _attestation("security_owner", "request_changes", "2026-06-15T00:45:00Z", bundle_hash),
                ],
            )
            module = _release_module()

            payload = module.build_pilot_release_decision(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                output_path=output_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                required_approver_roles=["privacy_owner", "security_owner"],
                decided_at="2026-06-15T00:50:00Z",
            )

        self.assertEqual("blocked", payload["status"])
        self.assertIn("required_attestation_not_approved:security_owner", payload["blocking_reasons"])
        self.assertEqual("request_changes", payload["attestations"]["latest_by_role"]["security_owner"]["decision"])

    def test_rejects_bundle_scope_mismatch_before_writing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            output_path = root / "release_decision.json"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            _write_jsonl(attestations_path, [])
            module = _release_module()

            with self.assertRaises(PermissionError):
                module.build_pilot_release_decision(
                    bundle_path=bundle_path,
                    attestations_path=attestations_path,
                    output_path=output_path,
                    run_id="local-phase-output-run",
                    tenant_id="other_tenant",
                    workspace_id="local_workspace",
                    required_approver_roles=["privacy_owner"],
                    decided_at="2026-06-15T00:40:00Z",
                )

        self.assertFalse(output_path.exists())

    def test_release_decision_command_prints_and_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            output_path = root / "release_decision.json"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            _write_jsonl(
                attestations_path,
                [
                    _attestation("privacy_owner", "approve", "2026-06-15T00:30:00Z", bundle_hash),
                    _attestation("security_owner", "approve", "2026-06-15T00:35:00Z", bundle_hash),
                ],
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "build_pilot_release_decision.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--bundle",
                    str(bundle_path),
                    "--attestations",
                    str(attestations_path),
                    "--output",
                    str(output_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                    "--required-approver-role",
                    "privacy_owner",
                    "--required-approver-role",
                    "security_owner",
                    "--decided-at",
                    "2026-06-15T00:40:00Z",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            written = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else None

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, written)
        self.assertEqual("approved_for_pilot", payload["status"])


def _release_module():
    try:
        return importlib.import_module("scripts.build_pilot_release_decision")
    except ModuleNotFoundError as exc:
        raise AssertionError("pilot release decision script is not implemented") from exc


def _bundle(status: str) -> dict[str, object]:
    return {
        "status": status,
        "attention_reasons": [] if status == "ready_for_pilot_review" else ["readiness_missing"],
        "run_id": "local-phase-output-run",
        "tenant_id": "local_tenant",
        "workspace_id": "local_workspace",
        "attestations": {"bundle_sha256_values": []},
    }


def _attestation(
    approver_role: str,
    decision: str,
    attested_at: str,
    bundle_sha256: str,
) -> dict[str, str]:
    return {
        "approver_id": f"{approver_role}-user",
        "approver_role": approver_role,
        "attestation_id": f"attestation-local-phase-output-run-{approver_role}",
        "attested_at": attested_at,
        "bundle_sha256": bundle_sha256,
        "bundle_status": "ready_for_pilot_review",
        "comment": "Reviewed.",
        "decision": decision,
        "run_id": "local-phase-output-run",
        "tenant_id": "local_tenant",
        "workspace_id": "local_workspace",
    }


def _write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
