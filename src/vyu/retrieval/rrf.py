from __future__ import annotations

from src.vyu.retrieval.contracts import (
    RetrievalHit,
    RetrievalScore,
    RetrievalTrace,
)


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalHit]],
    top_k: int = 10,
    rank_constant: int = 60,
) -> list[RetrievalHit]:
    by_document: dict[str, RetrievalHit] = {}
    scores: dict[str, float] = {}
    components: dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, hit in enumerate(ranked_list, start=1):
            by_document.setdefault(hit.document_id, hit)
            contribution = 1.0 / (rank_constant + rank)
            scores[hit.document_id] = scores.get(hit.document_id, 0.0) + contribution
            components[f"{hit.score.source}:{hit.document_id}"] = contribution

    ranked_document_ids = sorted(scores, key=lambda document_id: (-scores[document_id], document_id))
    fused: list[RetrievalHit] = []
    for final_rank, document_id in enumerate(ranked_document_ids[:top_k], start=1):
        hit = by_document[document_id]
        fused.append(
            RetrievalHit(
                document_id=hit.document_id,
                passage_id=hit.passage_id,
                document=hit.document,
                passage=hit.passage,
                score=RetrievalScore(
                    source="rrf",
                    value=scores[document_id],
                    components={
                        key: value
                        for key, value in components.items()
                        if key.endswith(f":{document_id}")
                    },
                ),
                trace=RetrievalTrace(
                    retriever="rrf",
                    original_rank=hit.trace.original_rank,
                    post_filter_rank=hit.trace.post_filter_rank,
                    final_rank=final_rank,
                ),
            )
        )
    return fused
