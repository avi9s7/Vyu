import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.phase0_intake import (
    collect_inventory,
    find_dependency_files,
    license_sha256,
    load_manifest,
    write_lockfile,
)


class Phase0IntakeTests(unittest.TestCase):
    def test_load_manifest_requires_expected_upstreams(self):
        manifest = load_manifest(Path("upstreams.yaml"))

        self.assertEqual(
            {
                "google_biocompass",
                "google_pubmed_mcp",
                "medrag",
                "zaoqu_pubmedrag",
                "rag_gym",
                "pubmedrag_simcse",
            },
            set(manifest["upstreams"]),
        )
        for name, upstream in manifest["upstreams"].items():
            with self.subTest(name=name):
                self.assertTrue(upstream["repo_url"].startswith("https://github.com/"))
                self.assertIn("usage", upstream)
                self.assertIn("license", upstream)
                self.assertIn("reuse_policy", upstream)

    def test_license_hash_reads_license_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            license_file = root / "LICENSE"
            license_file.write_bytes(b"Apache License\n")

            digest = license_sha256(root)

        self.assertEqual(hashlib.sha256(b"Apache License\n").hexdigest(), digest)

    def test_find_dependency_files_detects_common_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            nested = root / "app"
            nested.mkdir()
            (nested / "requirements.txt").write_text("httpx\n", encoding="utf-8")

            files = find_dependency_files(root)

        self.assertEqual(["app/requirements.txt", "pyproject.toml"], files)

    def test_write_lockfile_serializes_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "upstreams" / "demo"
            upstream.mkdir(parents=True)
            (upstream / "LICENSE").write_bytes(b"Demo license\n")
            (upstream / "requirements.txt").write_text("pytest\n", encoding="utf-8")

            inventory = collect_inventory(
                {
                    "upstreams": {
                        "demo": {
                            "repo": "example/demo",
                            "repo_url": "https://github.com/example/demo",
                            "local_path": "upstreams/demo",
                            "license": "Apache-2.0",
                            "usage": "selected_components",
                            "reuse_policy": "adapt_with_notice",
                        }
                    }
                },
                root,
            )
            output = root / "UPSTREAM_LOCK.json"
            write_lockfile(inventory, output)

            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("demo", saved["upstreams"][0]["name"])
        self.assertEqual(["requirements.txt"], saved["upstreams"][0]["dependency_files"])
        self.assertEqual(
            hashlib.sha256(b"Demo license\n").hexdigest(),
            saved["upstreams"][0]["license_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
