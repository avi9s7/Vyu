from __future__ import annotations

from src.vyu.synthesis.adjudication import load_adjudication_votes, summarize_adjudication
from src.vyu.synthesis.evaluation_contracts import SynthesisEvaluationSubject
from src.vyu.synthesis.evaluation_dataset import PILOT_ADJUDICATION_DATASET_VERSION
from src.vyu.synthesis.evaluation_runner import evaluate_synthesis_for_activation
from src.vyu.synthesis.staging_fixtures import OPERATIONAL_FAILURE_SCENARIOS, PLAN7_STAGING_CHECKLIST


def test_plan7_staging_validation_contracts() -> None:
    evaluation = evaluate_synthesis_for_activation(
        suite="synthesis_synthetic_v1",
        subject=SynthesisEvaluationSubject.deterministic_baseline(git_sha="test"),
    )
    assert evaluation.passed
    assert evaluation.metrics["critical_safety_pass_rate"] == 1.0
    assert len(PLAN7_STAGING_CHECKLIST) >= 8
    assert any(item["name"] == "audit_persist_failed" for item in OPERATIONAL_FAILURE_SCENARIOS)


def test_plan7_pilot_adjudication_fixture_is_loadable() -> None:
    votes = load_adjudication_votes("data/synthesis_evaluation/pilot_adjudication_v1.jsonl")
    summary = summarize_adjudication(
        votes,
        dataset_version=PILOT_ADJUDICATION_DATASET_VERSION,
    )
    assert summary.reviewer_count == 2
    assert summary.case_count == 3
