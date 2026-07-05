from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.entrypoints import (
    ReportExportApiRequest,
    ReportExportPayload,
    handle_report_export_api,
)
from src.vyu.generation import AnswerClaim, EvidenceContext, EvidenceItem, GroundedAnswer
from src.vyu.governance import GovernanceBox, TrustScore
from src.vyu.reports import ReportType
from src.vyu.storage import ProductionStorage


def export_report_from_store(
    sqlite_db: Path,
    output_dir: Path,
    review_id: str,
    user_id: str,
    role: Role,
    report_type: ReportType,
    report_output: Path | None = None,
    exported_at: str | None = None,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    review_task = storage.get_review_task(review_id)
    answer = _load_answer(output_dir / "phase4" / "grounded_answer.json")
    context = _load_context(output_dir / "phase4" / "evidence_context.json")
    governance_payload = _read_json(output_dir / "phase5" / "governance_audit_record.json")
    trust_score = _load_trust_score(dict(governance_payload["trust_score"]))
    governance_box = _load_governance_box(
        dict(governance_payload["governance_box"]),
        trust_score,
    )
    principal = Principal(
        user_id=user_id,
        memberships=(
            WorkspaceMembership(
                tenant_id=review_task.scope.tenant_id,
                workspace_id=review_task.scope.workspace_id,
                roles=(role,),
            ),
        ),
    )
    response = handle_report_export_api(
        ReportExportApiRequest(
            request_id="export-report-from-store",
            payload=ReportExportPayload(
                principal=principal,
                report_type=report_type,
                answer=answer,
                context=context,
                trust_score=trust_score,
                governance_box=governance_box,
                review_task=review_task,
            ),
        ),
        storage=storage,
        audit_event_id_factory=_audit_event_id,
        audit_created_at=exported_at,
    )
    body = {"status_code": response.status_code, **response.body}
    export_payload = dict(body["export"])
    if response.status_code == 200 and report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(str(export_payload["content"]), encoding="utf-8")
        body["report_output"] = str(report_output)
    else:
        body["report_output"] = None
    return body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a Vyu report from persisted phase artifacts and review storage."
    )
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", choices=[role.value for role in Role], required=True)
    parser.add_argument("--report-type", choices=[report_type.value for report_type in ReportType], required=True)
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--exported-at")
    args = parser.parse_args()

    payload = export_report_from_store(
        sqlite_db=args.sqlite_db,
        output_dir=args.output_dir,
        review_id=args.review_id,
        user_id=args.user_id,
        role=Role(args.role),
        report_type=ReportType(args.report_type),
        report_output=args.report_output,
        exported_at=args.exported_at,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status_code"] == 200 else 1


def _load_answer(path: Path) -> GroundedAnswer:
    payload = _read_json(path)
    return GroundedAnswer(
        question=str(payload["question"]),
        answer_text=str(payload["answer_text"]),
        claims=[
            AnswerClaim(
                claim_id=str(claim["claim_id"]),
                text=str(claim["text"]),
                citation_ids=[str(citation_id) for citation_id in claim["citation_ids"]],
                material=bool(claim.get("material", True)),
            )
            for claim in payload["claims"]
        ],
        abstained=bool(payload["abstained"]),
        abstention_reason=(
            str(payload["abstention_reason"])
            if payload.get("abstention_reason") is not None
            else None
        ),
    )


def _load_context(path: Path) -> EvidenceContext:
    payload = _read_json(path)
    return EvidenceContext(
        question=str(payload["question"]),
        items=[
            EvidenceItem(
                citation_id=str(item["citation_id"]),
                document_id=str(item["document_id"]),
                passage_id=str(item["passage_id"]),
                title=str(item["title"]),
                passage_text=str(item["passage_text"]),
                retrieval_score=float(item["retrieval_score"]),
                retrieval_source=str(item["retrieval_source"]),
                is_retracted=bool(item["is_retracted"]),
                is_preprint=bool(item["is_preprint"]),
            )
            for item in payload["items"]
        ],
    )


def _load_trust_score(payload: dict[str, object]) -> TrustScore:
    return TrustScore(
        overall=int(payload["overall"]),
        components={key: int(value) for key, value in dict(payload["components"]).items()},
        warnings=[str(warning) for warning in payload["warnings"]],
    )


def _load_governance_box(payload: dict[str, object], trust_score: TrustScore) -> GovernanceBox:
    return GovernanceBox(
        question=str(payload["question"]),
        sources_searched=[str(source) for source in payload["sources_searched"]],
        search_run_at=str(payload["search_run_at"]),
        retrieved_count=int(payload["retrieved_count"]),
        included_count=int(payload["included_count"]),
        excluded_count=int(payload["excluded_count"]),
        evidence_mix={key: int(value) for key, value in dict(payload["evidence_mix"]).items()},
        conflicts=[str(conflict) for conflict in payload["conflicts"]],
        models={key: str(value) for key, value in dict(payload["models"]).items()},
        policy_versions={
            key: str(value) for key, value in dict(payload["policy_versions"]).items()
        },
        human_review_required=bool(payload["human_review_required"]),
        human_review_reason=str(payload["human_review_reason"]),
        trust_score=trust_score,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_event_id(run_id: str, event_type: str) -> str:
    return f"{run_id}-{event_type}-{uuid.uuid4().hex}"


if __name__ == "__main__":
    raise SystemExit(main())
