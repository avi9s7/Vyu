from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.artifacts import ArtifactManifest
from src.vyu.review import ReviewStatus
from src.vyu.storage import (
    PRODUCTION_SCHEMA_VERSION,
    ProductionScope,
    ProductionStorage,
    ReadinessCheckResultRecord,
)


REQUIRED_AUDIT_EVENTS = {
    "artifact_manifest_saved",
    "evaluation_run_saved",
    "phase_outputs_completed",
}


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
        }


def check_production_readiness(
    sqlite_db: Path,
    artifact_manifest_path: Path,
    run_summary_path: Path | None,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    storage = ProductionStorage(sqlite_db)
    scope = ProductionScope(tenant_id=tenant_id, workspace_id=workspace_id)
    checks: list[ReadinessCheck] = []

    try:
        stored_manifest = storage.get_artifact_manifest_for_scope(run_id, scope)
        checks.append(_pass("scoped_manifest_access", "Manifest is readable within scope."))
    except Exception as exc:
        stored_manifest = None
        checks.append(_fail("scoped_manifest_access", str(exc)))

    try:
        schema_version = storage.get_schema_version()
        checks.append(
            _result(
                "schema_version_current",
                schema_version == PRODUCTION_SCHEMA_VERSION,
                f"Production schema version is {schema_version}."
                if schema_version == PRODUCTION_SCHEMA_VERSION
                else (
                    f"Production schema version {schema_version} does not match "
                    f"expected {PRODUCTION_SCHEMA_VERSION}."
                ),
            )
        )
    except Exception as exc:
        checks.append(_fail("schema_version_current", str(exc)))

    try:
        migrations = storage.list_migrations()
        migration_versions = {migration["version"] for migration in migrations}
        checks.append(
            _result(
                "migration_history_present",
                PRODUCTION_SCHEMA_VERSION in migration_versions,
                "Migration history includes the current production schema version."
                if PRODUCTION_SCHEMA_VERSION in migration_versions
                else (
                    "Migration history does not include the current production "
                    f"schema version {PRODUCTION_SCHEMA_VERSION}."
                ),
            )
        )
    except Exception as exc:
        checks.append(_fail("migration_history_present", str(exc)))

    file_manifest = ArtifactManifest.read(artifact_manifest_path)
    manifest = stored_manifest or file_manifest

    approved_sources = [
        source
        for source in file_manifest.sources
        if source.get("approval_status") == "approved"
        and source.get("approved_by")
        and source.get("approved_at")
    ]
    checks.append(
        _result(
            "approved_sources_present",
            len(approved_sources) == len(file_manifest.sources) and bool(approved_sources),
            "All manifest sources are approved."
            if len(approved_sources) == len(file_manifest.sources) and approved_sources
            else "Manifest must include approved source records.",
        )
    )

    missing_checksum_paths = [
        artifact.path for artifact in file_manifest.artifacts if not artifact.checksum_sha256
    ]
    checks.append(
        _result(
            "artifact_checksums_present",
            not missing_checksum_paths,
            "All artifacts include checksums."
            if not missing_checksum_paths
            else f"Artifacts missing checksums: {', '.join(missing_checksum_paths)}",
        )
    )

    mismatched_paths = _checksum_mismatches(artifact_manifest_path.parent, file_manifest)
    checks.append(
        _result(
            "artifact_checksums_match_files",
            not mismatched_paths,
            "All artifact checksums match files."
            if not mismatched_paths
            else f"Artifact checksum mismatches: {', '.join(mismatched_paths)}",
        )
    )

    evaluation_runs = [
        run
        for run in storage.list_evaluation_runs()
        if run.artifact_manifest_path == "outputs/artifact_manifest.json"
    ]
    checks.append(
        _result(
            "evaluation_run_present",
            bool(evaluation_runs),
            "Evaluation run is present."
            if evaluation_runs
            else "No evaluation run found for artifact manifest.",
        )
    )

    try:
        audit_events = storage.list_audit_events_for_scope(scope, run_id=run_id)
        present_event_types = {event.event_type for event in audit_events}
        missing_events = sorted(REQUIRED_AUDIT_EVENTS - present_event_types)
        checks.append(
            _result(
                "audit_events_present",
                not missing_events,
                "Required audit events are present."
                if not missing_events
                else f"Missing audit events: {', '.join(missing_events)}",
            )
        )
    except Exception as exc:
        checks.append(_fail("audit_events_present", str(exc)))

    checks.append(
        _check_review_approval(
            storage=storage,
            scope=scope,
            run_id=run_id,
        )
    )
    checks.append(
        _check_report_export_audit(
            storage=storage,
            scope=scope,
            run_id=run_id,
        )
    )

    try:
        connector_readiness = storage.connector_readiness_for_scope(scope, run_id=run_id)
        checks.append(
            _result(
                "connector_health_present",
                connector_readiness["health_ok"],
                "At least one passing connector health record is present."
                if connector_readiness["health_ok"]
                else "No passing connector health record found for run.",
            )
        )
        checks.append(
            _result(
                "connector_validation_present",
                connector_readiness["validation_ok"],
                "At least one passing staged connector validation record is present."
                if connector_readiness["validation_ok"]
                else "No passing staged connector validation record found for run.",
            )
        )
    except Exception as exc:
        checks.append(_fail("connector_health_present", str(exc)))
        checks.append(_fail("connector_validation_present", str(exc)))

    checks.extend(
        _check_evidence_memory_retrieval(
            storage=storage,
            scope=scope,
            run_id=run_id,
            manifest=file_manifest,
        )
    )
    checks.extend(
        _check_evidence_grading_methodology(
            storage=storage,
            scope=scope,
            run_id=run_id,
        )
    )
    checks.extend(
        _check_governance_box_trust_score(
            storage=storage,
            scope=scope,
            run_id=run_id,
        )
    )
    checks.append(
        _check_run_summary(
            run_summary_path=run_summary_path,
            manifest=file_manifest,
            run_id=run_id,
        )
    )

    wrong_scope = ProductionScope(
        tenant_id=f"{manifest.tenant_id}__scope_probe",
        workspace_id=manifest.workspace_id,
    )
    try:
        storage.get_artifact_manifest_for_scope(run_id, wrong_scope)
        checks.append(_fail("wrong_scope_rejected", "Wrong tenant scope was accepted."))
    except PermissionError:
        checks.append(_pass("wrong_scope_rejected", "Wrong tenant scope was rejected."))
    except Exception as exc:
        checks.append(_fail("wrong_scope_rejected", str(exc)))

    passed = all(check.passed for check in checks)
    created_at = datetime.now(timezone.utc).isoformat()
    result_id = f"readiness-{run_id}-{uuid.uuid4().hex}"
    payload = {
        "status": "pass" if passed else "fail",
        "run_id": run_id,
        "readiness_result_id": result_id,
        "checks": [check.to_json() for check in checks],
    }
    storage.record_readiness_check_result(
        ReadinessCheckResultRecord(
            result_id=result_id,
            run_id=run_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            status=str(payload["status"]),
            checks=tuple(check.to_json() for check in checks),
            artifact_manifest_path=str(artifact_manifest_path),
            run_summary_path=str(run_summary_path) if run_summary_path is not None else "",
            created_at=created_at,
        ),
        audit_event_id=f"{result_id}-audit",
        audit_created_at=created_at,
    )
    return payload


def _check_review_approval(
    storage: ProductionStorage,
    scope: ProductionScope,
    run_id: str,
) -> ReadinessCheck:
    try:
        tasks = storage.list_review_tasks_for_scope(scope, run_id=run_id)
    except Exception as exc:
        return _fail("review_approval_present", str(exc))
    approved_tasks = [
        task
        for task in tasks
        if task.status == ReviewStatus.APPROVED and task.decision is not None
    ]
    return _result(
        "review_approval_present",
        bool(approved_tasks),
        "At least one scoped review task is approved."
        if approved_tasks
        else "No approved scoped review task found for run.",
    )


def _check_report_export_audit(
    storage: ProductionStorage,
    scope: ProductionScope,
    run_id: str,
) -> ReadinessCheck:
    try:
        events = storage.list_audit_events_for_scope(
            scope,
            run_id=run_id,
            event_type="report_export_decision_recorded",
        )
    except Exception as exc:
        return _fail("report_export_audit_present", str(exc))
    allowed_exports = [
        event
        for event in events
        if event.payload.get("tenant_id") == scope.tenant_id
        and event.payload.get("workspace_id") == scope.workspace_id
        and event.payload.get("allowed") is True
        and event.payload.get("reason") == "export_allowed"
    ]
    return _result(
        "report_export_audit_present",
        bool(allowed_exports),
        "At least one allowed report-export audit event is present."
        if allowed_exports
        else "No allowed report-export audit event found for run.",
    )


def _check_evidence_memory_retrieval(
    storage: ProductionStorage,
    scope: ProductionScope,
    run_id: str,
    manifest: ArtifactManifest,
) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    try:
        evidence_objects = storage.list_evidence_object_records_for_scope(scope)
        checks.append(
            _result(
                "evidence_objects_present",
                bool(evidence_objects),
                "At least one scoped evidence object record is present."
                if evidence_objects
                else "No scoped evidence object records found.",
            )
        )
    except Exception as exc:
        checks.append(_fail("evidence_objects_present", str(exc)))

    try:
        indexes = storage.list_retrieval_index_records_for_scope(scope)
        index_versions = {record.index_version for record in indexes}
        checks.append(
            _result(
                "retrieval_index_current",
                manifest.index_version in index_versions,
                "Current manifest index version has a scoped retrieval index record."
                if manifest.index_version in index_versions
                else (
                    "No scoped retrieval index record found for manifest index "
                    f"version {manifest.index_version}."
                ),
            )
        )
    except Exception as exc:
        checks.append(_fail("retrieval_index_current", str(exc)))

    try:
        retrieval_runs = storage.list_retrieval_run_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "retrieval_run_present",
                bool(retrieval_runs),
                "At least one scoped retrieval run record is present."
                if retrieval_runs
                else "No scoped retrieval run record found for run.",
            )
        )
    except Exception as exc:
        checks.append(_fail("retrieval_run_present", str(exc)))

    try:
        memory_records = storage.list_production_research_memory_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "research_memory_present",
                bool(memory_records),
                "At least one scoped production research memory record is present."
                if memory_records
                else "No scoped production research memory record found for run.",
            )
        )
    except Exception as exc:
        checks.append(_fail("research_memory_present", str(exc)))
    return checks


