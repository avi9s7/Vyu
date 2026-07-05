import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ComplianceAttestationTests(unittest.TestCase):
    def test_records_approved_attestation_against_bundle_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
            module = _attestation_module()

            record = module.record_compliance_attestation(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                approver_id="privacy-owner",
                approver_role="privacy_owner",
                decision="approve",
                comment="Privacy evidence reviewed.",
                attested_at="2026-06-15T00:30:00Z",
            )
            records = [
                json.loads(line)
                for line in attestations_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(record, records[0])
        self.assertEqual("local-phase-output-run", record["run_id"])
        self.assertEqual("privacy_owner", record["approver_role"])
        self.assertEqual("approve", record["decision"])
        self.assertEqual("ready_for_pilot_review", record["bundle_status"])
        self.assertEqual(bundle_hash, record["bundle_sha256"])
        self.assertEqual("attestation-local-phase-output-run-privacy-owner-privacy_owner", record["attestation_id"])

    def test_appends_multiple_attestations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            module = _attestation_module()

            first = module.record_compliance_attestation(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                approver_id="privacy-owner",
                approver_role="privacy_owner",
                decision="approve",
                comment="Privacy evidence reviewed.",
                attested_at="2026-06-15T00:30:00Z",
            )
            second = module.record_compliance_attestation(
                bundle_path=bundle_path,
                attestations_path=attestations_path,
                run_id="local-phase-output-run",
                tenant_id="local_tenant",
                workspace_id="local_workspace",
                approver_id="security-owner",
                approver_role="security_owner",
                decision="request_changes",
                comment="Need deployed IAM evidence before pilot.",
                attested_at="2026-06-15T00:35:00Z",
            )
            records = [
                json.loads(line)
                for line in attestations_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual([first, second], records)
        self.assertEqual(["approve", "request_changes"], [record["decision"] for record in records])

    def test_approve_requires_ready_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            bundle_path.write_text(
                json.dumps(_bundle(status="attention"), sort_keys=True),
                encoding="utf-8",
            )
            module = _attestation_module()

            with self.assertRaises(ValueError) as context:
                module.record_compliance_attestation(
                    bundle_path=bundle_path,
                    attestations_path=attestations_path,
                    run_id="local-phase-output-run",
                    tenant_id="local_tenant",
                    workspace_id="local_workspace",
                    approver_id="privacy-owner",
                    approver_role="privacy_owner",
                    decision="approve",
                    comment="Privacy evidence reviewed.",
                    attested_at="2026-06-15T00:30:00Z",
                )

        self.assertIn("ready_for_pilot_review", str(context.exception))
        self.assertFalse(attestations_path.exists())

    def test_rejects_bundle_scope_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            module = _attestation_module()

            with self.assertRaises(PermissionError):
                module.record_compliance_attestation(
                    bundle_path=bundle_path,
                    attestations_path=attestations_path,
                    run_id="local-phase-output-run",
                    tenant_id="other_tenant",
                    workspace_id="local_workspace",
                    approver_id="privacy-owner",
                    approver_role="privacy_owner",
                    decision="approve",
                    comment="Privacy evidence reviewed.",
                    attested_at="2026-06-15T00:30:00Z",
                )

        self.assertFalse(attestations_path.exists())

    def test_attestation_command_prints_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle_path = root / "bundle.json"
            attestations_path = root / "attestations.jsonl"
            bundle_path.write_text(
                json.dumps(_bundle(status="ready_for_pilot_review"), sort_keys=True),
                encoding="utf-8",
            )
            script_path = (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "record_compliance_attestation.py"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(script_path),
                    "--bundle",
                    str(bundle_path),
                    "--attestations",
                    str(attestations_path),
                    "--run-id",
                    "local-phase-output-run",
                    "--tenant-id",
                    "local_tenant",
                    "--workspace-id",
                    "local_workspace",
                    "--approver-id",
                    "privacy-owner",
                    "--approver-role",
                    "privacy_owner",
                    "--decision",
                    "approve",
                    "--comment",
                    "Privacy evidence reviewed.",
                    "--attested-at",
                    "2026-06-15T00:30:00Z",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("approve", payload["decision"])
        self.assertEqual("privacy_owner", payload["approver_role"])


def _attestation_module():
    try:
        return importlib.import_module("scripts.record_compliance_attestation")
    except ModuleNotFoundError as exc:
        raise AssertionError("compliance attestation script is not implemented") from exc


def _bundle(status: str) -> dict[str, object]:
    return {
        "status": status,
        "run_id": "local-phase-output-run",
        "tenant_id": "local_tenant",
        "workspace_id": "local_workspace",
        "attention_reasons": [] if status == "ready_for_pilot_review" else ["review_pending"],
    }


if __name__ == "__main__":
    unittest.main()
