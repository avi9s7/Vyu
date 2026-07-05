# Phase 7 RAG-Gym-Style Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a transparent RAG-Gym-style evaluation layer that exports research trajectories, compares fixed versus iterative workflows, and reports quality, cost, latency, and auditability tradeoffs.

**Architecture:** Do not train agents or import RAG-Gym source. Represent each retrieval/action step as a JSON-serializable trajectory event. Evaluate a fixed one-shot retrieval baseline against the existing guided deep-dive workflow. Produce an adoption report that recommends keeping deterministic workflow unless iterative quality improves without reducing auditability.

**Tech Stack:** Python standard library, dataclasses, `unittest`.

---

## File Structure

- Create `src/vyu/evaluation/__init__.py`: evaluation exports.
- Create `src/vyu/evaluation/trajectories.py`: trajectory event/run contracts and export helpers.
- Create `src/vyu/evaluation/comparison.py`: fixed versus iterative workflow comparison.
- Create `src/vyu/evaluation/report.py`: cost, latency, quality, auditability report.
- Create `tests/test_phase7_trajectories.py`: trajectory export tests.
- Create `tests/test_phase7_comparison_report.py`: comparison and report tests.
- Modify `README.md`: document Phase 7 status and verification.
- Modify `docs/implementation-roadmap.md`: mark Phase 7 complete after verification.

## Task 1: Trajectory Export

**Files:**
- Create: `tests/test_phase7_trajectories.py`
- Create: `src/vyu/evaluation/trajectories.py`
- Create: `src/vyu/evaluation/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evaluation import export_deep_dive_trajectory
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever
from src.vyu.workflow import run_guided_deep_dive


class Phase7TrajectoryTests(unittest.TestCase):
    def test_deep_dive_trajectory_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            result = run_guided_deep_dive(
                "Does VX-101 reduce migraine days?",
                BM25Retriever.from_corpus(corpus),
                max_rounds=2,
            )

            trajectory = export_deep_dive_trajectory(result)

        self.assertEqual("guided_deep_dive", trajectory.workflow)
        self.assertGreaterEqual(len(trajectory.events), 1)
        self.assertIn("query", trajectory.to_json()["events"][0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase7_trajectories`

Expected: FAIL with missing evaluation package.

- [ ] **Step 3: Write minimal implementation**

Implement `TrajectoryEvent`, `ResearchTrajectory`, and `export_deep_dive_trajectory()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase7_trajectories`

Expected: `Ran 1 test ... OK`.

## Task 2: Workflow Comparison and Adoption Report

**Files:**
- Create: `tests/test_phase7_comparison_report.py`
- Create: `src/vyu/evaluation/comparison.py`
- Create: `src/vyu/evaluation/report.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evaluation import compare_workflows, render_adoption_report
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever


class Phase7ComparisonReportTests(unittest.TestCase):
    def test_comparison_and_report_include_quality_cost_latency_auditability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            comparison = compare_workflows(
                corpus,
                retriever,
                questions=["Does VX-101 reduce migraine days?"],
            )
            report = render_adoption_report(comparison)

        self.assertIn("fixed_one_shot", comparison.workflow_metrics)
        self.assertIn("guided_deep_dive", comparison.workflow_metrics)
        self.assertIn("Quality", report)
        self.assertIn("Auditability", report)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase7_comparison_report`

Expected: FAIL with missing comparison/report exports.

- [ ] **Step 3: Write minimal implementation**

Implement `WorkflowComparison`, `WorkflowMetrics`, `compare_workflows()`, and `render_adoption_report()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase7_comparison_report`

Expected: `Ran 1 test ... OK`.

## Task 3: Documentation and Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-roadmap.md`

- [ ] **Step 1: Update README**

Add Phase 7 status, created artifacts, limitations, and verification commands.

- [ ] **Step 2: Update implementation roadmap**

Mark Phase 7 complete and note that no RAG-Gym training or source import was performed.

## Task 4: Verify Phase 7

**Files:**
- All Phase 7 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_phase7_trajectories
python -m unittest tests.test_phase7_comparison_report
```

Expected: all focused Phase 7 tests pass.

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0-7 tests pass.

- [ ] **Step 3: Inspect workspace status**

Run: `git status --short`

Expected: Phase 7 files, roadmap, and README changes are visible; `upstreams/` remains ignored.
