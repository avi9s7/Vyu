from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEPENDENCY_MANIFEST_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "environment.yml",
}

LICENSE_NAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "COPYING",
    "COPYING.md",
)


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        manifest = yaml.safe_load(text)
    except ModuleNotFoundError:
        manifest = _load_simple_yaml(text)

    if not isinstance(manifest, dict) or not isinstance(manifest.get("upstreams"), dict):
        raise ValueError("Manifest must contain an 'upstreams' mapping.")

    for name, upstream in manifest["upstreams"].items():
        if not isinstance(upstream, dict):
            raise ValueError(f"Upstream {name!r} must be a mapping.")
        missing = {
            "repo",
            "repo_url",
            "local_path",
            "license",
            "usage",
            "reuse_policy",
        } - set(upstream)
        if missing:
            raise ValueError(f"Upstream {name!r} is missing: {', '.join(sorted(missing))}")

    return manifest


def _load_simple_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    current_item: dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, separator, value = line.strip().partition(":")
        if not separator:
            raise ValueError(f"Unsupported YAML line: {raw_line!r}")

        value = value.strip().strip('"')
        if indent == 0:
            data[key] = {}
            current_section = data[key]
            current_item = None
        elif indent == 2 and current_section is not None:
            current_section[key] = {}
            current_item = current_section[key]
        elif indent == 4 and current_item is not None:
            current_item[key] = value
        else:
            raise ValueError(f"Unsupported YAML indentation: {raw_line!r}")

    return data


def license_file(root: Path) -> Path | None:
    for name in LICENSE_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def license_sha256(root: Path) -> str | None:
    candidate = license_file(root)
    if candidate is None:
        return None
    return hashlib.sha256(candidate.read_bytes()).hexdigest()


def find_dependency_files(root: Path) -> list[str]:
    files: list[str] = []
    if not root.exists():
        return files

    for candidate in root.rglob("*"):
        if ".git" in candidate.parts:
            continue
        if candidate.is_file() and candidate.name in DEPENDENCY_MANIFEST_NAMES:
            files.append(candidate.relative_to(root).as_posix())

    return sorted(files)


def git_commit(root: Path) -> str | None:
    if not root.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def collect_inventory(manifest: dict[str, Any], project_root: Path) -> dict[str, Any]:
    collected_at = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for name, upstream in sorted(manifest["upstreams"].items()):
        root = project_root / upstream["local_path"]
        found_license = license_file(root)
        records.append(
            {
                "name": name,
                "repo": upstream["repo"],
                "repo_url": upstream["repo_url"],
                "local_path": upstream["local_path"],
                "upstream_path": upstream.get("path", ""),
                "usage": upstream["usage"],
                "reuse_policy": upstream["reuse_policy"],
                "declared_license": upstream["license"],
                "status": "cloned" if root.exists() else "missing",
                "commit": git_commit(root),
                "license_file": found_license.relative_to(root).as_posix()
                if found_license is not None
                else None,
                "license_sha256": license_sha256(root),
                "dependency_files": find_dependency_files(root),
                "copied_or_adapted_files": [],
                "local_modifications": [],
                "required_attribution": upstream.get("required_attribution", ""),
            }
        )

    return {
        "generated_at": collected_at,
        "phase": "0",
        "policy": "No upstream source files are copied into Vyu during Phase 0.",
        "upstreams": records,
    }


def write_lockfile(inventory: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_inventory(inventory: dict[str, Any], output: Path) -> None:
    lines = [
        "# Phase 0 Upstream Licence and Dependency Inventory",
        "",
        f"Generated: `{inventory['generated_at']}`",
        "",
        inventory["policy"],
        "",
        "| Upstream | Status | Commit | Licence | Licence SHA-256 | Dependency manifests | Reuse policy |",
        "|---|---|---|---|---|---:|---|",
    ]
    for upstream in inventory["upstreams"]:
        commit = upstream["commit"] or "not pinned"
        digest = upstream["license_sha256"] or "not captured"
        lines.append(
            "| {name} | {status} | {commit} | {license} | {digest} | {deps} | {policy} |".format(
                name=upstream["name"],
                status=upstream["status"],
                commit=commit,
                license=upstream["declared_license"],
                digest=digest,
                deps=len(upstream["dependency_files"]),
                policy=upstream["reuse_policy"],
            )
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Vyu Phase 0 upstream intake metadata.")
    parser.add_argument("--manifest", type=Path, default=Path("upstreams.yaml"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("UPSTREAM_LOCK.json"))
    parser.add_argument("--markdown", type=Path, default=Path("docs/phase0/license-inventory.md"))
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    inventory = collect_inventory(manifest, args.root)
    write_lockfile(inventory, args.output)
    write_markdown_inventory(inventory, args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
