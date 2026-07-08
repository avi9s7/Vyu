from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SynthesisEvaluationSubject:
    provider_id: str
    model_id: str
    prompt_version: str
    schema_version: str
    embedding_model: str
    index_manifest_checksum: str
    policy_version: str
    git_sha: str
    image_digest: str | None = None

    def label(self) -> str:
        return (
            f"{self.provider_id}/{self.model_id}/"
            f"{self.prompt_version}/{self.schema_version}/"
            f"{self.index_manifest_checksum[:12]}"
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "embedding_model": self.embedding_model,
            "index_manifest_checksum": self.index_manifest_checksum,
            "policy_version": self.policy_version,
            "git_sha": self.git_sha,
            "image_digest": self.image_digest,
        }

    @classmethod
    def deterministic_baseline(cls, *, git_sha: str = "local") -> "SynthesisEvaluationSubject":
        return cls(
            provider_id="deterministic",
            model_id="vyu-deterministic-v1",
            prompt_version="grounded_answer_v1",
            schema_version="grounded_answer_v1",
            embedding_model="text-embedding-3-large",
            index_manifest_checksum="deterministic-baseline",
            policy_version="1",
            git_sha=git_sha,
            image_digest=None,
        )


@dataclass(frozen=True)
class SynthesisCaseResult:
    case_id: str
    category: str
    critical: bool
    passed: bool
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "critical": self.critical,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SynthesisEvaluationResult:
    suite: str
    subject: str
    passed: bool
    metrics: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    case_results: tuple[SynthesisCaseResult, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "subject": self.subject,
            "passed": self.passed,
            "metrics": dict(self.metrics),
            "details": dict(self.details),
            "case_results": [case.to_json() for case in self.case_results],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "SynthesisEvaluationResult":
        return cls(
            suite=str(payload["suite"]),
            subject=str(payload["subject"]),
            passed=bool(payload["passed"]),
            metrics={
                str(key): float(value) for key, value in dict(payload.get("metrics", {})).items()
            },
            details=dict(payload.get("details", {})),
            case_results=tuple(
                SynthesisCaseResult(
                    case_id=str(case["case_id"]),
                    category=str(case["category"]),
                    critical=bool(case["critical"]),
                    passed=bool(case["passed"]),
                    detail=str(case["detail"]),
                )
                for case in payload.get("case_results", [])
            ),
        )


@dataclass(frozen=True)
class SynthesisComparisonResult:
    baseline_subject: str
    candidate_subject: str
    promote: bool
    rationale: str
    critical_regressions: tuple[str, ...] = ()
    metric_regressions: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "baseline_subject": self.baseline_subject,
            "candidate_subject": self.candidate_subject,
            "promote": self.promote,
            "rationale": self.rationale,
            "critical_regressions": list(self.critical_regressions),
            "metric_regressions": list(self.metric_regressions),
        }
