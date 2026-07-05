from __future__ import annotations

from dataclasses import dataclass

from src.vyu.contracts import DocumentRecord


@dataclass(frozen=True)
class Contradiction:
    document_ids: list[str]
    issue: str
    description: str

    def to_json(self) -> dict[str, object]:
        return {
            "document_ids": self.document_ids,
            "issue": self.issue,
            "description": self.description,
        }


def detect_contradictions(documents: list[DocumentRecord]) -> list[Contradiction]:
    positive = [
        document
        for document in documents
        if _contains_any(document, ["positive finding", "benefit", "reduced"])
        and not _contains_any(document, ["negative finding", "no vx-101"])
    ]
    negative = [
        document
        for document in documents
        if _contains_any(document, ["negative finding", "no vx-101", "null"])
    ]
    if not positive or not negative:
        return []

    return [
        Contradiction(
            document_ids=[positive[0].document_id, negative[0].document_id],
            issue="conflicting_primary_outcome",
            description=(
                "Synthetic evidence contains both positive and negative findings "
                "for VX-101 primary migraine-day outcomes."
            ),
        )
    ]


def _contains_any(document: DocumentRecord, needles: list[str]) -> bool:
    haystack = f"{document.title} {document.abstract}".lower()
    return any(needle in haystack for needle in needles)
