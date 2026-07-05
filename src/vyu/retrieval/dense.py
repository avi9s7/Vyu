from __future__ import annotations

import math
from collections import Counter

from src.vyu.contracts import LoadedCorpus
from src.vyu.retrieval.bm25 import _tokenize
from src.vyu.retrieval.contracts import (
    RetrievalHit,
    RetrievalQuery,
    RetrievalScore,
    RetrievalTrace,
)


class DenseKeywordRetriever:
    source = "dense_keyword"

    def __init__(self, corpus: LoadedCorpus):
        self.corpus = corpus
        self._vectors = {
            passage_id: Counter(_tokenize(passage.text))
            for passage_id, passage in corpus.passages.items()
        }

    @classmethod
    def from_corpus(cls, corpus: LoadedCorpus) -> "DenseKeywordRetriever":
        return cls(corpus)

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        query_vector = Counter(_tokenize(query.text))
        scored_passages: list[tuple[str, float]] = []
        for passage_id, vector in self._vectors.items():
            score = _cosine(query_vector, vector)
            if score > 0:
                scored_passages.append((passage_id, score))
        scored_passages.sort(key=lambda item: (-item[1], item[0]))

        best_by_document: dict[str, tuple[str, float, int]] = {}
        for original_rank, (passage_id, score) in enumerate(scored_passages, start=1):
            passage = self.corpus.passages[passage_id]
            document = self.corpus.documents[passage.document_id]
            if query.metadata_filter is not None and not query.metadata_filter.matches(document):
                continue
            existing = best_by_document.get(document.document_id)
            if existing is None or score > existing[1]:
                best_by_document[document.document_id] = (passage_id, score, original_rank)

        ranked_documents = sorted(
            best_by_document.items(),
            key=lambda item: (-item[1][1], item[0]),
        )
        hits: list[RetrievalHit] = []
        for final_rank, (document_id, (passage_id, score, original_rank)) in enumerate(
            ranked_documents[: query.top_k], start=1
        ):
            hits.append(
                RetrievalHit(
                    document_id=document_id,
                    passage_id=passage_id,
                    document=self.corpus.documents[document_id],
                    passage=self.corpus.passages[passage_id],
                    score=RetrievalScore(
                        source=self.source,
                        value=score,
                        components={"cosine": score},
                    ),
                    trace=RetrievalTrace(
                        retriever=self.source,
                        original_rank=original_rank,
                        post_filter_rank=final_rank,
                        final_rank=final_rank,
                    ),
                )
            )
        return hits


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[term] * right.get(term, 0) for term in left)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
