from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.storage import ProductionScope, ProductionStorage


def summarize_production_observability(
    sqlite_db: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    scope = ProductionScope(tenant_id=tenant_id, workspace_id=workspace_id)
    manifest = storage.get_artifact_manifest_for_scope(run_id, scope)
    review_tasks = storage.list_review_tasks_for_scope(scope, run_id=run_id)
    health_records = storage.list_connector_health_records_for_scope(
        scope,
        run_id=run_id,
    )
    validation_records = storage.list_staged_connector_validation_records_for_scope(
        scope,
        run_id=run_id,
    )
    readiness_results = storage.list_readiness_check_results_for_scope(
        scope,
        run_id=run_id,
    )
    evidence_objects = storage.list_evidence_object_records_for_scope(scope)
    retrieval_indexes = storage.list_retrieval_index_records_for_scope(scope)
    retrieval_runs = storage.list_retrieval_run_records_for_scope(scope, run_id=run_id)
    research_memory = storage.list_production_research_memory_records_for_scope(
        scope,
        run_id=run_id,
    )
    methodology_runs = storage.list_evidence_methodology_run_records_for_scope(
        scope,
        run_id=run_id,
    )
    methodology_assessments = (
        storage.list_evidence_methodology_assessment_records_for_scope(
            scope,
            run_id=run_id,
        )
    )
    reviewer_ratings = storage.list_reviewer_evidence_rating_records_for_scope(
        scope,
        run_id=run_id,
    )
    external_requests = storage.list_external_evidence_grading_request_records_for_scope(
        scope,
        run_id=run_id,
    )
    external_responses = storage.list_external_evidence_grading_response_records_for_scope(
        scope,
        run_id=run_id,
    )
    production_trust_scores = storage.list_production_trust_score_records_for_scope(
        scope,
        run_id=run_id,
    )
    production_governance_boxes = storage.list_production_governance_box_records_for_scope(
        scope,
        run_id=run_id,
    )
    reviewer_trust_score_overrides = storage.list_reviewer_trust_score_override_records_for_scope(
        scope,
        run_id=run_id,
    )
    external_governance_requests = storage.list_external_governance_request_records_for_scope(
        scope,
        run_id=run_id,
    )
    external_governance_responses = storage.list_external_governance_response_records_for_scope(
        scope,
        run_id=run_id,
    )
    audit_events = storage.list_audit_events_for_scope(scope, run_id=run_id)

    readiness = _readiness_summary(readiness_results)
    review = _review_summary(review_tasks)
    report_export = _report_export_summary(audit_events)
    attention_reasons = _attention_reasons(
        readiness=readiness,
        review=review,
        report_export=report_export,
    )

    return {
        "status": "attention" if attention_reasons else "ok",
        "attention_reasons": attention_reasons,
        "run_id": manifest.run_id,
        "tenant_id": manifest.tenant_id,
        "workspace_id": manifest.workspace_id,
        "environment": manifest.environment,
        "readiness": readiness,
        "review": review,
        "connectors": {
            "health_record_count": len(health_records),
            "health_status_counts": _status_counts(
                record.status.value for record in health_records
            ),
            "validation_record_count": len(validation_records),
            "validation_status_counts": _status_counts(
                record.status.value for record in validation_records
            ),
            "health_sources": sorted({record.source_id for record in health_records}),
            "validation_sources": sorted(
                {record.source_id for record in validation_records}
            ),
        },
        "evidence_memory_retrieval": {
            "evidence_object_count": len(evidence_objects),
            "retrieval_index_count": len(retrieval_indexes),
            "retrieval_run_count": len(retrieval_runs),
            "research_memory_count": len(research_memory),
            "index_versions": sorted({record.index_version for record in retrieval_indexes}),
            "retrieval_modes": sorted({record.retrieval_mode for record in retrieval_runs}),
            "topics": sorted({record.topic for record in research_memory}),
        },
        "evidence_grading_methodology": {
            "methodology_run_count": len(methodology_runs),
            "assessment_count": len(methodology_assessments),
            "reviewer_rating_count": len(reviewer_ratings),
            "external_request_count": len(external_requests),
            "external_response_count": len(external_responses),
            "strength_band_counts": _status_counts(
                record.evidence_strength_band.value for record in methodology_assessments
            ),
            "assessment_source_counts": _status_counts(
                record.assessment_source for record in methodology_assessments
            ),
            "external_provider_ids": sorted({record.provider_id for record in external_requests}),
            "human_review_required_count": sum(
                1 for record in methodology_assessments if record.requires_human_review
            ),
        },
        "governance_box_trust_score": {
            "trust_score_count": len(production_trust_scores),
            "governance_box_count": len(production_governance_boxes),
            "reviewer_override_count": len(reviewer_trust_score_overrides),
            "external_request_count": len(external_governance_requests),
            "external_response_count": len(external_governance_responses),
            "decision_status_counts": _status_counts(
                record.decision_status.value for record in production_trust_scores
            ),
            "export_status_counts": _status_counts(
                record.export_status.value for record in production_governance_boxes
            ),
            "external_provider_ids": sorted(
                {record.provider_id for record in external_governance_requests}
            ),
            "trust_score_overall_values": [
                record.overall for record in production_trust_scores
            ],
        },
        "report_export": report_export,
        "audit_events": {
            "total_count": len(audit_events),
            "event_type_counts": _status_counts(
                event.event_type for event in audit_events
            ),
        },
    }


def _readiness_summary(readiness_results: list[Any]) -> dict[str, Any]:
    latest = readiness_results[-1] if readiness_results else None
    return {
        "result_count": len(readiness_results),
        "latest_status": latest.status if latest is not None else None,
        "latest_result_id": latest.result_id if latest is not None else None,
        "latest_failed_checks": list(latest.failed_checks)
        if latest is not None
        else [],
    }


def _review_summary(review_tasks: list[Any]) -> dict[str, Any]:
    status_counts = _status_counts(task.status.value for task in review_tasks)
    return {
        "task_count": len(review_tasks),
        "status_counts": status_counts,
        "approved_count": status_counts.get("approved", 0),
        "pending_count": status_counts.get("pending", 0),
        "rejected_count": status_counts.get("rejected", 0),
    }


def _report_export_summary(audit_events: list[Any]) -> dict[str, Any]:
    export_events = [
        event
        for event in audit_events
        if event.event_type == "report_export_decision_recorded"
    ]
    allowed_events = [
        event for event in export_events if event.payload.get("allowed") is True
    ]
    latest = export_events[-1] if export_events else None
    return {
        "attempt_count": len(export_events),
        "allowed_count": len(allowed_events),
        "blocked_count": len(export_events) - len(allowed_events),
        "latest_reason": latest.payload.get("reason") if latest is not None else None,
        "latest_allowed": latest.payload.get("allowed") if latest is not None else None,
    }


def _attention_reasons(
    readiness: dict[str, Any],
    review: dict[str, Any],
    report_export: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if readiness["result_count"] == 0:
        reasons.append("readiness_missing")
    elif readiness["latest_status"] != "pass":
        reasons.append("readiness_not_passing")
    if review["pending_count"]:
        reasons.append("review_pending")
    if review["rejected_count"]:
        reasons.append("review_rejected")
    if review["approved_count"] == 0:
        reasons.append("review_approval_missing")
    if report_export["allowed_count"] == 0:
        reasons.append("allowed_report_export_missing")
    return reasons


def _status_counts(values) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Vyu production observability records for one scoped run."
    )
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    try:
        payload = summarize_production_observability(
            sqlite_db=args.sqlite_db,
            run_id=args.run_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
        )
    except (KeyError, PermissionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