def _check_evidence_grading_methodology(
    storage: ProductionStorage,
    scope: ProductionScope,
    run_id: str,
) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    try:
        methodology_runs = storage.list_evidence_methodology_run_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "evidence_methodology_run_present",
                bool(methodology_runs),
                "At least one scoped evidence methodology run is present."
                if methodology_runs
                else "No scoped evidence methodology run found for run.",
            )
        )
    except Exception as exc:
        checks.append(_fail("evidence_methodology_run_present", str(exc)))

    try:
        assessments = storage.list_evidence_methodology_assessment_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "evidence_methodology_assessments_present",
                bool(assessments),
                "At least one scoped evidence methodology assessment is present."
                if assessments
                else "No scoped evidence methodology assessment found for run.",
            )
        )
        checks.append(
            _result(
                "evidence_methodology_scores_present",
                bool(assessments)
                and all(0 <= record.evidence_strength_score <= 100 for record in assessments),
                "Evidence methodology assessments have bounded strength scores."
                if assessments
                and all(0 <= record.evidence_strength_score <= 100 for record in assessments)
                else "Evidence methodology assessments must include bounded strength scores.",
            )
        )
    except Exception as exc:
        checks.append(_fail("evidence_methodology_assessments_present", str(exc)))
        checks.append(_fail("evidence_methodology_scores_present", str(exc)))

    try:
        requests = storage.list_external_evidence_grading_request_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "external_evidence_grading_connector_present",
                bool(requests),
                "At least one scoped external evidence-grading connector request is present."
                if requests
                else "No scoped external evidence-grading connector request found.",
            )
        )
    except Exception as exc:
        checks.append(_fail("external_evidence_grading_connector_present", str(exc)))
    return checks


