# Phase 4 Grounded Answer Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic grounded answer generation over retrieved evidence with structured context, claim-level passage citations, citation validation, and abstention behavior.

**Architecture:** Keep generation model-free and deterministic for the POC. Convert retrieval hits into an `EvidenceContext`, assign stable citation IDs to passage-level evidence items, generate `GroundedAnswer` objects with `AnswerClaim` records, and validate that every cited claim references evidence present in the context.

**Tech Stack:** Python standard library, dataclasses, `unittest`.

---

## File Structure

- Create `src/vyu/generation/__init__.py`: generation exports.
- Create `src/vyu/generation/contracts.py`: `EvidenceItem`, `EvidenceContext`, `AnswerClaim`, `GroundedAnswer`, and citation validation result contracts.
- Create `src/vyu/generation/context.py`: context builder from retrieval hits.
- Create `src/vyu/generation/answer.py`: deterministic grounded answer generator and citation validator.
- Create `tests/test_phase4_context_builder.py`: context-building tests.
- Create `tests/test_phase4_grounded_answer.py`: answer, citation, and abstention tests.
- Modify `README.md`: document Phase 4 status and verification.
- Modify `docs/implementation-roadmap.md`: mark Phase 4 complete after verification.

## Task 1: Evidence Context Contracts and Builder

**Files:**
- Create: `tests/test_phase4_context_builder.py`
- Create: `src/vyu/generation/contracts.py`
- Create: `src/vyu/generation/context.py`
- Create: `src/vyu/generation/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import build_evidence_context
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase4ContextBuilderTests(unittest.TestCase):
    def test_context_assigns_stable_citation_ids_to_retrieved_passages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="VX-101 migraine trial", top_k=3)
            )

            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)

        self.assertEqual("Does VX-101 reduce migraine days?", context.question)
        self.assertEqual(3, len(context.items))
        self.assertEqual("CIT-001", context.items[0].citation_id)
        self.assertEqual(hits[0].passage_id, context.items[0].passage_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase4_context_builder`

Expected: FAIL with missing generation package.

- [ ] **Step 3: Write minimal implementation**

Implement contracts and `build_evidence_context(question, hits)` using stable citation IDs `CIT-001`, `CIT-002`, and so on.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase4_context_builder`

Expected: `Ran 1 test ... OK`.

## Task 2: Grounded Answer and Citation Validation

**Files:**
- Create: `tests/test_phase4_grounded_answer.py`
- Create: `src/vyu/generation/answer.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import build_evidence_context, generate_grounded_answer, validate_citations
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase4GroundedAnswerTests(unittest.TestCase):
    def test_grounded_answer_claims_have_valid_passage_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=4)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)

            answer = generate_grounded_answer(context)
            validation = validate_citations(answer, context)

        self.assertFalse(answer.abstained)
        self.assertGreaterEqual(len(answer.claims), 1)
        self.assertTrue(all(claim.citation_ids for claim in answer.claims))
        self.assertTrue(validation.valid)

    def test_grounded_answer_abstains_without_evidence(self):
        context = build_evidence_context("Does VX-101 prevent chronic migraine?", [])

        answer = generate_grounded_answer(context)
        validation = validate_citations(answer, context)

        self.assertTrue(answer.abstained)
        self.assertEqual([], answer.claims)
        self.assertTrue(validation.valid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase4_grounded_answer`

Expected: FAIL with missing answer exports.

- [ ] **Step 3: Write minimal implementation**

Implement deterministic answer generation. If no evidence exists, return an abstention. Otherwise create concise answer text and one claim per top evidence item, each citing its passage-level citation ID. Implement `validate_citations(answer, context)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase4_grounded_answer`

Expected: `Ran 2 tests ... OK`.

## Task 3: Documentation and Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-roadmap.md`

- [ ] **Step 1: Update README**

Add Phase 4 status, created artifacts, limitations, and verification commands.

- [ ] **Step 2: Update implementation roadmap**

Mark Phase 4 complete, list implemented artifacts, and keep Phase 5 as the next phase.

## Task 4: Verify Phase 4

**Files:**
- All Phase 4 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_phase4_context_builder
python -m unittest tests.test_phase4_grounded_answer
```

Expected: all focused Phase 4 tests pass.

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0-4 tests pass.

- [ ] **Step 3: Inspect workspace status**

Run: `git status --short`

Expected: Phase 4 files, roadmap, and README changes are visible; `upstreams/` remains ignored.
