import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA,
    DeploymentTranscriptBundle,
    build_deployment_command_transcript,
    build_deployment_transcript_bundle,
    write_deployment_command_transcript,
    write_deployment_transcript_bundle,
)


class DeploymentTranscriptBundleTests(unittest.TestCase):
    def test_bundle_marks_ready_when_required_commands_have_passed_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            artifact = root / "outputs" / "deployment_release_package_checklist.json"
            artifact.parent.mkdir()
            artifact.write_text('{"status":"ready"}\n', encoding="utf-8")
            transcript_paths = _write_transcripts(root, artifact_path=Path("outputs/deployment_release_package_checklist.json"))

            bundle = build_deployment_transcript_bundle(
                manifest,
                transcript_paths=transcript_paths,
                root=root,
                created_at="2026-06-15T02:00:00Z",
            )

        payload = bundle.to_json()
        self.assertIsInstance(bundle, DeploymentTranscriptBundle)
        self.assertEqual(DEPLOYMENT_TRANSCRIPT_BUNDLE_SCHEMA, payload["schema_version"])
        self.assertEqual("ready", payload["status"])
        self.assertEqual(3, payload["summary"]["covered_command_count"])
        self.assertTrue(all(payload["command_coverage"].values()))
        self.assertEqual(1, payload["transcripts"][-1]["artifact_summary"]["hashed"])
        self.assertEqual("2026-06-15T02:00:00Z", payload["created_at"])

    def test_bundle_blocks_when_required_command_is_missing_or_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            transcript_paths = [
                _write_transcript(root, "validate.json", COMMANDS[0], exit_code=0),
                _write_transcript(root, "plan.json", COMMANDS[1], exit_code=1),
            ]

            bundle = build_deployment_transcript_bundle(
                manifest,
                transcript_paths=transcript_paths,
                root=root,
                created_at="2026-06-15T02:01:00Z",
            )

        payload = bundle.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(checks["all_transcripts_valid_and_passed"]["passed"])
        self.assertFalse(checks["required_command_coverage_complete"]["passed"])
        self.assertIn("scripts/plan_deployment_package.py", checks["required_command_coverage_complete"]["detail"])
        self.assertIn("scripts/check_deployment_release_package.py", checks["required_command_coverage_complete"]["detail"])

    def test_bundle_blocks_when_transcripts_are_out_of_required_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            transcript_paths = [
                _write_transcript(root, "plan.json", COMMANDS[1], exit_code=0),
                _write_transcript(root, "validate.json", COMMANDS[0], exit_code=0),
                _write_transcript(root, "release.json", COMMANDS[2], exit_code=0),
            ]

            bundle = build_deployment_transcript_bundle(
                manifest,
                transcript_paths=transcript_paths,
                root=root,
                created_at="2026-06-15T02:02:00Z",
            )

        payload = bundle.to_json()
        checks = {check["name"]: check for check in payload["checks"]}
        self.assertEqual("blocked", payload["status"])
        self.assertTrue(checks["required_command_coverage_complete"]["passed"])
        self.assertFalse(checks["required_command_sequence_order"]["passed"])

    def test_bundle_blocks_when_recorded_artifact_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            transcript_paths = _write_transcripts(
                root,
                artifact_path=Path("outputs/missing_release_checklist.json"),
            )

            bundle = build_deployment_transcript_bundle(
                manifest,
                transcript_paths=transcript_paths,
                root=root,
                created_at="2026-06-15T02:02:30Z",
            )

        payload = bundle.to_json()
        release_checks = {
            check["name"]: check
            for check in payload["transcripts"][-1]["checks"]
        }
        self.assertEqual("blocked", payload["status"])
        self.assertFalse(release_checks["recorded_artifacts_exist_and_hashed"]["passed"])
        self.assertEqual(1, payload["transcripts"][-1]["artifact_summary"]["missing"])


    def test_bundle_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = _write_manifest(root)
            artifact = root / "outputs" / "deployment_release_package_checklist.json"
            output = root / "outputs" / "deployment_transcript_bundle.json"
            artifact.parent.mkdir()
            artifact.write_text('{"status":"ready"}\n', encoding="utf-8")
            transcript_paths = _write_transcripts(root, artifact_path=Path("outputs/deployment_release_package_checklist.json"))

            bundle = build_deployment_transcript_bundle(
                manifest,
                transcript_paths=transcript_paths,
                root=root,
                created_at="2026-06-15T02:03:00Z",
            )
            write_deployment_transcript_bundle(bundle, output)
            written_payload = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/check_deployment_transcript_bundle.py",
                    "--manifest",
                    str(manifest),
                    "--transcript",
                    str(transcript_paths[0]),
                    "--transcript",
                    str(transcript_paths[1]),
                    "--transcript",
                    str(transcript_paths[2]),
                    "--root",
                    str(root),
                    "--created-at",
                    "2026-06-15T02:04:00Z",
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
        self.assertEqual("2026-06-15T02:04:00Z", file_payload["created_at"])


COMMANDS = (
    ("python", "scripts/validate_deployment_package.py", "--manifest", "deploy/serverless/package.manifest.json"),
    (
        "python",
        "scripts/plan_deployment_package.py",
        "--manifest",
        "deploy/serverless/package.manifest.json",
        "--output",
        "outputs/deployment_package_inventory.json",
    ),
    (
        "python",
        "scripts/check_deployment_release_package.py",
        "--manifest",
        "deploy/serverless/package.manifest.json",
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


def _write_manifest(root: Path) -> Path:
    manifest = root / "deploy" / "serverless" / "package.manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "package_name": "test-package",
                "deployment_target": "serverless-http",
                "runtime": "python3.11",
                "handler": "apps.serverless.handler.handler",
                "operator_config_env_var": "VYU_DEPLOYMENT_ENV_FILE",
                "operator_config_example": "config/deployment.local.example.env",
                "include_paths": ["src/vyu"],
                "exclude_paths": ["config/deployment.local.env"],
                "required_validation_commands": [list(command) for command in COMMANDS],
                "infrastructure_managed_elsewhere": True,
                "secret_values_in_manifest": False,
                "notes": ["test manifest"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def _write_transcripts(root: Path, *, artifact_path: Path) -> list[Path]:
    return [
        _write_transcript(root, "validate.json", COMMANDS[0], exit_code=0),
        _write_transcript(root, "plan.json", COMMANDS[1], exit_code=0),
        _write_transcript(root, "release.json", COMMANDS[2], exit_code=0, artifact_paths=[artifact_path]),
    ]


def _write_transcript(
    root: Path,
    name: str,
    command: tuple[str, ...],
    *,
    exit_code: int,
    artifact_paths: list[Path] | None = None,
) -> Path:
    path = root / "transcripts" / name
    transcript = build_deployment_command_transcript(
        command=command,
        purpose=" ".join(command[1:2]),
        exit_code=exit_code,
        started_at="2026-06-15T02:00:00Z",
        finished_at="2026-06-15T02:00:01Z",
        stdout_text='{"status":"ok"}\n',
        stderr_text="",
        artifact_paths=artifact_paths or [],
        root=root,
    )
    write_deployment_command_transcript(transcript, path)
    return Path("transcripts") / name


if __name__ == "__main__":
    unittest.main()
