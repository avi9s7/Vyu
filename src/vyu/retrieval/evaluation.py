from __future__ import annotations

import math
from typing import Protocol

from src.vyu.contracts import LoadedCorpus
from src.vyu.retrieval.contracts import RetrievalHit, RetrievalQuery


class Retriever(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        ...


def evaluate_golden_questions(
    corpus: LoadedCorpus,
    retriever: Retriever,
    top_k: int = 10,
) -> dict[str, float]:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []

    for question in corpus.golden_questions.values():
        expected = corpus.expected_documents.get(question.question_id, [])
        if not expected:
            continue
        hits = retriever.search(RetrievalQuery(text=question.question, top_k=top_k))
        ranked_document_ids = [hit.document_id for hit in hits[:top_k]]
        recalls.append(_recall_at_k(ranked_document_ids, expected))
        reciprocal_ranks.append(_mrr_at_k(ranked_document_ids, expected))
        ndcgs.append(_ndcg_at_k(ranked_document_ids, expected))

    return {
        f"recall_at_{top_k}": _mean(recalls),
        f"mrr_at_{top_k}": _mean(reciprocal_ranks),
        f"ndcg_at_{top_k}": _mean(ndcgs),
        "question_count": float(len(recalls)),
    }


def _recall_at_k(ranked: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    return len(expected_set.intersection(ranked)) / len(expected_set)


def _mrr_at_k(ranked: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    for rank, document_id in enumerate(ranked, start=1):
        if document_id in expected_set:
            return 1.0 / rank
    return 0.0


def _ndcg_at_k(ranked: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    dcg = 0.0
    for rank, document_id in enumerate(ranked, start=1):
        if document_id in expected_set:
            dcg += 1.0 / math.log2(rank + 1)
    ideal_count = min(len(expected_set), len(ranked))
    if ideal_count == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / idcg if idcg else 0.0


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
