# VYU Repository Baseline and Engineering System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the unversioned VYU working folder into a reproducible, clean-clone project with safe exclusions, explicit tool versions, locked dependencies, real frontend tests, one verification command, CI, and truthful implementation tracking.

**Architecture:** Preserve current POC behavior while introducing repository-level quality boundaries. This plan does not migrate SQLite, add production APIs, or deploy AWS resources; it establishes the reliable engineering system required before those changes can be reviewed safely.

**Tech Stack:** Git, Python 3.13, uv, pytest, Ruff, mypy, Node.js 24, npm, Vitest, Testing Library, GitHub Actions.

---

## Prerequisites and Entry Gate

Read:

- `docs/production/JUNIOR_DEVELOPER_HANDBOOK.md`
- `docs/superpowers/specs/2026-07-05-vyu-production-platform-design.md`

This plan starts from the audited state where Git has no commits and repository files are untracked. Back up the working directory before changing ignore rules or creating the baseline commit. Do not delete patch archives, output databases, logs, frontend screenshots, `node_modules`, or `.next` during this plan; exclude them from Git and archive/remove them only in an owner-approved cleanup.

Verify the current behavior before Task 1:

```powershell
python -m unittest discover
npm.cmd run build --prefix apps/web
npm.cmd run lint --prefix apps/web
npm.cmd test --prefix apps/web
```

Expected audited result:

- Python: `Ran 388 tests ... OK (skipped=1)`.
- Frontend build: exits `0`.
- Frontend lint: exits `0`.
- Frontend test: exits `1` with `No test files found`.

## Planned File Map

| Path | Responsibility |
| --- | --- |
| `.gitignore` | Prevent secrets, local state, generated files, archives, and caches from entering Git |
| `.gitattributes` | Normalize text line endings and classify binary files |
| `.editorconfig` | Shared editor whitespace and encoding rules |
| `.python-version` | Pin the Python minor release |
| `.nvmrc` | Pin the Node.js major release |
| `pyproject.toml` | Python package, dependency groups, pytest, Ruff, mypy, and coverage configuration |
| `uv.lock` | Exact Python dependency resolution |
| `apps/web/package.json` | Frontend engine and verification scripts |
| `apps/web/package-lock.json` | Exact frontend dependency resolution |
| `apps/web/vitest.config.ts` | Vitest environment and path aliases |
| `apps/web/tests/setup.ts` | Testing Library matchers and cleanup |
| `apps/web/components/ui/Button.test.tsx` | First real frontend component test |
| `scripts/verify.py` | Cross-platform repository verification entry point |
| `tests/test_repository_hygiene.py` | Executable repository exclusion and metadata policy |
| `tests/test_python_project_config.py` | Executable Python packaging/tooling policy |
| `tests/test_verify_script.py` | Verification command composition tests |
| `docs/production/IMPLEMENTATION_STATUS.md` | Evidence-backed workstream status |
| `.github/workflows/ci.yml` | Clean-clone backend/frontend verification |

## Task 1: Enforce Repository Hygiene

**Files:**

- Create: `tests/test_repository_hygiene.py`
- Modify: `.gitignore`
- Create: `.gitattributes`
- Create: `.editorconfig`

- [ ] **Step 1: Write the failing repository-hygiene tests**

Create `tests/test_repository_hygiene.py`:

