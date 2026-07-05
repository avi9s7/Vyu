from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from src.vyu.contracts import LoadedCorpus
from src.vyu.retrieval.contracts import (
    RetrievalHit,
    RetrievalQuery,
    RetrievalScore,
    RetrievalTrace,
)

TOKEN_RE = re.compile(r"[a-z0-9]+")


class BM25Retriever:
    source = "bm25"

    def __init__(self, corpus: LoadedCorpus):
        self.corpus = corpus
        self._passage_terms = {
            passage_id: Counter(_tokenize(passage.text))
            for passage_id, passage in corpus.passages.items()
        }
        self._avgdl = _average_length(self._passage_terms)
        self._idf = _idf(self._passage_terms)

    @classmethod
    def from_corpus(cls, corpus: LoadedCorpus) -> "BM25Retriever":
        return cls(corpus)

    def search(self, query: RetrievalQuery) -> list[RetrievalHit]:
        query_terms = _tokenize(query.text)
        ranked_passages: list[tuple[str, float]] = []
        for passage_id, terms in self._passage_terms.items():
            score = _bm25_score(query_terms, terms, self._idf, self._avgdl)
            if score > 0:
                ranked_passages.append((passage_id, score))

        ranked_passages.sort(key=lambda item: (-item[1], item[0]))
        best_by_document: dict[str, tuple[str, float, int]] = {}
        for rank, (passage_id, score) in enumerate(ranked_passages, start=1):
            passage = self.corpus.passages[passage_id]
            document = self.corpus.documents[passage.document_id]
            if query.metadata_filter is not None and not query.metadata_filter.matches(document):
                continue
            existing = best_by_document.get(document.document_id)
            if existing is None or score > existing[1]:
                best_by_document[document.document_id] = (passage_id, score, rank)

        ranked_documents = sorted(
            best_by_document.items(),
            key=lambda item: (-item[1][1], item[0]),
        )
        hits: list[RetrievalHit] = []
        for final_rank, (document_id, (passage_id, score, original_rank)) in enumerate(
            ranked_documents[: query.top_k], start=1
        ):
            passage = self.corpus.passages[passage_id]
            document = self.corpus.documents[document_id]
            hits.append(
                RetrievalHit(
                    document_id=document_id,
                    passage_id=passage_id,
                    document=document,
                    passage=passage,
                    score=RetrievalScore(
                        source=self.source,
                        value=score,
                        components={"bm25": score},
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


def _tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _average_length(passage_terms: dict[str, Counter[str]]) -> float:
    if not passage_terms:
        return 0.0
    return sum(sum(terms.values()) for terms in passage_terms.values()) / len(passage_terms)


def _idf(passage_terms: dict[str, Counter[str]]) -> dict[str, float]:
    doc_count = len(passage_terms)
    document_frequency: defaultdict[str, int] = defaultdict(int)
    for terms in passage_terms.values():
        for term in terms:
            document_frequency[term] += 1
    return {
        term: math.log(1 + (doc_count - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in document_frequency.items()
    }


def _bm25_score(
    query_terms: list[str],
    passage_terms: Counter[str],
    idf: dict[str, float],
    avgdl: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if avgdl == 0:
        return 0.0
    score = 0.0
    passage_length = sum(passage_terms.values())
    for term in query_terms:
        frequency = passage_terms.get(term, 0)
        if frequency == 0:
            continue
        denominator = frequency + k1 * (1 - b + b * passage_length / avgdl)
        score += idf.get(term, 0.0) * frequency * (k1 + 1) / denominator
    return score
