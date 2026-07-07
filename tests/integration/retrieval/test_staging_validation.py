from __future__ import annotations

from src.vyu.retrieval.evaluation_runner import evaluate_index_for_activation
from src.vyu.retrieval.index_contracts import IndexStatus, manifest_checksum
from src.vyu.retrieval.snapshot import snapshot_ready_documents


def test_plan6_staging_validation_contracts() -> None:
    evaluation = evaluate_index_for_activation(
        suite="retrieval_synthetic_v1",
        chunk_count=2,
        document_count=1,
    )
    assert evaluation.passed
    assert IndexStatus.ACTIVE.value == "active"
    assert callable(snapshot_ready_documents)
    assert callable(manifest_checksum)
