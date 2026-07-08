from __future__ import annotations

import unittest
from pathlib import Path

from src.vyu.synthesis.adjudication import (
    load_adjudication_votes,
    summarize_adjudication,
)
from src.vyu.synthesis.evaluation_contracts import SynthesisEvaluationSubject
from src.vyu.synthesis.evaluation_dataset import (
    PILOT_ADJUDICATION_DATASET_VERSION,
    SYNTHETIC_EVALUATION_CASES,
)
from src.vyu.synthesis.evaluation_runner import (
    SynthesisEvaluationThresholds,
    compare_subject_to_baseline,
    evaluate_synthesis_case,
    evaluate_synthesis_for_activation,
    run_synthetic_synthesis_evaluation,
)


class SynthesisEvaluationRunnerTests(unittest.TestCase):
    def test_evaluate_synthesis_for_activation_passes_deterministic_baseline(self) -> None:
        subject = SynthesisEvaluationSubject.deterministic_baseline(git_sha="test")
        result = evaluate_synthesis_for_activation(
            suite="synthesis_synthetic_v1",
            subject=subject,
        )
        self.assertTrue(result.passed)
        self.assertEqual(1.0, result.metrics["critical_safety_pass_rate"])
        self.assertEqual(len(SYNTHETIC_EVALUATION_CASES), len(result.case_results))

    def test_critical_safety_failure_blocks_activation(self) -> None:
        case = next(
            case
            for case in SYNTHETIC_EVALUATION_CASES
            if case.case_id == "unknown_citation_blocked"
        )
        broken = case.__class__(
            case_id=case.case_id,
            category=case.category,
            critical=case.critical,
            context=case.context,
            output_payload=case.output_payload,
            expect_valid=True,
            required_abstention=case.required_abstention,
            expected_error_substrings=case.expected_error_substrings,
            requires_contradiction_disclosure=case.requires_contradiction_disclosure,
        )
        result = run_synthetic_synthesis_evaluation(
            suite="synthesis_synthetic_v1",
            subject=SynthesisEvaluationSubject.deterministic_baseline(git_sha="test"),
            cases=(broken,),
        )
        self.assertFalse(result.passed)

    def test_compare_subject_to_baseline_promotes_matching_candidate(self) -> None:
        baseline = SynthesisEvaluationSubject.deterministic_baseline(git_sha="test")
        candidate = SynthesisEvaluationSubject(
            provider_id="openai",
            model_id="gpt-test",
            prompt_version=baseline.prompt_version,
            schema_version=baseline.schema_version,
            embedding_model=baseline.embedding_model,
            index_manifest_checksum=baseline.index_manifest_checksum,
            policy_version=baseline.policy_version,
            git_sha="test",
        )
        comparison = compare_subject_to_baseline(
            baseline=baseline,
            candidate=candidate,
            suite="synthesis_synthetic_v1",
        )
        self.assertTrue(comparison.promote)

    def test_evaluate_synthesis_case_reports_unknown_citation_failure(self) -> None:
        case = next(
            case
            for case in SYNTHETIC_EVALUATION_CASES
            if case.case_id == "unknown_citation_blocked"
        )
        result = evaluate_synthesis_case(case)
        self.assertTrue(result.passed)
        self.assertTrue(result.critical)

    def test_thresholds_can_fail_aggregate_gate(self) -> None:
        subject = SynthesisEvaluationSubject.deterministic_baseline(git_sha="test")
        result = run_synthetic_synthesis_evaluation(
            suite="synthesis_synthetic_v1",
            subject=subject,
            thresholds=SynthesisEvaluationThresholds(case_pass_rate=1.1),
        )
        self.assertFalse(result.passed)


class SynthesisAdjudicationTests(unittest.TestCase):
    def test_pilot_adjudication_detects_disagreement(self) -> None:
        votes = load_adjudication_votes(
            Path("data/synthesis_evaluation/pilot_adjudication_v1.jsonl")
        )
        summary = summarize_adjudication(
            votes,
            dataset_version=PILOT_ADJUDICATION_DATASET_VERSION,
        )
        self.assertEqual(3, summary.case_count)
        self.assertIn("pilot_003", summary.unresolved_cases)
        self.assertFalse(summary.passed)


if __name__ == "__main__":
    unittest.main()
