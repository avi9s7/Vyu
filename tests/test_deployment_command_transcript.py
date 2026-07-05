import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.vyu.deployment import (
    DEFAULT_OUTPUT_EXCERPT_LIMIT,
    DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA,
    DeploymentCommandTranscript,
    DeploymentCommandTranscriptError,
    build_deployment_command_transcript,
    command_from_json,
    write_deployment_command_transcript,
)


class DeploymentCommandTranscriptTests(unittest.TestCase):
    def test_transcript_records_success_outputs_and_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "outputs" / "deployment_package_evidence.json"
            artifact.parent.mkdir()
            artifact.write_text('{"status":"complete"}\n', encoding="utf-8")

            transcript = build_deployment_command_transcript(
                command=["python", "scripts/write_deployment_package_evidence.py"],
                purpose="write deployment package evidence",
                exit_code=0,
                started_at="2026-06-15T01:10:00Z",
                finished_at="2026-06-15T01:10:02Z",
                stdout_text='{"status":"complete"}\n',
                stderr_text="",
                artifact_paths=[Path("outputs/deployment_package_evidence.json")],
                root=root,
            )

        payload = transcript.to_json()
        artifact_payload = payload["artifacts"][0]
        self.assertIsInstance(transcript, DeploymentCommandTranscript)
        self.assertEqual(DEPLOYMENT_COMMAND_TRANSCRIPT_SCHEMA, payload["schema_version"])
        self.assertEqual("passed", payload["status"])
        self.assertEqual(["python", "scripts/write_deployment_package_evidence.py"], payload["command"])
        self.assertEqual("write deployment package evidence", payload["purpose"])
        self.assertEqual(0, payload["exit_code"])
        self.assertEqual("2026-06-15T01:10:00Z", payload["started_at"])
        self.assertEqual("2026-06-15T01:10:02Z", payload["finished_at"])
        self.assertEqual(hashlib.sha256(b'{"status":"complete"}\n').hexdigest(), payload["outputs"]["stdout"]["sha256"])
        self.assertFalse(payload["outputs"]["stdout"]["truncated"])
        self.assertEqual("", payload["outputs"]["stderr"]["excerpt"])
        self.assertTrue(artifact_payload["exists"])
        self.assertRegex(artifact_payload["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(1, payload["summary"]["existing_artifact_count"])

    def test_transcript_records_failure_and_truncates_output_excerpt(self):
        long_error = "x" * (DEFAULT_OUTPUT_EXCERPT_LIMIT + 10)
        transcript = build_deployment_command_transcript(
            command=["python", "scripts/check_deployment_release_package.py"],
            purpose="check release package",
            exit_code=1,
            started_at="2026-06-15T01:11:00Z",
            finished_at="2026-06-15T01:11:01Z",
            stderr_text=long_error,
            artifact_paths=[Path("outputs/missing.json")],
            root=Path("."),
        )

        payload = transcript.to_json()
        self.assertEqual("failed", payload["status"])
        self.assertEqual(1, payload["exit_code"])
        self.assertTrue(payload["outputs"]["stderr"]["truncated"])
        self.assertEqual(DEFAULT_OUTPUT_EXCERPT_LIMIT, len(payload["outputs"]["stderr"]["excerpt"]))
        self.assertFalse(payload["artifacts"][0]["exists"])
        self.assertEqual(1, payload["summary"]["missing_artifact_count"])

    def test_transcript_rejects_invalid_command_metadata(self):
        with self.assertRaisesRegex(DeploymentCommandTranscriptError, "command cannot be empty"):
            build_deployment_command_transcript(
                command=[],
                purpose="bad",
                exit_code=0,
                started_at="2026-06-15T01:12:00Z",
                finished_at="2026-06-15T01:12:01Z",
            )
        with self.assertRaisesRegex(DeploymentCommandTranscriptError, "command_json must be a JSON array"):
            command_from_json('"python"')
        with self.assertRaisesRegex(DeploymentCommandTranscriptError, "only string parts"):
            command_from_json('["python", 3]')

    def test_transcript_writer_and_command_write_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout_file = root / "stdout.txt"
            stderr_file = root / "stderr.txt"
            artifact = root / "outputs" / "deployment_release_package_checklist.json"
            output = root / "outputs" / "deployment_command_transcript.json"
            artifact.parent.mkdir()
            stdout_file.write_text('{"status":"ready"}\n', encoding="utf-8")
            stderr_file.write_text("", encoding="utf-8")
            artifact.write_text('{"status":"ready"}\n', encoding="utf-8")

            transcript = build_deployment_command_transcript(
                command=["python", "scripts/check_deployment_release_package.py"],
                purpose="check release package",
                exit_code=0,
                started_at="2026-06-15T01:13:00Z",
                finished_at="2026-06-15T01:13:03Z",
                stdout_text=stdout_file.read_text(encoding="utf-8"),
                artifact_paths=[Path("outputs/deployment_release_package_checklist.json")],
                root=root,
            )
            write_deployment_command_transcript(transcript, output)
            written_payload = json.loads(output.read_text(encoding="utf-8"))

            proc = subprocess.run(
                [
                    sys.executable,
                    "scripts/write_deployment_command_transcript.py",
                    "--command-json",
                    '["python", "scripts/check_deployment_release_package.py"]',
                    "--purpose",
                    "check release package",
                    "--exit-code",
                    "0",
                    "--started-at",
                    "2026-06-15T01:14:00Z",
                    "--finished-at",
                    "2026-06-15T01:14:03Z",
                    "--stdout-file",
                    str(stdout_file),
                    "--stderr-file",
                    str(stderr_file),
                    "--artifact",
                    "outputs/deployment_release_package_checklist.json",
                    "--root",
                    str(root),
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

        self.assertEqual("passed", written_payload["status"])
        self.assertEqual(proc.stderr, "")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("passed", command_payload["status"])
        self.assertEqual(command_payload, file_payload)
        self.assertEqual("2026-06-15T01:14:00Z", file_payload["started_at"])


if __name__ == "__main__":
    unittest.main()
