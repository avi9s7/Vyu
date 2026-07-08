from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from src.vyu.synthesis.adjudication import (
    load_adjudication_votes,
    promotion_binding,
    summarize_adjudication,
)
from src.vyu.synthesis.evaluation_contracts import SynthesisEvaluationSubject
from src.vyu.synthesis.evaluation_dataset import PILOT_ADJUDICATION_DATASET_VERSION
from src.vyu.synthesis.evaluation_runner import (
    compare_subject_to_baseline,
    run_synthetic_synthesis_evaluation,
)


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run locked synthesis evaluation.")
    parser.add_argument(
        "--suite",
        default="synthesis_synthetic_v1",
        help="Evaluation suite identifier.",
    )
    parser.add_argument(
        "--provider-id",
        default="deterministic",
        help="Provider under evaluation.",
    )
    parser.add_argument(
        "--model-id",
        default="vyu-deterministic-v1",
        help="Model snapshot under evaluation.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the evaluation report JSON.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare candidate subject against deterministic baseline.",
    )
    parser.add_argument(
        "--adjudication",
        type=Path,
        default=Path("data/synthesis_evaluation/pilot_adjudication_v1.jsonl"),
        help="Pilot adjudication votes JSONL.",
    )
    parser.add_argument(
        "--skip-adjudication",
        action="store_true",
        help="Do not require pilot adjudication agreement for release_gate_passed.",
    )
    args = parser.parse_args()

    git_sha = _git_sha()
    baseline = SynthesisEvaluationSubject.deterministic_baseline(git_sha=git_sha)
    candidate = SynthesisEvaluationSubject(
        provider_id=args.provider_id,
        model_id=args.model_id,
        prompt_version=baseline.prompt_version,
        schema_version=baseline.schema_version,
        embedding_model=baseline.embedding_model,
        index_manifest_checksum=baseline.index_manifest_checksum,
        policy_version=baseline.policy_version,
        git_sha=git_sha,
        image_digest=None,
    )

    evaluation = run_synthetic_synthesis_evaluation(suite=args.suite, subject=candidate)
    adjudication = summarize_adjudication(
        load_adjudication_votes(args.adjudication),
        dataset_version=PILOT_ADJUDICATION_DATASET_VERSION,
    )

    report: dict[str, object] = {
        "evaluation": evaluation.to_json(),
        "adjudication": adjudication.to_json(),
        "promotion_binding": promotion_binding(candidate, evaluation),
        "release_gate_passed": evaluation.passed,
    }
    if not args.skip_adjudication:
        report["release_gate_passed"] = evaluation.passed and adjudication.passed

    if args.compare_baseline and candidate.label() != baseline.label():
        comparison = compare_subject_to_baseline(
            baseline=baseline,
            candidate=candidate,
            suite=args.suite,
        )
        report["comparison"] = comparison.to_json()
        if not comparison.promote:
            report["release_gate_passed"] = False

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Wrote synthesis evaluation report to {args.output}")
    else:
        print(payload)

    return 0 if report["release_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
