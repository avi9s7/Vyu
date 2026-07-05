# Phase 2 Connector Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 2 connector layer so dummy/local records and mocked PubMed API responses return the same Vyu document and passage contracts with auditable search/fetch traces.

**Architecture:** Define connector request/result and audit contracts once, then implement source adapters against those contracts. `DummyConnector` reads the Phase 1 loaded corpus. `PubMedConnector` accepts an injectable transport function so unit tests can mock NCBI E-utilities without network access. Audit logging remains local and append-only as JSONL.

**Tech Stack:** Python standard library, dataclasses, JSONL audit files, `unittest`.

---

## File Structure

- Create `src/vyu/connectors/__init__.py`: exported connector contracts and adapters.
- Create `src/vyu/connectors/contracts.py`: `SearchRequest`, `ConnectorResult`, `ConnectorAuditEvent`, and `SourceConnector` protocol.
- Create `src/vyu/connectors/audit.py`: append/read JSONL audit events.
- Create `src/vyu/connectors/dummy.py`: connector over the Phase 1 dummy corpus.
- Create `src/vyu/connectors/pubmed.py`: mocked-testable PubMed ESearch/ESummary adapter.
- Create `tests/test_phase2_connector_contracts.py`: shared result/audit contract tests.
- Create `tests/test_phase2_dummy_connector.py`: dummy search/fetch behavior and audit tests.
- Create `tests/test_phase2_pubmed_connector.py`: PubMed XML/JSON mocked response tests.
- Modify `README.md`: document Phase 2 scope and verification.

## Task 1: Connector Contracts

**Files:**
- Create: `tests/test_phase2_connector_contracts.py`
- Create: `src/vyu/connectors/contracts.py`
- Create: `src/vyu/connectors/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from src.vyu.connectors import ConnectorAuditEvent, ConnectorResult, SearchRequest


class Phase2ConnectorContractsTests(unittest.TestCase):
    def test_connector_result_tracks_source_and_document_counts(self):
        request = SearchRequest(query="VX-101 migraine", limit=5)
        result = ConnectorResult(source="dummy", request=request, documents=[], passages=[])

        self.assertEqual("dummy", result.source)
        self.assertEqual(0, result.document_count)

    def test_audit_event_serializes_core_fields(self):
        event = ConnectorAuditEvent(
            source="dummy",
            action="search",
            query="VX-101",
            document_ids=["DOC-001"],
            status="ok",
        )

        self.assertEqual("search", event.to_json()["action"])
        self.assertEqual(["DOC-001"], event.to_json()["document_ids"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase2_connector_contracts`

Expected: FAIL with missing connector package.

- [ ] **Step 3: Write minimal implementation**

Implement dataclasses and a protocol. Keep defaults deterministic and source-agnostic.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase2_connector_contracts`

Expected: `Ran 2 tests ... OK`.

## Task 2: Dummy Connector

**Files:**
- Create: `tests/test_phase2_dummy_connector.py`
- Create: `src/vyu/connectors/dummy.py`
- Create: `src/vyu/connectors/audit.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.connectors import DummyConnector, JsonlAuditSink, SearchRequest
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase2DummyConnectorTests(unittest.TestCase):
    def test_dummy_connector_search_fetch_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            audit_path = root / "audit.jsonl"
            connector = DummyConnector(load_dummy_corpus(root), audit_sink=JsonlAuditSink(audit_path))

            result = connector.search(SearchRequest(query="retracted", limit=3))
            fetched = connector.fetch(result.documents[0].document_id)
            events = JsonlAuditSink(audit_path).read_events()

        self.assertGreaterEqual(result.document_count, 1)
        self.assertEqual(result.documents[0].document_id, fetched.document_id)
        self.assertEqual(["search", "fetch"], [event["action"] for event in events])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase2_dummy_connector`

Expected: FAIL with missing dummy connector or audit sink.

- [ ] **Step 3: Write minimal implementation**

Implement keyword search over loaded documents, matching passages for returned documents, document fetch by ID, and JSONL audit append/read behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase2_dummy_connector`

Expected: `Ran 1 test ... OK`.

## Task 3: PubMed Connector With Mock Transport

**Files:**
- Create: `tests/test_phase2_pubmed_connector.py`
- Create: `src/vyu/connectors/pubmed.py`

- [ ] **Step 1: Write the failing test**

```python
import tempfile
import unittest
from pathlib import Path

from src.vyu.connectors import JsonlAuditSink, PubMedConnector, SearchRequest


class Phase2PubMedConnectorTests(unittest.TestCase):
    def test_pubmed_connector_maps_mocked_responses_to_vyu_contracts(self):
        calls = []

        def transport(url, params):
            calls.append((url, params))
            if params["mode"] == "search":
                return {"ids": ["12345"]}
            return {
                "documents": [
                    {
                        "uid": "12345",
                        "title": "Mock VX-101 PubMed abstract",
                        "pubdate": "2026 Jan",
                        "source": "Mock Journal",
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            connector = PubMedConnector(transport=transport, audit_sink=JsonlAuditSink(audit_path))
            result = connector.search(SearchRequest(query="VX-101 migraine", limit=1))
            events = JsonlAuditSink(audit_path).read_events()

        self.assertEqual(["PUBMED-12345"], [doc.document_id for doc in result.documents])
        self.assertEqual(2, len(calls))
        self.assertEqual("search", events[0]["action"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_phase2_pubmed_connector`

Expected: FAIL with missing PubMed connector.

- [ ] **Step 3: Write minimal implementation**

Call injectable transport twice: once for search IDs and once for summaries. Map returned summaries into `DocumentRecord` and synthetic abstract passages.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_phase2_pubmed_connector`

Expected: `Ran 1 test ... OK`.

## Task 4: Verify Phase 2

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run full tests**

Run: `python -m unittest discover`

Expected: all Phase 0, Phase 1, and Phase 2 tests pass.

- [ ] **Step 2: Inspect workspace status**

Run: `git status --short`

Expected: new connector source, tests, docs, and README changes are visible; `upstreams/` remains ignored.
