# Persist Phase Outputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic script that writes Phase 2-7 outputs as persisted artifacts under `outputs/`.

**Architecture:** Keep phase logic in existing `src/vyu` modules and add one orchestration script in `scripts/`. The script loads the local dummy corpus, runs representative Phase 2-7 flows, and writes JSON, JSONL, and Markdown artifacts.

**Tech Stack:** Python standard library, existing `src.vyu` modules, `unittest`.

---

### Task 1: Add Artifact Runner Test

**Files:**
- Create: `tests/test_phase_outputs_script.py`
- Create: `scripts/run_phase_outputs.py`

- [ ] **Step 1: Write the failing test**

Add a unittest that imports `run_phase_outputs`, runs it in a temporary workspace after generating the dummy corpus, and asserts the expected files exist with key fields.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase_outputs_script`
Expected: failure because `scripts.run_phase_outputs` does not exist.

- [ ] **Step 3: Implement the artifact runner**

Create `scripts/run_phase_outputs.py` with a `run_phase_outputs(root, output_dir)` function and CLI entry point.

- [ ] **Step 4: Run focused test**

Run: `python -m unittest tests.test_phase_outputs_script`
Expected: pass.

- [ ] **Step 5: Run full suite**

Run: `python -m unittest discover`
Expected: all tests pass.

### Task 2: Document Output Command

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add output persistence note**

Document `python scripts/run_phase_outputs.py --root . --output-dir outputs`.

- [ ] **Step 2: Run script in project workspace**

Run the new command and confirm `outputs/phase2` through `outputs/phase7` are written.