def _check_governance_box_trust_score(
    storage: ProductionStorage,
    scope: ProductionScope,
    run_id: str,
) -> list[ReadinessCheck]:
    checks: list[ReadinessCheck] = []
    try:
        trust_scores = storage.list_production_trust_score_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "production_trust_score_present",
                bool(trust_scores),
                "At least one scoped production Trust Score record is present."
                if trust_scores
                else "No scoped production Trust Score record found for run.",
            )
        )
        checks.append(
            _result(
                "production_trust_score_bounded",
                bool(trust_scores) and all(0 <= record.overall <= 100 for record in trust_scores),
                "Production Trust Score records are bounded from 0 to 100."
                if trust_scores and all(0 <= record.overall <= 100 for record in trust_scores)
                else "Production Trust Score records must be bounded from 0 to 100.",
            )
        )
    except Exception as exc:
        checks.append(_fail("production_trust_score_present", str(exc)))
        checks.append(_fail("production_trust_score_bounded", str(exc)))

    try:
        governance_boxes = storage.list_production_governance_box_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "production_governance_box_present",
                bool(governance_boxes),
                "At least one scoped production Governance Box record is present."
                if governance_boxes
                else "No scoped production Governance Box record found for run.",
            )
        )
        checks.append(
            _result(
                "production_governance_box_audit_export_status_present",
                bool(governance_boxes)
                and all(record.audit_id and record.export_status.value for record in governance_boxes),
                "Governance Box records include audit and export status metadata."
                if governance_boxes
                and all(record.audit_id and record.export_status.value for record in governance_boxes)
                else "Governance Box records must include audit and export status metadata.",
            )
        )
    except Exception as exc:
        checks.append(_fail("production_governance_box_present", str(exc)))
        checks.append(_fail("production_governance_box_audit_export_status_present", str(exc)))

    try:
        requests = storage.list_external_governance_request_records_for_scope(
            scope,
            run_id=run_id,
        )
        checks.append(
            _result(
                "external_governance_connector_present",
                bool(requests),
                "At least one scoped external governance connector request is present."
                if requests
                else "No scoped external governance connector request found.",
            )
        )
    except Exception as exc:
        checks.append(_fail("external_governance_connector_present", str(exc)))
    return checks