```python
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MUST_BE_IGNORED = (
    ".env",
    ".env.local",
    "config/deployment.local.env",
    "apps/web/node_modules/example.js",
    "apps/web/.next/BUILD_ID",
    ".pytest_cache/example",
    ".mypy_cache/example",
    ".ruff_cache/example",
    "htmlcov/index.html",
    ".coverage",
    "outputs/production.sqlite",
    "logs/application.log",
    "infra/terraform/environments/dev/terraform.tfstate",
    "infra/terraform/environments/dev/.terraform/provider.lock",
    "Additional_scripts_patch_v16/reference.patch",
    "Front End Screenshots/reference.png",
)

MUST_NOT_BE_IGNORED = (
    ".env.example",
    "config/deployment.local.example.env",
    "apps/web/package-lock.json",
    "uv.lock",
)


def check_ignore(path: str) -> int:
    completed = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path],
        cwd=ROOT,
        check=False,
    )
    return completed.returncode


class RepositoryHygieneTests(unittest.TestCase):
    def test_local_generated_and_secret_paths_are_ignored(self) -> None:
        failures = [path for path in MUST_BE_IGNORED if check_ignore(path) != 0]
        self.assertEqual([], failures, f"Paths must be ignored: {failures}")

    def test_examples_and_lock_files_are_not_ignored(self) -> None:
        failures = [path for path in MUST_NOT_BE_IGNORED if check_ignore(path) == 0]
        self.assertEqual([], failures, f"Paths must remain trackable: {failures}")

    def test_repository_metadata_files_exist(self) -> None:
        for relative_path in (".gitignore", ".gitattributes", ".editorconfig"):
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)

    def test_no_forbidden_path_is_tracked(self) -> None:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        tracked = completed.stdout.decode("utf-8").split("\0")
        forbidden_fragments = (
            "/node_modules/",
            "/.next/",
            "terraform.tfstate",
            ".env.local",
            "deployment.local.env",
        )
        failures = [
            path
            for path in tracked
            if any(fragment in f"/{path}" for fragment in forbidden_fragments)
        ]
        self.assertEqual([], failures, f"Forbidden tracked paths: {failures}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_repository_hygiene -v
```

Expected: failure listing at least `apps/web/node_modules/example.js`, `apps/web/.next/BUILD_ID`, `outputs/production.sqlite`, or a missing metadata file.

- [ ] **Step 3: Replace `.gitignore` with the production-safe rules**

Use this complete `.gitignore`:

```gitignore
# Secrets and local environment overrides
.env
.env.*
!.env.example
!.env.*.example
config/*.env
!config/*.example.env
!config/*.env.example

# Python
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
.coverage.*
coverage.xml
htmlcov/
dist/
build/
*.egg-info/

# Node / Next.js
node_modules/
.next/
out/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*

# Runtime state and generated evidence
outputs/
logs/
*.sqlite
*.sqlite3
*.db

# Terraform local state
.terraform/
*.tfstate
*.tfstate.*
crash.log
crash.*.log
*.tfplan
override.tf
override.tf.json
*_override.tf
*_override.tf.json

# Local upstream/reference archives
upstreams/
Additional_scripts_patch*/
Front End Screenshots/

# Editors and operating systems
.idea/
.vscode/
*.swp
*.swo
.DS_Store
Thumbs.db
Desktop.ini
```

- [ ] **Step 4: Add line-ending and editor policies**

Create `.gitattributes`:

```gitattributes
* text=auto eol=lf
*.ps1 text eol=crlf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png binary
*.jpg binary
*.jpeg binary
*.gif binary
*.pdf binary
*.zip binary
*.sqlite binary
*.sqlite3 binary
*.db binary
```

Create `.editorconfig`:

```editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.py]
indent_style = space
indent_size = 4
max_line_length = 100

[{*.js,*.jsx,*.ts,*.tsx,*.json,*.yml,*.yaml,*.md}]
indent_style = space
indent_size = 2

[*.ps1]
end_of_line = crlf
indent_style = space
indent_size = 4

[Makefile]
indent_style = tab
```

- [ ] **Step 5: Verify the policy passes**

Run:

```powershell
python -m unittest tests.test_repository_hygiene -v
git status --short --ignored
```

Expected:

- Four tests pass.
- `node_modules`, `.next`, outputs, logs, patch archives, and screenshots appear with `!!` when present.
- `.env.example`, example configuration, and lock files are not ignored.

- [ ] **Step 6: Commit the hygiene boundary**

