from __future__ import annotations

import unittest

from src.vyu.retrieval.evaluation_runner import (
    EvaluationThresholds,
    evaluate_index_for_activation,
    evaluate_retrieval_metrics,
)
from src.vyu.retrieval.rrf import reciprocal_rank_fusion_by_passage


class _Candidate:
    def __init__(
        self,
        *,
        passage_id: str,
        document_id: str,
        document_chunk_id: object,
        document_title: str | None,
        source_id: str,
        text: str,
        score: float,
        score_source: str,
        original_rank: int,
    ) -> None:
        self.passage_id = passage_id
        self.document_id = document_id
        self.document_chunk_id = document_chunk_id
        self.document_title = document_title
        self.source_id = source_id
        self.text = text
        self.score = score
        self.score_source = score_source
        self.original_rank = original_rank


class RetrievalEvaluationRunnerTests(unittest.TestCase):
    def test_evaluate_index_for_activation_passes_with_chunks(self) -> None:
        result = evaluate_index_for_activation(
            suite="retrieval_synthetic_v1",
            chunk_count=3,
            document_count=1,
        )
        self.assertTrue(result.passed)

    def test_evaluate_index_for_activation_fails_without_chunks(self) -> None:
        result = evaluate_index_for_activation(
            suite="retrieval_synthetic_v1",
            chunk_count=0,
            document_count=0,
        )
        self.assertFalse(result.passed)

    def test_evaluate_retrieval_metrics_respects_thresholds(self) -> None:
        result = evaluate_retrieval_metrics(
            {"recall_at_5": 0.5, "mrr_at_10": 0.5, "ndcg_at_10": 0.5},
            thresholds=EvaluationThresholds(recall_at_5=0.4, mrr_at_10=0.4, ndcg_at_10=0.4),
        )
        self.assertTrue(result.passed)


class RrfByPassageTests(unittest.TestCase):
    def test_reciprocal_rank_fusion_by_passage_deduplicates_chunks(self) -> None:
        first = [
            _Candidate(
                passage_id="chunk-a",
                document_id="doc-1",
                document_chunk_id="a",
                document_title=None,
                source_id="pubmed",
                text="a",
                score=1.0,
                score_source="lexical",
                original_rank=1,
            )
        ]
        second = [
            _Candidate(
                passage_id="chunk-a",
                document_id="doc-1",
                document_chunk_id="a",
                document_title=None,
                source_id="pubmed",
                text="a",
                score=0.9,
                score_source="vector",
                original_rank=1,
            ),
            _Candidate(
                passage_id="chunk-b",
                document_id="doc-2",
                document_chunk_id="b",
                document_title=None,
                source_id="pubmed",
                text="b",
                score=0.8,
                score_source="vector",
                original_rank=2,
            ),
        ]
        fused = reciprocal_rank_fusion_by_passage([first, second], top_k=2, rank_constant=60)
        self.assertEqual(["chunk-a", "chunk-b"], [item.passage_id for item in fused])


if __name__ == "__main__":
    unittest.main()
