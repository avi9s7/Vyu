from __future__ import annotations

import pytest

from src.vyu.ingestion.contracts import (
    DOCUMENT_STATUSES,
    QUERYABLE_DOCUMENT_STATUS,
    TERMINAL_DOCUMENT_STATUSES,
    DocumentStatus,
    can_transition_document_status,
)


@pytest.mark.parametrize(
    ("current", "target", "expected"),
    [
        ("awaiting_upload", "uploaded", True),
        ("uploaded", "scanning", True),
        ("scanning", "parsing", True),
        ("scanning", "blocked", True),
        ("parsing", "chunking", True),
        ("chunking", "ready", True),
        ("ready", "deleted", True),
        ("failed", "scanning", True),
        ("awaiting_upload", "ready", False),
        ("blocked", "parsing", False),
        ("ready", "parsing", False),
        ("deleted", "ready", False),
        ("scanning", "not_a_status", False),
    ],
)
def test_document_status_transitions(current: str, target: str, expected: bool) -> None:
    assert can_transition_document_status(current, target) is expected


def test_only_ready_versions_are_queryable() -> None:
    assert QUERYABLE_DOCUMENT_STATUS == DocumentStatus.READY.value


def test_terminal_statuses_do_not_allow_unapproved_exits() -> None:
    for status in TERMINAL_DOCUMENT_STATUSES:
        if status == DocumentStatus.FAILED.value:
            continue
        if status == DocumentStatus.READY.value:
            assert can_transition_document_status(status, DocumentStatus.DELETED.value)
            continue
        for target in DOCUMENT_STATUSES:
            if target == status:
                continue
            assert not can_transition_document_status(status, target)
