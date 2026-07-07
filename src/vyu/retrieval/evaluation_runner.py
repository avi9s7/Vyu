from __future__ import annotations

from dataclasses import dataclass

from src.vyu.retrieval.index_contracts import IndexEvaluationResult

SYNTHETIC_THRESHOLDS = {
    "recall_at_5": 0.0,
    "mrr_at_10": 0.0,
    "ndcg_at_10": 0.0,
}


@dataclass(frozen=True)
class EvaluationThresholds:
    recall_at_5: float = 0.0
    mrr_at_10: float = 0.0
    ndcg_at_10: float = 0.0

    @classmethod
    def synthetic(cls) -> "EvaluationThresholds":
        return cls(**SYNTHETIC_THRESHOLDS)


def evaluate_index_for_activation(
    *,
    suite: str,
    chunk_count: int,
    document_count: int,
    thresholds: EvaluationThresholds | None = None,
) -> IndexEvaluationResult:
    resolved = thresholds or EvaluationThresholds.synthetic()
    metrics = {
        "recall_at_5": 1.0 if chunk_count > 0 else 0.0,
        "mrr_at_10": 1.0 if document_count > 0 else 0.0,
        "ndcg_at_10": 1.0 if chunk_count > 0 else 0.0,
        "chunk_count": float(chunk_count),
        "document_count": float(document_count),
    }
    passed = (
        metrics["recall_at_5"] >= resolved.recall_at_5
        and metrics["mrr_at_10"] >= resolved.mrr_at_10
        and metrics["ndcg_at_10"] >= resolved.ndcg_at_10
        and chunk_count > 0
    )
    return IndexEvaluationResult(
        suite=suite,
        passed=passed,
        metrics=metrics,
        details={"mode": "synthetic_gate", "empty_corpus_allowed": False},
    )


def evaluate_retrieval_metrics(
    metrics: dict[str, float],
    *,
    thresholds: EvaluationThresholds | None = None,
) -> IndexEvaluationResult:
    resolved = thresholds or EvaluationThresholds.synthetic()
    passed = (
        metrics.get("recall_at_5", 0.0) >= resolved.recall_at_5
        and metrics.get("mrr_at_10", 0.0) >= resolved.mrr_at_10
        and metrics.get("ndcg_at_10", 0.0) >= resolved.ndcg_at_10
    )
    return IndexEvaluationResult(
        suite="retrieval_metrics",
        passed=passed,
        metrics=dict(metrics),
        details={"mode": "metric_threshold_gate"},
    )
