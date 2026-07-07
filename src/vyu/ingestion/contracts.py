from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    AWAITING_UPLOAD = "awaiting_upload"
    UPLOADED = "uploaded"
    SCANNING = "scanning"
    BLOCKED = "blocked"
    PARSING = "parsing"
    CHUNKING = "chunking"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class MalwareStatus(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"
    UNKNOWN = "unknown"


class PhiStatus(StrEnum):
    NON_PHI = "non_phi"
    SUSPECTED_PHI = "suspected_phi"
    UNKNOWN = "unknown"


DOCUMENT_STATUSES = tuple(status.value for status in DocumentStatus)
MALWARE_STATUSES = tuple(status.value for status in MalwareStatus)
PHI_STATUSES = tuple(status.value for status in PhiStatus)

TERMINAL_DOCUMENT_STATUSES = frozenset(
    {
        DocumentStatus.BLOCKED.value,
        DocumentStatus.READY.value,
        DocumentStatus.FAILED.value,
        DocumentStatus.DELETED.value,
    }
)

QUERYABLE_DOCUMENT_STATUS = DocumentStatus.READY.value

_ALLOWED_DOCUMENT_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.AWAITING_UPLOAD: frozenset({DocumentStatus.UPLOADED}),
    DocumentStatus.UPLOADED: frozenset({DocumentStatus.SCANNING}),
    DocumentStatus.SCANNING: frozenset(
        {DocumentStatus.PARSING, DocumentStatus.BLOCKED, DocumentStatus.FAILED}
    ),
    DocumentStatus.PARSING: frozenset(
        {DocumentStatus.CHUNKING, DocumentStatus.BLOCKED, DocumentStatus.FAILED}
    ),
    DocumentStatus.CHUNKING: frozenset({DocumentStatus.READY, DocumentStatus.FAILED}),
    DocumentStatus.READY: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.FAILED: frozenset({DocumentStatus.SCANNING}),
    DocumentStatus.BLOCKED: frozenset(),
    DocumentStatus.DELETED: frozenset(),
}


def can_transition_document_status(current: str, target: str) -> bool:
    try:
        current_status = DocumentStatus(current)
        target_status = DocumentStatus(target)
    except ValueError:
        return False
    return target_status in _ALLOWED_DOCUMENT_TRANSITIONS[current_status]
