# Phase 1 Dummy Corpus and Domain Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 1 local synthetic biomedical corpus, Vyu-owned data contracts, corpus loader, and database schema so the dummy records can be loaded, normalized, queried, and inspected without an LLM.

**Architecture:** Use Vyu-owned dataclasses as the canonical internal contracts. Generate deterministic fictional JSONL records and minimal synthetic PDFs from a script, then load them through a small ingestion module that validates identifiers, passage links, retraction flags, and golden-question references. Keep all data local and synthetic.

**Tech Stack:** Python standard library, `unittest`, dataclasses, JSONL files, SQLite schema.

---

## File Structure

- Create `src/vyu/__init__.py`: package marker.
- Create `src/vyu/contracts/__init__.py`: exported contract types.
- Create `src/vyu/contracts/evidence.py`: document, passage, evidence, citation, question, and loaded corpus dataclasses.
- Create `src/vyu/ingestion/__init__.py`: package marker.
- Create `src/vyu/ingestion/dummy_corpus.py`: JSONL reader, corpus loader, validation, and simple query inspection.
- Create `src/vyu/storage/schema.sql`: local relational schema for documents, passages, evidence profiles, citations, memory, and audit events.
- Create `src/vyu/storage/__init__.py`: schema loader helper.
- Create `scripts/generate_phase1_corpus.py`: deterministic generator for 30 fictional documents, passages, ground truth, golden questions, and two minimal PDFs.
- Create `tests/test_phase1_contracts.py`: contract behavior tests.
- Create `tests/test_phase1_corpus_generation.py`: corpus generator and file shape tests.
- Create `tests/test_phase1_loader.py`: loader validation and query inspection tests.
- Create `tests/test_phase1_schema.py`: SQLite schema smoke tests.
- Modify `README.md`: document Phase 1 verification commands and generated artifacts.

## Task 1: Domain Contracts

**Files:**
- Create: `tests/test_phase1_contracts.py`
- Create: `src/vyu/contracts/evidence.py`
- Create: `src/vyu/contracts/__init__.py`
- Create: `src/vyu/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from src.vyu.contracts import DocumentRecord, EvidenceProfile, PassageRecord, StudyDesign


class Phase1ContractsTests(unittest.TestCase):
    def test_document_materializes_stable_citation_label(self):
        document = DocumentRecord(
            document_id="DOC-001",
            title="VX-101 Trial",
            year=2026,
            study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL,
            source_type="dummy_pubmed",
            publication_status="peer_reviewed",
        )

        self.assertEqual("DOC-001 (2026)", document.citation_label)

    def test_evidence_profile_flags_human_review_for_retracted_source(self):
        profile = EvidenceProfile(
            document_id="DOC-030",
            study_design=StudyDesign.CASE_REPORT,
            evidence_level="lower",
            bias_flags=[],
            applicability_flags=[],
            retraction_status="retracted",
            preprint_status=False,
            assessment_confidence=0.5,
        )

        self.assertTrue(profile.requires_human_review)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase1_contracts`

Expected: FAIL with `ModuleNotFoundError` or missing contract names.

- [ ] **Step 3: Write minimal implementation**

Define `StudyDesign` as a `str` enum and create frozen dataclasses for `DocumentRecord`, `PassageRecord`, `EvidenceProfile`, `CitationRecord`, `GoldenQuestion`, and `LoadedCorpus`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase1_contracts`

Expected: `Ran 2 tests ... OK`.

## Task 2: Deterministic Synthetic Corpus Generator

**Files:**
- Create: `tests/test_phase1_corpus_generation.py`
- Create: `scripts/generate_phase1_corpus.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus


class Phase1CorpusGenerationTests(unittest.TestCase):
    def test_generator_creates_required_phase1_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)

            documents = [json.loads(line) for line in (root / "data/dummy_articles/documents.jsonl").read_text().splitlines()]
            passages = [json.loads(line) for line in (root / "data/dummy_articles/passages.jsonl").read_text().splitlines()]
            questions = [json.loads(line) for line in (root / "data/golden_questions/questions.jsonl").read_text().splitlines()]

        self.assertEqual(30, len(documents))
        self.assertGreaterEqual(len(passages), 60)
        self.assertEqual(15, len(questions))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase1_corpus_generation`

Expected: FAIL with missing generator module.

- [ ] **Step 3: Write minimal implementation**

Generate 30 fictional VX-101 records across the categories from the README. Write `documents.jsonl`, `passages.jsonl`, `evidence_ground_truth.jsonl`, `retraction_ground_truth.jsonl`, `questions.jsonl`, `expected_documents.jsonl`, `expected_citations.jsonl`, `expected_evidence_flags.jsonl`, and two valid minimal PDFs.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase1_corpus_generation`

Expected: `Ran 1 test ... OK`.

## Task 3: Corpus Loader and Query Inspection

**Files:**
- Create: `tests/test_phase1_loader.py`
- Create: `src/vyu/ingestion/dummy_corpus.py`
- Create: `src/vyu/ingestion/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase1LoaderTests(unittest.TestCase):
    def test_loader_validates_links_and_supports_keyword_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)

        self.assertEqual(30, len(corpus.documents))
        self.assertEqual(15, len(corpus.golden_questions))
        self.assertGreaterEqual(len(corpus.find_documents("retracted")), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase1_loader`

Expected: FAIL with missing loader module.

- [ ] **Step 3: Write minimal implementation**

Load JSONL files into contract dataclasses, validate passage document IDs exist, validate evidence and retraction document IDs exist, and expose `LoadedCorpus.find_documents(keyword)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase1_loader`

Expected: `Ran 1 test ... OK`.

## Task 4: SQLite Schema

**Files:**
- Create: `tests/test_phase1_schema.py`
- Create: `src/vyu/storage/schema.sql`
- Create: `src/vyu/storage/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import sqlite3
import unittest

from src.vyu.storage import load_schema_sql


class Phase1SchemaTests(unittest.TestCase):
    def test_schema_creates_core_phase1_tables(self):
        connection = sqlite3.connect(":memory:")
        connection.executescript(load_schema_sql())
        tables = {
            row[0]
            for row in connection.execute("select name from sqlite_master where type = 'table'")
        }

        self.assertIn("documents", tables)
        self.assertIn("passages", tables)
        self.assertIn("evidence_profiles", tables)
        self.assertIn("golden_questions", tables)
        self.assertIn("audit_events", tables)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase1_schema`

Expected: FAIL with missing storage module.

- [ ] **Step 3: Write minimal implementation**

Add a SQLite schema with primary keys and foreign keys for Phase 1 entities. Add `load_schema_sql()` to read the schema file.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase1_schema`

Expected: `Ran 1 test ... OK`.

## Task 5: Generate Workspace Data and Verify

**Files:**
- Generated: `data/dummy_articles/documents.jsonl`
- Generated: `data/dummy_articles/passages.jsonl`
- Generated: `data/dummy_articles/evidence_ground_truth.jsonl`
- Generated: `data/dummy_articles/retraction_ground_truth.jsonl`
- Generated: `data/dummy_pdfs/*.pdf`
- Generated: `data/golden_questions/questions.jsonl`
- Generated: `data/golden_questions/expected_documents.jsonl`
- Generated: `data/golden_questions/expected_citations.jsonl`
- Generated: `data/golden_questions/expected_evidence_flags.jsonl`
- Modify: `README.md`

- [ ] **Step 1: Generate the local corpus**

Run: `python scripts/generate_phase1_corpus.py --root .`

Expected: required data files are created under `data/`.

- [ ] **Step 2: Run complete tests**

Run: `python -m unittest discover`

Expected: all Phase 0 and Phase 1 tests pass.

- [ ] **Step 3: Inspect Git status**

Run: `git status --short`

Expected: new Phase 1 source, tests, docs, and generated synthetic data are visible; `upstreams/` remains ignored.
