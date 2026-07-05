# Privacy Approval Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist privacy/PHI approval gate decisions in production-shaped SQLite storage and expose them to operators through scoped inspection and backup/restore.

**Architecture:** Reuse the existing `ProductionStorage` scoped-record pattern. Store `PrivacyApprovalRecord` rows with tenant/workspace scope, record append-only audit events, include records in backup payloads, and return them from `scripts/inspect_production_store.py`.

**Tech Stack:** Python standard library, dataclasses, sqlite3, unittest.

---

### Task 1: Storage Contract and Tests

**Files:**
- Modify: `tests/test_production_storage.py`
- Modify: `src/vyu/storage/production.py`
- Modify: `src/vyu/storage/__init__.py`

- [ ] **Step 1: Write failing tests**

Add tests that create a privacy approval record, persist it with `record_privacy_approval`, list it by scope, assert the audit event payload, and assert wrong tenant/workspace reads raise `PermissionError`.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `python -m unittest tests.test_production_storage`

Expected: failure because `PrivacyApprovalRecord` and storage methods do not exist.

- [ ] **Step 3: Implement minimal storage support**

Add `PrivacyApprovalRecord`, a `privacy_approvals` table, migration version `4`, save/list/record methods, scoped checks, and exports in `src/vyu/storage/production.py`. Re-export the record and migration constant from `src/vyu/storage/__init__.py`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `python -m unittest tests.test_production_storage`

Expected: all tests pass.

### Task 2: Inspection and Backup

**Files:**
- Modify: `tests/test_inspect_production_store.py`
- Modify: `tests/test_production_backup.py`
- Modify: `scripts/inspect_production_store.py`
- Modify: `scripts/backup_production_store.py`

- [ ] **Step 1: Write failing tests**

Add tests proving inspection output includes `privacy_approval_records`, wrong-scope privacy records are rejected, backup JSON includes privacy approvals, and restore preserves them.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `python -m unittest tests.test_inspect_production_store tests.test_production_backup`

Expected: failure because inspection and backup do not include privacy approvals yet.

- [ ] **Step 3: Implement minimal inspection and backup support**

Add privacy approvals to inspection output and backup count output; include privacy approvals in `ProductionStorage.export_backup` and `restore_backup`.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `python -m unittest tests.test_inspect_production_store tests.test_production_backup`

Expected: all tests pass.

### Task 3: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/project-overview-and-usage.md`
- Modify: `docs/production-grade-migration-plan.md`
- Modify: `docs/production/privacy-data-flow.md`
- Modify: `docs/production/operator-runbook.md`
- Modify: `docs/production/threat-model.md`

- [ ] **Step 1: Update status docs**

Document privacy approval persistence, operator inspection, backup/restore, and remaining limitations.

- [ ] **Step 2: Run full verification**

Run: `python -Wd -m unittest discover`

Expected: all tests pass without warning output.
