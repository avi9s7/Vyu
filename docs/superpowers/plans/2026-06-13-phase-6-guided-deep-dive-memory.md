# Phase 6 Guided Deep-Dive and Research Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic guided deep-dive, scoped research memory, follow-up decision classification, and evidence/research/policy output templates.

**Architecture:** Keep workflow state explicit and auditable. Store research memory under tenant/workspace/user/topic scope, classify follow-up intent from question wording and scoped memory, decompose questions into PICO-like fields, run up to two retrieval rounds, and render deterministic text outputs from existing answer/governance records.

**Tech Stack:** Python standard library, dataclasses, `unittest`.

---

## File Structure

- Create `src/vyu/memory/__init__.py`: memory exports.
- Create `src/vyu/memory/store.py`: scoped in-memory research memory and follow-up classification.
- Create `src/vyu/workflow/__init__.py`: workflow exports.
- Create `src/vyu/workflow/deep_dive.py`: PICO decomposition, coverage-gap detection, and two-round deep dive.
- Create `src/vyu/reports/__init__.py`: report exports.
- Create `src/vyu/reports/templates.py`: evidence brief, research report, and policy output templates.
- Create `tests/test_phase6_memory.py`: memory scoping and follow-up decision tests.
- Create `tests/test_phase6_deep_dive.py`: PICO and guided deep-dive tests.
- Create `tests/test_phase6_outputs.py`: output template tests.
- Modify `README.md`: document Phase 6 status and verification.
- Modify `docs/implementation-roadmap.md`: mark Phase 6 complete after verification.

## Task 1: Scoped Research Memory and Follow-Up Decisions

**Files:**
- Create: `tests/test_phase6_memory.py`
- Create: `src/vyu/memory/store.py`
- Create: `src/vyu/memory/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from src.vyu.memory import (
    FollowUpDecision,
    InMemoryResearchMemoryStore,
    ResearchMemoryRecord,
    classify_follow_up,
)


class Phase6MemoryTests(unittest.TestCase):
    def test_memory_is_scoped_by_tenant_workspace_user_and_topic(self):
        store = InMemoryResearchMemoryStore()
        record = ResearchMemoryRecord(
            tenant_id="tenant-a",
            workspace_id="migraine",
            user_id="user-1",
            topic="VX-101",
            question="Does VX-101 reduce migraine days?",
            retrieved_document_ids=["DOC-001"],
            generated_output_ids=["answer-1"],
        )

        store.save(record)

        self.assertEqual(1, len(store.list_for_scope("tenant-a", "migraine", "user-1", "VX-101")))
        self.assertEqual([], store.list_for_scope("tenant-b", "migraine", "user-1", "VX-101"))

    def test_follow_up_classifier_uses_question_intent(self):
        store = InMemoryResearchMemoryStore()

        self.assertEqual(
            FollowUpDecision.REUSE_EXISTING_EVIDENCE,
            classify_follow_up("Based on that evidence, summarize the main result.", store),
        )
        self.assertEqual(
            FollowUpDecision.SEARCH_NEW_EVIDENCE,
            classify_follow_up("Now check whether any new preprints disagree.", store),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase6_memory`

Expected: FAIL with missing memory package.

- [ ] **Step 3: Write minimal implementation**

Implement `FollowUpDecision`, `ResearchMemoryRecord`, `InMemoryResearchMemoryStore`, and `classify_follow_up()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase6_memory`

Expected: `Ran 2 tests ... OK`.

## Task 2: PICO Decomposition and Guided Deep Dive

**Files:**
- Create: `tests/test_phase6_deep_dive.py`
- Create: `src/vyu/workflow/deep_dive.py`
- Create: `src/vyu/workflow/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever
from src.vyu.workflow import decompose_pico, run_guided_deep_dive


class Phase6DeepDiveTests(unittest.TestCase):
    def test_pico_decomposition_extracts_vx101_defaults(self):
        pico = decompose_pico("Does VX-101 reduce migraine days in adults with episodic migraine compared with standard therapy?")

        self.assertEqual("adults with episodic migraine", pico.population)
        self.assertEqual("VX-101", pico.intervention)
        self.assertEqual("standard therapy", pico.comparator)
        self.assertIn("migraine days", pico.outcomes)

    def test_deep_dive_runs_no_more_than_two_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            result = run_guided_deep_dive(
                "Does VX-101 reduce migraine days in adults with episodic migraine?",
                retriever,
                max_rounds=2,
            )

        self.assertGreaterEqual(len(result.rounds), 1)
        self.assertLessEqual(len(result.rounds), 2)
        self.assertIn(result.stopping_reason, {"enough_evidence", "max_rounds_reached"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase6_deep_dive`

Expected: FAIL with missing workflow package.

- [ ] **Step 3: Write minimal implementation**

Implement `PICOQuestion`, `DeepDiveRound`, `DeepDiveResult`, `decompose_pico()`, `detect_coverage_gap()`, and `run_guided_deep_dive()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase6_deep_dive`

Expected: `Ran 2 tests ... OK`.

## Task 3: Evidence Brief, Research Report, and Policy Output Templates

**Files:**
- Create: `tests/test_phase6_outputs.py`
- Create: `src/vyu/reports/templates.py`
- Create: `src/vyu/reports/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import build_evidence_context, generate_grounded_answer, validate_citations
from src.vyu.governance import build_governance_box, calculate_trust_score
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.reports import render_evidence_brief, render_policy_output, render_research_report
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase6OutputTemplateTests(unittest.TestCase):
    def test_templates_include_answer_governance_and_review_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=3)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)
            answer = generate_grounded_answer(context)
            trust = calculate_trust_score(answer, context, validate_citations(answer, context))
            box = build_governance_box(context.question, context, trust, ["dummy_corpus"])

            brief = render_evidence_brief(answer, trust, box)
            report = render_research_report(answer, context, trust, box)
            policy = render_policy_output(answer, trust, box)

        self.assertIn("Evidence Brief", brief)
        self.assertIn("Research Report", report)
        self.assertIn("Human review", policy)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase6_outputs`

Expected: FAIL with missing reports package.

- [ ] **Step 3: Write minimal implementation**

Render deterministic markdown-like strings from answer, trust score, context, and governance box.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase6_outputs`

Expected: `Ran 1 test ... OK`.

## Task 4: Documentation and Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-roadmap.md`

- [ ] **Step 1: Update README**

Add Phase 6 status, created artifacts, limitations, and verification commands.

- [ ] **Step 2: Update implementation roadmap**

Mark Phase 6 complete, list implemented artifacts, and keep Phase 7 as the next phase.

## Task 5: Verify Phase 6

**Files:**
- All Phase 6 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_phase6_memory
python -m unittest tests.test_phase6_deep_dive
python -m unittest tests.test_phase6_outputs
```

Expected: all focused Phase 6 tests pass.

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0-6 tests pass.

- [ ] **Step 3: Inspect workspace status**

Run: `git status --short`

Expected: Phase 6 files, roadmap, and README changes are visible; `upstreams/` remains ignored.