```powershell
git add .gitignore .gitattributes .editorconfig tests/test_repository_hygiene.py
git commit -m "chore: establish repository hygiene policy"
```

## Task 2: Pin Developer Runtime Majors

**Files:**

- Create: `.python-version`
- Create: `.nvmrc`
- Modify: `apps/web/package.json`
- Modify: `tests/test_repository_hygiene.py`

- [ ] **Step 1: Extend the metadata test**

In `test_repository_metadata_files_exist`, replace the tuple with:

```python
        for relative_path in (
            ".gitignore",
            ".gitattributes",
            ".editorconfig",
            ".python-version",
            ".nvmrc",
        ):
```

Add this test method:

```python
    def test_runtime_major_versions_are_pinned(self) -> None:
        self.assertEqual("3.13", (ROOT / ".python-version").read_text().strip())
        self.assertEqual("24", (ROOT / ".nvmrc").read_text().strip())
```

- [ ] **Step 2: Verify the test fails for missing version files**

Run:

```powershell
python -m unittest tests.test_repository_hygiene -v
```

Expected: failure because `.python-version` and `.nvmrc` do not exist.

- [ ] **Step 3: Add version files**

Create `.python-version`:

```text
3.13
```

Create `.nvmrc`:

```text
24
```

- [ ] **Step 4: Add frontend engine constraints and a typecheck script**

In `apps/web/package.json`, add these top-level fields after `"private": true`:

```json
  "engines": {
    "node": ">=24 <25",
    "npm": ">=11 <12"
  },
```

Add this entry inside `scripts`:

```json
    "typecheck": "tsc --noEmit",
```

Do not change application dependencies or upgrade Next.js in this task; Plan 9 performs the framework migration with browser regression tests.

- [ ] **Step 5: Verify versions and tests**

Run:

```powershell
python -m unittest tests.test_repository_hygiene -v
npm.cmd run typecheck --prefix apps/web
```

Expected: all repository-hygiene tests pass and TypeScript exits `0`.

- [ ] **Step 6: Commit runtime pins**

```powershell
git add .python-version .nvmrc apps/web/package.json tests/test_repository_hygiene.py
git commit -m "chore: pin developer runtime majors"
```

## Task 3: Make the Python Project Installable and Reproducible

**Files:**

- Create: `tests/test_python_project_config.py`
- Modify: `pyproject.toml`
- Create: `uv.lock`

- [ ] **Step 1: Write failing project-configuration tests**

Create `tests/test_python_project_config.py`:

```python
from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PythonProjectConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_project_targets_python_313(self) -> None:
        self.assertEqual(">=3.13,<3.14", self.config["project"]["requires-python"])

    def test_build_backend_is_declared(self) -> None:
        self.assertEqual(
            "setuptools.build_meta",
            self.config["build-system"]["build-backend"],
        )

    def test_development_tools_are_declared(self) -> None:
        dependencies = "\n".join(self.config["dependency-groups"]["dev"])
        for required in ("pytest", "pytest-cov", "ruff", "mypy"):
            self.assertIn(required, dependencies)

    def test_static_analysis_targets_python_313(self) -> None:
        self.assertEqual("py313", self.config["tool"]["ruff"]["target-version"])
        self.assertEqual("3.13", self.config["tool"]["mypy"]["python_version"])

    def test_lock_file_exists(self) -> None:
        self.assertTrue((ROOT / "uv.lock").is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the current minimal `pyproject.toml` fails**

Run:

```powershell
python -m unittest tests.test_python_project_config -v
```

Expected: errors or failures for the missing build system, dependency group, Ruff, mypy, and lock file.

- [ ] **Step 3: Replace `pyproject.toml` with the baseline project definition**

Use:

```toml
[build-system]
requires = ["setuptools>=75,<76"]
build-backend = "setuptools.build_meta"