def _check_run_summary(
    run_summary_path: Path | None,
    manifest: ArtifactManifest,
    run_id: str,
) -> ReadinessCheck:
    if run_summary_path is None:
        return _fail("run_summary_consistent", "Run summary path was not provided.")
    if not run_summary_path.is_file():
        return _fail("run_summary_consistent", f"Run summary not found: {run_summary_path}")
    summary = json.loads(run_summary_path.read_text(encoding="utf-8"))
    expected = {
        "run_id": run_id,
        "artifact_count": len(manifest.artifacts),
        "source_count": len(manifest.sources),
        "index_version": manifest.index_version,
        "corpus_version": manifest.corpus_version,
    }
    mismatches = [
        key
        for key, expected_value in expected.items()
        if summary.get(key) != expected_value
    ]
    return _result(
        "run_summary_consistent",
        not mismatches,
        "Run summary matches manifest."
        if not mismatches
        else f"Run summary mismatches: {', '.join(mismatches)}",
    )


def _checksum_mismatches(base_dir: Path, manifest: ArtifactManifest) -> list[str]:
    mismatches: list[str] = []
    for artifact in manifest.artifacts:
        if not artifact.checksum_sha256:
            continue
        path = base_dir / artifact.path
        if not path.is_file():
            mismatches.append(artifact.path)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != artifact.checksum_sha256:
            mismatches.append(artifact.path)
    return mismatches


def _pass(name: str, message: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, passed=True, message=message)


def _fail(name: str, message: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, passed=False, message=message)


def _result(name: str, passed: bool, message: str) -> ReadinessCheck:
    return ReadinessCheck(name=name, passed=passed, message=message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Vyu production-readiness invariants.")
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--run-summary", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    payload = check_production_readiness(
        sqlite_db=args.sqlite_db,
        artifact_manifest_path=args.artifact_manifest,
        run_summary_path=args.run_summary,
        run_id=args.run_id,
        tenant_id=args.tenant_id,
        workspace_id=args.workspace_id,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
