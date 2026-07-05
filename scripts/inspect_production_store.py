from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.storage import ProductionScope, ProductionStorage


def inspect_production_store(
    sqlite_db: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    scope = ProductionScope(tenant_id=tenant_id, workspace_id=workspace_id)
    manifest = storage.get_artifact_manifest_for_scope(run_id, scope)
    evaluation_runs = storage.list_evaluation_runs()
    audit_events = storage.list_audit_events_for_scope(scope, run_id=run_id)
    review_tasks = storage.list_review_tasks_for_scope(scope, run_id=run_id)
    connector_health_records = storage.list_connector_health_records_for_scope(
        scope,
        run_id=run_id,
    )
    connector_validation_records = (
        storage.list_staged_connector_validation_records_for_scope(
            scope,
            run_id=run_id,
        )
    )
    privacy_approval_records = storage.list_privacy_approval_records_for_scope(
        scope,
        run_id=run_id,
    )
    readiness_check_results = storage.list_readiness_check_results_for_scope(
        scope,
        run_id=run_id,
    )
    evidence_object_records = storage.list_evidence_object_records_for_scope(scope)
    retrieval_index_records = storage.list_retrieval_index_records_for_scope(scope)
    retrieval_run_records = storage.list_retrieval_run_records_for_scope(
        scope,
        run_id=run_id,
    )
    production_research_memory_records = (
        storage.list_production_research_memory_records_for_scope(
            scope,
            run_id=run_id,
        )
    )
    evidence_methodology_runs = storage.list_evidence_methodology_run_records_for_scope(
        scope,
        run_id=run_id,
    )
    evidence_methodology_assessments = (
        storage.list_evidence_methodology_assessment_records_for_scope(
            scope,
            run_id=run_id,
        )
    )
    reviewer_evidence_ratings = storage.list_reviewer_evidence_rating_records_for_scope(
        scope,
        run_id=run_id,
    )
    external_grading_requests = (
        storage.list_external_evidence_grading_request_records_for_scope(
            scope,
            run_id=run_id,
        )
    )
    external_grading_responses = (
        storage.list_external_evidence_grading_response_records_for_scope(
            scope,
            run_id=run_id,
        )
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
    return {
        "artifact_manifest": manifest.to_json(),
        "evaluation_runs": [
            run.to_json()
            for run in evaluation_runs
            if run.artifact_manifest_path == "outputs/artifact_manifest.json"
        ],
        "review_tasks": [task.to_json() for task in review_tasks],
        "connector_health_records": [
            record.to_json() for record in connector_health_records
        ],
        "connector_validation_records": [
            record.to_json() for record in connector_validation_records
        ],
        "privacy_approval_records": [
            record.to_json() for record in privacy_approval_records
        ],
        "readiness_check_results": [
            record.to_json() for record in readiness_check_results
        ],
        "evidence_object_records": [
            record.to_json() for record in evidence_object_records
        ],
        "retrieval_index_records": [
            record.to_json() for record in retrieval_index_records
        ],
        "retrieval_run_records": [
            record.to_json() for record in retrieval_run_records
        ],
        "production_research_memory_records": [
            record.to_json() for record in production_research_memory_records
        ],
        "evidence_methodology_run_records": [
            record.to_json() for record in evidence_methodology_runs
        ],
        "evidence_methodology_assessment_records": [
            record.to_json() for record in evidence_methodology_assessments
        ],
        "reviewer_evidence_rating_records": [
            record.to_json() for record in reviewer_evidence_ratings
        ],
        "external_evidence_grading_request_records": [
            record.to_json() for record in external_grading_requests
        ],
        "external_evidence_grading_response_records": [
            record.to_json() for record in external_grading_responses
        ],
        "production_trust_score_records": [
            record.to_json() for record in production_trust_scores
        ],
        "production_governance_box_records": [
            record.to_json() for record in production_governance_boxes
        ],
        "reviewer_trust_score_override_records": [
            record.to_json() for record in reviewer_trust_score_overrides
        ],
        "external_governance_request_records": [
            record.to_json() for record in external_governance_requests
        ],
        "external_governance_response_records": [
            record.to_json() for record in external_governance_responses
        ],
        "audit_events": [event.to_json() for event in audit_events],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Vyu production SQLite store.")
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    try:
        payload = inspect_production_store(
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