[project]
name = "vyu"
version = "0.1.0"
description = "Governed biomedical evidence research platform."
readme = "README.md"
requires-python = ">=3.13,<3.14"
dependencies = []

[dependency-groups]
dev = [
  "mypy>=1.14,<2",
  "pytest>=8.3,<9",
  "pytest-cov>=6,<7",
  "ruff>=0.9,<1",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["src*", "apps*", "scripts*"]
exclude = ["tests*", "upstreams*", "Additional_scripts_patch*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "--strict-config --strict-markers"

[tool.coverage.run]
branch = true
source = ["src/vyu"]

[tool.coverage.report]
show_missing = true
skip_covered = true

[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "apps", "scripts", "tests"]

[tool.ruff.lint]
select = ["E4", "E7", "E9", "F"]
ignore = []

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"

[tool.mypy]
python_version = "3.13"
files = ["scripts/verify.py"]
check_untyped_defs = true
disallow_any_generics = true
disallow_incomplete_defs = true
no_implicit_optional = true
show_error_codes = true
warn_redundant_casts = true
warn_return_any = true
warn_unused_ignores = true
```

Production dependencies remain empty in Plan 1 because the current code is standard-library based. Each later plan adds only the dependencies it actually uses and updates `uv.lock` in the same pull request.

- [ ] **Step 4: Generate and verify the lock**

Run:

```powershell
uv lock
uv sync --all-groups --frozen
uv run python -m unittest tests.test_python_project_config -v
uv build
```

Expected:

- `uv.lock` is created.
- Frozen sync exits `0` without changing the lock.
- Five configuration tests pass.
- `dist/` contains one wheel and one source distribution; `dist/` remains ignored.

- [ ] **Step 5: Run static analysis and record existing debt**

Run:

```powershell
uv run ruff check src apps/serverless scripts tests
uv run mypy
```

Expected: Ruff's baseline fatal-error rules pass across the existing Python tree. Mypy checks `scripts/verify.py`, the first newly introduced typed module, and passes. Every later plan adds its new production packages to mypy's `files` list in the same change that creates them. Do not disable mypy globally or add `ignore_errors = true`.

- [ ] **Step 6: Run the existing backend suite**

```powershell
uv run python -m unittest discover
```

Expected: 388 tests pass and one live PubMed test remains skipped unless the suite has intentionally gained reviewed tests.

- [ ] **Step 7: Commit Python packaging and locks**

```powershell
git add pyproject.toml uv.lock tests/test_python_project_config.py src apps/serverless scripts tests
git commit -m "build: add reproducible Python project tooling"
```

Inspect `git diff --cached --stat` before the commit. If mechanical formatting touched an excessive number of files, split formatting into its own commit and re-run the full suite after both commits.

## Task 4: Add Truthful Production Status Tracking

**Files:**

- Create: `docs/production/IMPLEMENTATION_STATUS.md`
- Create: `tests/test_implementation_status.py`

- [ ] **Step 1: Write the failing status-document test**

Create `tests/test_implementation_status.py`:

```python
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "production" / "IMPLEMENTATION_STATUS.md"


class ImplementationStatusTests(unittest.TestCase):
    def test_status_document_contains_all_plans_and_truthful_states(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        for plan_number in range(1, 11):
            self.assertIn(f"| {plan_number} |", text)
        self.assertIn("not_started", text)
        self.assertIn("in_progress", text)
        self.assertIn("staging_verified", text)
        self.assertIn("complete", text)

    def test_status_document_rejects_local_artifacts_as_production_evidence(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        self.assertIn("Local JSON and SQLite artifacts are not production evidence", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the test fails because the status document is absent**

```powershell
uv run python -m unittest tests.test_implementation_status -v
```

Expected: `FileNotFoundError` for `IMPLEMENTATION_STATUS.md`.

- [ ] **Step 3: Create the status document**

Create `docs/production/IMPLEMENTATION_STATUS.md`:

```markdown
# VYU Production Implementation Status

Last verified Git SHA: baseline pending  
Last verified date: 2026-07-05  
Overall state: development POC  

Allowed states: `not_started`, `in_progress`, `blocked`, `staging_verified`, `complete`.

Local JSON and SQLite artifacts are not production evidence. A plan reaches `complete` only when its exit gate has executable evidence bound to the recorded Git SHA.

| # | Workstream | Status | Owner | Issue/PR | Entry evidence | Exit evidence | Blockers |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Repository baseline and engineering system | in_progress | unassigned | none | Architecture approved | none | Initial Git baseline and CI are absent |
| 2 | PostgreSQL persistence and tenancy | not_started | unassigned | none | none | none | Plan 1 incomplete |
| 3 | FastAPI application and job platform | not_started | unassigned | none | none | none | Plan 2 incomplete |
| 4 | AWS infrastructure and deployment | not_started | unassigned | none | none | none | Plans 1-3 incomplete |
| 5 | Evidence ingestion | not_started | unassigned | none | none | none | Plans 2-4 incomplete |
| 6 | Governed connectors and retrieval | not_started | unassigned | none | none | none | Plans 2-4 incomplete |
| 7 | Model gateway and grounded synthesis | not_started | unassigned | none | none | none | Plans 2-4 and 6 incomplete |
| 8 | Governance, review, and exports | not_started | unassigned | none | none | none | Plans 2-4 and 7 incomplete |
| 9 | Frontend product completion | not_started | unassigned | none | none | none | Stable APIs from Plans 3 and 5-8 are required |
| 10 | Operational and pilot readiness | not_started | unassigned | none | none | none | Integrated product incomplete |

## Update Rule

Update one row in the same pull request that changes its evidence. Include command output or a durable staging evidence link. Never mark a row complete because files exist, unit tests pass, or a local readiness JSON says approved.
```

- [ ] **Step 4: Verify and commit status tracking**

```powershell
uv run python -m unittest tests.test_implementation_status -v
git add docs/production/IMPLEMENTATION_STATUS.md tests/test_implementation_status.py
git commit -m "docs: add evidence-backed production status tracking"
```

Expected: two tests pass.

## Task 5: Add a Cross-Platform Verification Command

**Files:**

- Create: `scripts/verify.py`
- Create: `tests/test_verify_script.py`

- [ ] **Step 1: Write failing verification-command tests**

Create `tests/test_verify_script.py`:

```python
from __future__ import annotations

import unittest

from scripts.verify import Command, commands_for_scope


class VerifyScriptTests(unittest.TestCase):
    def test_backend_scope_contains_quality_and_test_commands(self) -> None:
        commands = commands_for_scope("backend", npm="npm")
        self.assertEqual(
            [
                Command("ruff", ("uv", "run", "ruff", "check", "src", "apps/serverless", "scripts", "tests")),
                Command("mypy", ("uv", "run", "mypy")),
                Command("python-tests", ("uv", "run", "python", "-m", "unittest", "discover")),
            ],
            commands,
        )

    def test_frontend_scope_uses_clean_install_and_real_tests(self) -> None:
        commands = commands_for_scope("frontend", npm="npm.cmd")
        self.assertEqual(
            [
                Command("npm-ci", ("npm.cmd", "ci", "--prefix", "apps/web")),
                Command("frontend-typecheck", ("npm.cmd", "run", "typecheck", "--prefix", "apps/web")),
                Command("frontend-lint", ("npm.cmd", "run", "lint", "--prefix", "apps/web")),
                Command("frontend-tests", ("npm.cmd", "test", "--prefix", "apps/web")),
                Command("frontend-build", ("npm.cmd", "run", "build", "--prefix", "apps/web")),
            ],
            commands,
        )

    def test_all_scope_orders_backend_before_frontend(self) -> None:
        names = [command.name for command in commands_for_scope("all", npm="npm")]
        self.assertEqual("ruff", names[0])
        self.assertEqual("frontend-build", names[-1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify the module is missing**

```powershell
uv run python -m unittest tests.test_verify_script -v
```

Expected: import error for `scripts.verify`.

- [ ] **Step 3: Implement `scripts/verify.py`**

```python
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Literal, Sequence


Scope = Literal["backend", "frontend", "all"]


@dataclass(frozen=True)
class Command:
    name: str
    argv: tuple[str, ...]


def default_npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def commands_for_scope(scope: Scope, *, npm: str) -> list[Command]:
    backend = [
        Command("ruff", ("uv", "run", "ruff", "check", "src", "apps/serverless", "scripts", "tests")),
        Command("mypy", ("uv", "run", "mypy")),
        Command("python-tests", ("uv", "run", "python", "-m", "unittest", "discover")),
    ]
    frontend = [
        Command("npm-ci", (npm, "ci", "--prefix", "apps/web")),
        Command("frontend-typecheck", (npm, "run", "typecheck", "--prefix", "apps/web")),
        Command("frontend-lint", (npm, "run", "lint", "--prefix", "apps/web")),
        Command("frontend-tests", (npm, "test", "--prefix", "apps/web")),
        Command("frontend-build", (npm, "run", "build", "--prefix", "apps/web")),
    ]
    if scope == "backend":
        return backend
    if scope == "frontend":
        return frontend
    return [*backend, *frontend]


def run_commands(commands: Sequence[Command]) -> int:
    for command in commands:
        print(f"==> {command.name}: {' '.join(command.argv)}", flush=True)
        completed = subprocess.run(command.argv, check=False)
        if completed.returncode != 0:
            print(f"FAILED: {command.name} exited {completed.returncode}", file=sys.stderr)
            return completed.returncode
    print("Verification passed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the VYU repository.")
    parser.add_argument(
        "--scope",
        choices=("backend", "frontend", "all"),
        default="all",
    )
    args = parser.parse_args(argv)
    return run_commands(
        commands_for_scope(args.scope, npm=default_npm_executable())
    )


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Verify command composition**

```powershell
uv run python -m unittest tests.test_verify_script -v
```

Expected: three tests pass.

- [ ] **Step 5: Run backend verification**

```powershell
uv run python scripts/verify.py --scope backend
```

Expected: Ruff, mypy, and the full Python test suite pass, followed by `Verification passed.`

- [ ] **Step 6: Commit the verification entry point**

```powershell
git add scripts/verify.py tests/test_verify_script.py
git commit -m "build: add cross-platform verification command"
```

## Task 6: Add Real Frontend Tests

**Files:**

- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/tests/setup.ts`
- Create: `apps/web/components/ui/Button.test.tsx`

- [ ] **Step 1: Install the test DOM dependency**

Run:

```powershell
npm.cmd install --save-dev jsdom --prefix apps/web
```

Expected: `package.json` and `package-lock.json` change; no other source file changes.

- [ ] **Step 2: Add Vitest configuration**

Create `apps/web/vitest.config.ts`:

```typescript
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": root
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    restoreMocks: true,
    clearMocks: true
  }
});
```

Create `apps/web/tests/setup.ts`:

```typescript
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());
```

- [ ] **Step 3: Write the first component test**

Create `apps/web/components/ui/Button.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/Button";

describe("Button", () => {
  it("defaults to a non-submitting button and handles activation", () => {
    const onClick = vi.fn();

    render(<Button onClick={onClick}>Save report</Button>);

    const button = screen.getByRole("button", { name: "Save report" });
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("supports disabled state", () => {
    render(<Button disabled>Save report</Button>);

    expect(screen.getByRole("button", { name: "Save report" })).toBeDisabled();
  });
});
```

- [ ] **Step 4: Run frontend verification**

```powershell
npm.cmd run typecheck --prefix apps/web
npm.cmd run lint --prefix apps/web
npm.cmd test --prefix apps/web
npm.cmd run build --prefix apps/web
```

Expected:

- TypeScript and lint exit `0`.
- Vitest runs one file and two tests; both pass.
- Next.js production build exits `0`.

- [ ] **Step 5: Run the unified frontend command**

```powershell
uv run python scripts/verify.py --scope frontend
```

Expected: clean npm install, typecheck, lint, two tests, and build pass.

- [ ] **Step 6: Commit the frontend test baseline**

```powershell
git add apps/web/package.json apps/web/package-lock.json apps/web/vitest.config.ts apps/web/tests/setup.ts apps/web/components/ui/Button.test.tsx
git commit -m "test: establish frontend component testing"
```

## Task 7: Add Clean-Clone Continuous Integration

**Files:**

- Create: `.github/workflows/ci.yml`
- Modify: `tests/test_repository_hygiene.py`

- [ ] **Step 1: Add a failing CI-policy test**

Add to `RepositoryHygieneTests`:

```python
    def test_ci_workflow_has_read_only_default_permissions_and_two_jobs(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("backend:", workflow)
        self.assertIn("frontend:", workflow)
        self.assertIn("uv sync --all-groups --frozen", workflow)
        self.assertIn("npm ci", workflow)
```

- [ ] **Step 2: Verify the test fails because CI is absent**

```powershell
uv run python -m unittest tests.test_repository_hygiene -v
```

Expected: `FileNotFoundError` for `.github/workflows/ci.yml`.

- [ ] **Step 3: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - name: Check out source
        uses: actions/checkout@v6
      - name: Install uv and Python
        uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b # v8.1.0
        with:
          python-version: "3.13"
          enable-cache: true
      - name: Install locked dependencies
        run: uv sync --all-groups --frozen
      - name: Run backend verification
        run: uv run python scripts/verify.py --scope backend

  frontend:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    defaults:
      run:
        working-directory: apps/web
    steps:
      - name: Check out source
        uses: actions/checkout@v6
      - name: Set up Node.js
        uses: actions/setup-node@v6.4.0
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - name: Install locked dependencies
        run: npm ci
      - name: Type check
        run: npm run typecheck
      - name: Lint
        run: npm run lint
      - name: Test
        run: npm test
      - name: Build
        run: npm run build
```

The official `setup-uv` action is pinned to the v8.1.0 commit. Before merging, resolve the other two action tags to commit SHAs and replace them with this PowerShell sequence:

```powershell
$checkoutSha = (git ls-remote https://github.com/actions/checkout.git refs/tags/v6 | ForEach-Object { ($_ -split '\s+')[0] })
$setupNodeSha = (git ls-remote https://github.com/actions/setup-node.git refs/tags/v6.4.0 | ForEach-Object { ($_ -split '\s+')[0] })
if ($checkoutSha -notmatch '^[0-9a-f]{40}$') { throw 'Unable to resolve actions/checkout v6' }
if ($setupNodeSha -notmatch '^[0-9a-f]{40}$') { throw 'Unable to resolve actions/setup-node v6.4.0' }
$workflow = Get-Content -Raw .github/workflows/ci.yml
$workflow = $workflow.Replace('actions/checkout@v6', "actions/checkout@$checkoutSha # v6")
$workflow = $workflow.Replace('actions/setup-node@v6.4.0', "actions/setup-node@$setupNodeSha # v6.4.0")
Set-Content -Path .github/workflows/ci.yml -Value $workflow -Encoding utf8NoBOM
```

Then add this assertion to `test_ci_workflow_has_read_only_default_permissions_and_two_jobs`:

```python
        import re

        mutable = re.findall(r"uses:\s+[^\s]+@v\d", workflow)
        self.assertEqual([], mutable, f"Actions must use immutable SHAs: {mutable}")
```

The pull request must not merge while either action uses a mutable tag.

- [ ] **Step 4: Verify local policy and YAML syntax**

Run:

```powershell
uv run python -m unittest tests.test_repository_hygiene -v
uvx --from yamllint yamllint .github/workflows/ci.yml
```

Expected: repository tests pass. Resolve only substantive YAML errors; line-length warnings caused by immutable action SHAs may be disabled for that line or in a reviewed `.yamllint.yml`.

- [ ] **Step 5: Push a branch and verify both CI jobs**

Push the branch and open a pull request. Expected GitHub checks:

- `backend`: pass from a clean checkout and frozen dependency sync.
- `frontend`: pass from `npm ci`, typecheck, lint, real tests, and build.
- No workflow has write permissions.

- [ ] **Step 6: Commit CI**

```powershell
git add .github/workflows/ci.yml tests/test_repository_hygiene.py
git commit -m "ci: verify backend and frontend from clean checkout"
```

## Task 8: Create the Reviewed Baseline and Prove Reproducibility

**Files:**

- Modify: `docs/production/IMPLEMENTATION_STATUS.md`
- Review: all non-ignored repository files

- [ ] **Step 1: Confirm ignored material is not staged**

```powershell
git status --short --ignored
git ls-files | Select-String -Pattern 'node_modules|\.next|outputs/|logs/|\.sqlite|terraform\.tfstate|Additional_scripts_patch|Front End Screenshots'
```

Expected:

- Local/generated/reference directories appear ignored.
- The second command prints nothing.

- [ ] **Step 2: Review the complete baseline inventory**

```powershell
git ls-files
git diff --stat --cached
```

Expected: only source, tests, approved synthetic fixtures, configuration examples, infrastructure source, and current documentation are staged. No real secret, database, log, build output, upstream clone, or patch archive is present.

- [ ] **Step 3: Run complete verification**

```powershell
uv sync --all-groups --frozen
npm.cmd ci --prefix apps/web
uv run python scripts/verify.py --scope all
```

Expected: all quality checks, 388 or more Python tests, two or more frontend tests, and the frontend build pass.

- [ ] **Step 4: Update Plan 1 status evidence**

In `docs/production/IMPLEMENTATION_STATUS.md`:

- Change Plan 1 status from `in_progress` to `complete` only after CI passes.
- Set owner and issue/PR.
- Set entry evidence to the architecture-spec path.
- Set exit evidence to the CI run URL and clean-clone verification output.
- Set `Last verified Git SHA` to the merge commit SHA.
- Set `Last verified date` to the actual UTC verification date.
- Clear blockers only when the evidence exists.

- [ ] **Step 5: Commit the status evidence**

```powershell
git add docs/production/IMPLEMENTATION_STATUS.md
git commit -m "docs: record repository baseline evidence"
```

- [ ] **Step 6: Verify from a second clean clone**

Clone the repository into a separate directory with no existing `.venv`, `node_modules`, `.next`, outputs, or caches. Run:

```powershell
uv sync --all-groups --frozen
npm.cmd ci --prefix apps/web
uv run python scripts/verify.py --scope all
git status --short
```

Expected:

- Verification passes.
- `git status --short` is empty after verification because all generated outputs are ignored.

## Exit Gate

Plan 1 is complete only when:

- The repository has an owner-reviewed baseline commit and protected main branch.
- A clean clone installs from `uv.lock` and `package-lock.json` without modifying either.
- `scripts/verify.py --scope all` passes locally and in CI.
- CI has backend and frontend jobs with read-only permissions and immutable action SHAs.
- Frontend tests execute real tests instead of accepting an empty suite.
- Generated files, local state, secrets, archives, databases, and Terraform state are ignored and untracked.
- `IMPLEMENTATION_STATUS.md` records the merge SHA and CI evidence.
- No POC behavior was intentionally changed.

## Handoff to Plan 2

Plan 2 may begin only from the verified baseline SHA. Its first migration must introduce PostgreSQL/Alembic alongside the existing SQLite implementation; it must not delete the SQLite path until data-contract and parity tests prove the replacement.
