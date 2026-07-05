from __future__ import annotations

from src.vyu.generation.contracts import EvidenceContext, EvidenceItem
from src.vyu.retrieval import RetrievalHit


def build_evidence_context(question: str, hits: list[RetrievalHit]) -> EvidenceContext:
    items = [
        EvidenceItem(
            citation_id=f"CIT-{index:03d}",
            document_id=hit.document_id,
            passage_id=hit.passage_id,
            title=hit.document.title,
            passage_text=hit.passage.text,
            retrieval_score=hit.score.value,
            retrieval_source=hit.score.source,
            is_retracted=hit.document.is_retracted,
            is_preprint=hit.document.is_preprint,
        )
        for index, hit in enumerate(hits, start=1)
    ]
    return EvidenceContext(question=question, items=items)
