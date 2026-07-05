from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    suite: str
    subject: str
    metrics: dict[str, float]
    dataset_version: str
    artifact_manifest_path: str
    created_at: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "suite": self.suite,
            "subject": self.subject,
            "metrics": dict(self.metrics),
            "dataset_version": self.dataset_version,
            "artifact_manifest_path": self.artifact_manifest_path,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "EvaluationRun":
        return cls(
            run_id=str(payload["run_id"]),
            suite=str(payload["suite"]),
            subject=str(payload["subject"]),
            metrics={key: float(value) for key, value in payload["metrics"].items()},
            dataset_version=str(payload["dataset_version"]),
            artifact_manifest_path=str(payload["artifact_manifest_path"]),
            created_at=str(payload.get("created_at", "")),
        )


class EvaluationRegistry:
    def __init__(self, path: Path):
        self.path = path

    def append(self, run: EvaluationRun) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(run.to_json(), sort_keys=True) + "\n")

    def read_all(self) -> list[EvaluationRun]:
        if not self.path.is_file():
            return []
        return [
            EvaluationRun.from_json(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
