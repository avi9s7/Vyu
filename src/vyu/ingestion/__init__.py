"""Governed evidence ingestion domain."""

from src.vyu.ingestion.contracts import (
    DOCUMENT_STATUSES,
    MALWARE_STATUSES,
    PHI_STATUSES,
    TERMINAL_DOCUMENT_STATUSES,
    DocumentStatus,
    MalwareStatus,
    PhiStatus,
    can_transition_document_status,
)

__all__ = [
    "DOCUMENT_STATUSES",
    "MALWARE_STATUSES",
    "PHI_STATUSES",
    "TERMINAL_DOCUMENT_STATUSES",
    "DocumentStatus",
    "MalwareStatus",
    "PhiStatus",
    "can_transition_document_status",
]
