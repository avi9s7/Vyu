# Phase 5 Evidence and Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic evidence and governance outputs: automated evidence profiles, contradiction detection, explainable Trust Score, Governance Box, and JSON audit export.

**Architecture:** Use the Phase 1 evidence ground truth and Phase 4 answer/context contracts as inputs. Keep all rules explicit and deterministic. Output JSON-serializable governance records that explain evidence strength, warnings, conflicts, citation coverage, and audit metadata.

**Tech Stack:** Python standard library, dataclasses, `unittest`, JSON.

---

## File Structure

- Create `src/vyu/evidence/__init__.py`: evidence exports.
- Create `src/vyu/evidence/profiles.py`: automated evidence profile builder.
- Create `src/vyu/evidence/contradictions.py`: contradiction detector.
- Create `src/vyu/governance/__init__.py`: governance exports.
- Create `src/vyu/governance/trust.py`: Trust Score component calculation.
- Create `src/vyu/governance/box.py`: user-readable and JSON Governance Box builder.
- Create `src/vyu/governance/audit.py`: JSON audit export.
- Create `tests/test_phase5_evidence_profiles.py`: profile and contradiction tests.
- Create `tests/test_phase5_governance.py`: Trust Score, Governance Box, and audit export tests.
- Modify `README.md`: document Phase 5 status and verification.
- Modify `docs/implementation-roadmap.md`: mark Phase 5 complete after verification.

## Task 1: Evidence Profiles and Contradiction Detection

**Files:**
- Create: `tests/test_phase5_evidence_profiles.py`
- Create: `src/vyu/evidence/profiles.py`
- Create: `src/vyu/evidence/contradictions.py`
- Create: `src/vyu/evidence/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evidence import build_automated_evidence_profile, detect_contradictions
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase5EvidenceProfileTests(unittest.TestCase):
    def test_profile_flags_retracted_preprint_and_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)

            retracted = build_automated_evidence_profile(corpus, "DOC-029")
            preprint = build_automated_evidence_profile(corpus, "DOC-022")

        self.assertTrue(retracted.requires_human_review)
        self.assertIn("retracted", retracted.warnings)
        self.assertTrue(preprint.requires_human_review)
        self.assertIn("preprint", preprint.applicability_flags)

    def test_detector_finds_conflicting_primary_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            documents = [corpus.documents["DOC-001"], corpus.documents["DOC-002"]]

            conflicts = detect_contradictions(documents)

        self.assertGreaterEqual(len(conflicts), 1)
        self.assertEqual({"DOC-001", "DOC-002"}, set(conflicts[0].document_ids))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase5_evidence_profiles`

Expected: FAIL with missing evidence package.

- [ ] **Step 3: Write minimal implementation**

Implement an `AutomatedEvidenceProfile` dataclass, builder from loaded corpus evidence profiles, and a simple contradiction detector using positive/negative/mixed/insufficient language in synthetic abstracts.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase5_evidence_profiles`

Expected: `Ran 2 tests ... OK`.

## Task 2: Trust Score, Governance Box, and Audit Export

**Files:**
- Create: `tests/test_phase5_governance.py`
- Create: `src/vyu/governance/trust.py`
- Create: `src/vyu/governance/box.py`
- Create: `src/vyu/governance/audit.py`
- Create: `src/vyu/governance/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import build_evidence_context, generate_grounded_answer, validate_citations
from src.vyu.governance import build_governance_box, calculate_trust_score, export_audit_record
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase5GovernanceTests(unittest.TestCase):
    def test_trust_score_governance_box_and_audit_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=5)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)
            answer = generate_grounded_answer(context)
            validation = validate_citations(answer, context)

            trust = calculate_trust_score(answer, context, validation)
            box = build_governance_box(
                question=context.question,
                context=context,
                trust_score=trust,
                sources_searched=["dummy_corpus"],
            )
            audit = export_audit_record(answer, context, trust, box)

        self.assertGreaterEqual(trust.overall, 0)
        self.assertLessEqual(trust.overall, 100)
        self.assertIn("citation_coverage", trust.components)
        self.assertEqual("dummy_corpus", box.sources_searched[0])
        self.assertEqual(answer.question, audit["answer"]["question"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase5_governance`

Expected: FAIL with missing governance package.

- [ ] **Step 3: Write minimal implementation**

Implement `TrustScore`, `GovernanceBox`, `calculate_trust_score()`, `build_governance_box()`, and `export_audit_record()` using deterministic component rules.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase5_governance`

Expected: `Ran 1 test ... OK`.

## Task 3: Documentation and Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-roadmap.md`

- [ ] **Step 1: Update README**

Add Phase 5 status, created artifacts, limitations, and verification commands.

- [ ] **Step 2: Update implementation roadmap**

Mark Phase 5 complete, list implemented artifacts, and keep Phase 6 as the next phase.

## Task 4: Verify Phase 5

**Files:**
- All Phase 5 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_phase5_evidence_profiles
python -m unittest tests.test_phase5_governance
```

Expected: all focused Phase 5 tests pass.

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0-5 tests pass.

- [ ] **Step 3: Inspect workspace status**

Run: `git status --short`

Expected: Phase 5 files, roadmap, and README changes are visible; `upstreams/` remains ignored.
