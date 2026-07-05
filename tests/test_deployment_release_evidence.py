import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
    DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA,
    DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA,
    DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA,
    DeploymentReleaseEvidenceSummary,
    build_deployment_release_evidence_summary,
    write_deployment_release_evidence_summary,
)


class DeploymentReleaseEvidenceSummaryTests(unittest.TestCase):
    def test_summary_marks_ready_when_evidence_checklist_and_bundle_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_evidence, release_checklist, transcript_bundle = _write_ready_inputs(root)

            summary = build_deployment_release_evidence_summary(
                package_evidence_path=package_evidence,
                release_checklist_path=release_checklist,
                transcript_bundle_path=transcript_bundle,
                created_at="2026-06-15T02:30:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertIsInstance(summary, DeploymentReleaseEvidenceSummary)
        self.assertEqual(DEPLOYMENT_RELEASE_EVIDENCE_SUMMARY_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual("2026-06-15T02:30:00Z", payload["created_at"])
        self.assertEqual("vyu-local-serverless-entrypoint", payload["package"]["package_name"])
        self.assertRegex(payload["artifact_hashes"]["package_evidence_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["artifact_hashes"]["release_checklist_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["artifact_hashes"]["transcript_bundle_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["command_summary"]["commands_match"])
        self.assertEqual(3, payload["command_summary"]["covered_command_count"])
        self.assertTrue(checks["manifest_paths_match"]["passed"])
        self.assertTrue(checks["package_artifact_hashes_match_checklist"]["passed"])
        self.assertTrue(checks["checklist_evidence_hash_matches_input"]["passed"])
        self.assertTrue(checks["required_commands_match_transcript_bundle"]["passed"])
        self.assertTrue(checks["transcript_bundle_coverage_complete"]["passed"])

    def test_summary_blocks_when_release_checklist_references_stale_package_evidence_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_evidence, release_checklist, transcript_bundle = _write_ready_inputs(
                root,
                stale_checklist_evidence_hash=True,
            )

            summary = build_deployment_release_evidence_summary(
                package_evidence_path=package_evidence,
                release_checklist_path=release_checklist,
                transcript_bundle_path=transcript_bundle,
                created_at="2026-06-15T02:31:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertEqual("blocked", payload["status"])
        self.assertTrue(checks["release_checklist_ready"]["passed"])
        self.assertFalse(checks["checklist_evidence_hash_matches_input"]["passed"])
        self.assertFalse(all(check["passed"] for check in payload["checks"]))

    def test_summary_blocks_when_manifest_or_required_commands_do_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_evidence, release_checklist, transcript_bundle = _write_ready_inputs(
                root,
                bundle_manifest_path="deploy/other/package.manifest.json",
                bundle_command_override=[COMMANDS[0], COMMANDS[2]],
            )

            summary = build_deployment_release_evidence_summary(
                package_evidence_path=package_evidence,
                release_checklist_path=release_checklist,
                transcript_bundle_path=transcript_bundle,
                created_at="2026-06-15T02:32:00Z",
            )

        payload = summary.to_json()
        checks = {check["name"]: check for check in payload["checks"]}

        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["manifest_paths_match"]["passed"])
        self.assertFalse(checks["required_commands_match_transcript_bundle"]["passed"])
        self.assertFalse(payload["command_summary"]["commands_match"])

    def test_summary_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_evidence, release_checklist, transcript_bundle = _write_ready_inputs(root)
            output = root / "deployment_release_evidence_summary.json"

            summary = build_deployment_release_evidence_summary(
                package_evidence_path=package_evidence,
                release_checklist_path=release_checklist,
                transcript_bundle_path=transcript_bundle,
                created_at="2026-06-15T02:33:00Z",
            )
            write_deployment_release_evidence_summary(summary, output)
            written_payload = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/build_deployment_release_evidence.py",
                    "--package-evidence",
                    str(package_evidence),
                    "--release-checklist",
                    str(release_checklist),
                    "--transcript-bundle",
                    str(transcript_bundle),
                    "--created-at",
                    "2026-06-15T02:34:00Z",
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

        self.assertEqual("ready", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("ready", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T02:34:00Z", file_payload["created_at"])


MANIFEST_PATH = "deploy/serverless/package.manifest.json"
PACKAGE = {
    "package_name": "vyu-local-serverless-entrypoint",
    "deployment_target": "serverless-http",
    "runtime": "python3.11",
    "handler": "apps.serverless.handler.handler",
}
COMMANDS = (
    ("python", "scripts/validate_deployment_package.py", "--manifest", MANIFEST_PATH),
    (
        "python",
        "scripts/plan_deployment_package.py",
        "--manifest",
        MANIFEST_PATH,
        "--output",
        "outputs/deployment_package_inventory.json",
    ),
    (
        "python",
        "scripts/check_deployment_release_package.py",
        "--manifest",
        MANIFEST_PATH,
        "--archive",
        "outputs/vyu_deployment_package.zip",
        "--inventory",
        "outputs/deployment_package_inventory.json",
        "--evidence",
        "outputs/deployment_package_evidence.json",
        "--output",
        "outputs/deployment_release_package_checklist.json",
    ),
)
ARCHIVE_SHA256 = "a" * 64
INVENTORY_SHA256 = "b" * 64


def _write_ready_inputs(
    root: Path,
    *,
    stale_checklist_evidence_hash: bool = False,
    bundle_manifest_path: str = MANIFEST_PATH,
    bundle_command_override: list[tuple[str, ...]] | None = None,
) -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    package_evidence = root / "deployment_package_evidence.json"
    release_checklist = root / "deployment_release_package_checklist.json"
    transcript_bundle = root / "deployment_transcript_bundle.json"

    evidence_payload = {
        "schema_version": DEPLOYMENT_PACKAGE_EVIDENCE_SCHEMA,
        "status": "complete",
        "created_at": "2026-06-15T02:20:00Z",
        "manifest_path": MANIFEST_PATH,
        "archive_path": "outputs/vyu_deployment_package.zip",
        "inventory_path": "outputs/deployment_package_inventory.json",
        "package": PACKAGE,
        "artifact_hashes": {
            "archive_sha256": ARCHIVE_SHA256,
            "inventory_sha256": INVENTORY_SHA256,
        },
        "manifest_validation": {"status": "pass"},
        "archive_verification": {"status": "pass"},
        "required_validation_commands": [list(command) for command in COMMANDS],
        "checks": [{"name": "inventory_matches_plan", "passed": True, "detail": "ok"}],
    }
    _write_json(package_evidence, evidence_payload)
    evidence_sha256 = _sha256(package_evidence)

    checklist_payload = {
        "schema_version": DEPLOYMENT_RELEASE_PACKAGE_CHECKLIST_SCHEMA,
        "status": "ready",
        "created_at": "2026-06-15T02:21:00Z",
        "manifest_path": MANIFEST_PATH,
        "archive_path": "outputs/vyu_deployment_package.zip",
        "inventory_path": "outputs/deployment_package_inventory.json",
        "evidence_path": "outputs/deployment_package_evidence.json",
        "package": PACKAGE,
        "artifact_hashes": {
            "archive_sha256": ARCHIVE_SHA256,
            "inventory_sha256": INVENTORY_SHA256,
            "evidence_sha256": "0" * 64 if stale_checklist_evidence_hash else evidence_sha256,
        },
        "required_command_coverage": {" ".join(command): True for command in COMMANDS},
        "summary": {"passed": 8, "failed": 0, "total": 8},
        "checks": [{"name": "evidence_hashes_match_artifacts", "passed": True, "detail": "ok"}],
    }
    _write_json(release_checklist, checklist_payload)

    bundle_commands = tuple(bundle_command_override) if bundle_command_override is not None else COMMANDS
    bundle_payload = {
        "schema_version": DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA,
        "status": "ready",
        "created_at": "2026-06-15T02:22:00Z",
        "manifest_path": bundle_manifest_path,
        "transcript_paths": [f"outputs/transcripts/{idx}.json" for idx, _ in enumerate(bundle_commands)],
        "required_commands": [
            {
                "index": idx,
                "command": list(command),
                "covered": True,
                "transcript_path": f"outputs/transcripts/{idx}.json",
            }
            for idx, command in enumerate(bundle_commands)
        ],
        "command_coverage": {" ".join(command): True for command in bundle_commands},
        "summary": {
            "required_command_count": len(bundle_commands),
            "covered_command_count": len(bundle_commands),
            "transcript_count": len(bundle_commands),
        },
        "checks": [{"name": "required_command_coverage_complete", "passed": True, "detail": "ok"}],
    }
    _write_json(transcript_bundle, bundle_payload)

    return package_evidence, release_checklist, transcript_bundle


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
