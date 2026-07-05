# Phase 3 Retrieval Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local retrieval baseline over the synthetic corpus with BM25, deterministic dense retrieval, reciprocal-rank fusion, metadata filters, retrieval traces, and golden-question evaluation.

**Architecture:** Keep retrieval source-neutral and standard-library only. Build indexes from `LoadedCorpus` passages, return scored `RetrievalHit` records, apply filters before ranking where appropriate, and evaluate against Phase 1 golden-question expected documents. Real MedCPT/FAISS integration remains behind the dense retriever interface for a later dependency-enabled phase.

**Tech Stack:** Python standard library, dataclasses, `unittest`, JSON-serializable trace records.

---

## File Structure

- Create `src/vyu/retrieval/__init__.py`: retrieval exports.
- Create `src/vyu/retrieval/contracts.py`: retrieval query, filter, score, hit, and trace contracts.
- Create `src/vyu/retrieval/bm25.py`: BM25 lexical retriever.
- Create `src/vyu/retrieval/dense.py`: deterministic lexical-vector dense placeholder.
- Create `src/vyu/retrieval/rrf.py`: reciprocal-rank fusion.
- Create `src/vyu/retrieval/filters.py`: metadata filter helpers.
- Create `src/vyu/retrieval/evaluation.py`: Recall@K, MRR@K, and nDCG@K evaluation over golden questions.
- Create `tests/test_phase3_retrieval_bm25.py`: BM25 and trace tests.
- Create `tests/test_phase3_retrieval_fusion_filters.py`: dense, RRF, and filter tests.
- Create `tests/test_phase3_retrieval_evaluation.py`: golden-question metric tests.
- Modify `README.md`: document Phase 3 status and verification.
- Modify `docs/implementation-roadmap.md`: mark Phase 3 complete after verification.

## Task 1: Retrieval Contracts and BM25

**Files:**
- Create: `tests/test_phase3_retrieval_bm25.py`
- Create: `src/vyu/retrieval/contracts.py`
- Create: `src/vyu/retrieval/bm25.py`
- Create: `src/vyu/retrieval/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase3BM25RetrievalTests(unittest.TestCase):
    def test_bm25_returns_ranked_hits_with_trace_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            hits = retriever.search(RetrievalQuery(text="retracted VX-101 trial", top_k=5))

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual("bm25", hits[0].score.source)
        self.assertGreater(hits[0].score.value, 0)
        self.assertIn(hits[0].document_id, {"DOC-029", "DOC-030"})
        self.assertEqual(1, hits[0].trace.original_rank)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase3_retrieval_bm25`

Expected: FAIL with missing retrieval package.

- [ ] **Step 3: Write minimal implementation**

Implement `RetrievalQuery`, `RetrievalScore`, `RetrievalTrace`, `RetrievalHit`, and `BM25Retriever`. Tokenize lowercase alphanumeric text, compute standard BM25 over passages, aggregate each document by its best passage, and return ranked hits with original/final ranks.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase3_retrieval_bm25`

Expected: `Ran 1 test ... OK`.

## Task 2: Dense Placeholder, Filters, and RRF

**Files:**
- Create: `tests/test_phase3_retrieval_fusion_filters.py`
- Create: `src/vyu/retrieval/dense.py`
- Create: `src/vyu/retrieval/filters.py`
- Create: `src/vyu/retrieval/rrf.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import DenseKeywordRetriever, MetadataFilter, RetrievalQuery, reciprocal_rank_fusion


class Phase3FusionFilterTests(unittest.TestCase):
    def test_filter_excludes_retracted_documents_and_rrf_combines_ranks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = DenseKeywordRetriever.from_corpus(corpus)

            filtered_hits = retriever.search(
                RetrievalQuery(
                    text="retracted VX-101 trial",
                    top_k=10,
                    metadata_filter=MetadataFilter(include_retracted=False),
                )
            )
            unfiltered_hits = retriever.search(RetrievalQuery(text="VX-101 trial", top_k=5))
            fused = reciprocal_rank_fusion([filtered_hits, unfiltered_hits], top_k=5)

        self.assertTrue(all(not hit.document.is_retracted for hit in filtered_hits))
        self.assertGreaterEqual(len(fused), 1)
        self.assertEqual("rrf", fused[0].score.source)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase3_retrieval_fusion_filters`

Expected: FAIL with missing dense/filter/RRF exports.

- [ ] **Step 3: Write minimal implementation**

Implement `MetadataFilter.matches(document)`, a deterministic dense placeholder using cosine similarity over term-frequency counters, and reciprocal-rank fusion over hit lists.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase3_retrieval_fusion_filters`

Expected: `Ran 1 test ... OK`.

## Task 3: Golden-Question Evaluation

**Files:**
- Create: `tests/test_phase3_retrieval_evaluation.py`
- Create: `src/vyu/retrieval/evaluation.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, evaluate_golden_questions


class Phase3RetrievalEvaluationTests(unittest.TestCase):
    def test_evaluation_reports_recall_mrr_and_ndcg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            metrics = evaluate_golden_questions(corpus, retriever, top_k=10)

        self.assertIn("recall_at_10", metrics)
        self.assertIn("mrr_at_10", metrics)
        self.assertIn("ndcg_at_10", metrics)
        self.assertGreaterEqual(metrics["recall_at_10"], 0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase3_retrieval_evaluation`

Expected: FAIL with missing evaluation export.

- [ ] **Step 3: Write minimal implementation**

Evaluate every golden question by calling the retriever with the question text. Compute mean Recall@K, MRR@K, and nDCG@K against expected document IDs.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase3_retrieval_evaluation`

Expected: `Ran 1 test ... OK`.

## Task 4: Documentation and Roadmap

**Files:**
- Modify: `README.md`
- Modify: `docs/implementation-roadmap.md`

- [ ] **Step 1: Update README**

Add Phase 3 status, created artifacts, and verification commands.

- [ ] **Step 2: Update implementation roadmap**

Mark Phase 3 complete, list implemented artifacts and current limitations, and keep Phases 4-7 as not started.

## Task 5: Verify Phase 3

**Files:**
- All Phase 3 files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
python -m unittest tests.test_phase3_retrieval_bm25
python -m unittest tests.test_phase3_retrieval_fusion_filters
python -m unittest tests.test_phase3_retrieval_evaluation
```

Expected: all focused Phase 3 tests pass.

- [ ] **Step 2: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0-3 tests pass.

- [ ] **Step 3: Inspect workspace status**

Run: `git status --short`

Expected: Phase 3 files, roadmap, and README changes are visible; `upstreams/` remains ignored.
