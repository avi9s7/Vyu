from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.inspect_production_store import inspect_production_store
from scripts.summarize_production_observability import (
    summarize_production_observability,
)
from src.vyu.artifacts import ArtifactManifest


POLICY_DOCUMENTS = [
    "docs/production/intended-use.md",
    "docs/production/forbidden-uses.md",
    "docs/production/product-claim-inventory.md",
    "docs/production/regulatory-position.md",
    "docs/production/regulatory-review-checklist.md",
    "docs/production/access-control-matrix.md",
    "docs/production/source-registry-schema.md",
    "docs/production/security-architecture.md",
    "docs/production/threat-model.md",
    "docs/production/human-review-workflow.md",
    "docs/production/reviewer-queue-route-runtime.md",
    "docs/production/report-export-policy.md",
    "docs/production/observability-snapshot.md",
    "docs/production/incident-recovery-drill.md",
    "docs/production/operator-runbook.md",
    "docs/production/compliance-attestations.md",
    "docs/production/pilot-release-decision.md",
]


def build_compliance_evidence_bundle(
    sqlite_db: Path,
    artifact_manifest_path: Path,
    source_registry_path: Path,
    backup_path: Path,
    drill_json_path: Path,
    output_path: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
    attestations_path: Path | None = None,
) -> dict[str, Any]:
    inspection = inspect_production_store(
        sqlite_db=sqlite_db,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    observability = summarize_production_observability(
        sqlite_db=sqlite_db,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    manifest = ArtifactManifest.read(artifact_manifest_path)
    backup_payload = _read_json(backup_path)
    drill_payload = _read_json(drill_json_path)
    policy_documents = _policy_documents()
    source_approval = _source_approval(
        manifest=manifest,
        source_registry_path=source_registry_path,
    )
    backup_counts = _backup_counts(backup_payload)
    drill_summary = _drill_summary(drill_payload)
    attention_reasons = _attention_reasons(
        policy_documents=policy_documents,
        source_approval=source_approval,
        observability=observability,
        drill_summary=drill_summary,
        backup_counts=backup_counts,
    )

    payload = {
        "status": (
            "ready_for_pilot_review" if not attention_reasons else "attention"
        ),
        "attention_reasons": attention_reasons,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "policy_documents": policy_documents,
        "source_approval": source_approval,
        "readiness": observability["readiness"],
        "review": observability["review"],
        "report_export": observability["report_export"],
        "observability": {
            "status": observability["status"],
            "attention_reasons": list(observability["attention_reasons"]),
        },
        "backup": {
            "path": str(backup_path),
            "backup_schema_version": backup_payload.get("backup_schema_version"),
            "production_schema_version": backup_payload.get(
                "production_schema_version"
            ),
            "counts": backup_counts,
        },
        "incident_recovery_drill": drill_summary,
        "attestations": _attestation_summary(
            attestations_path=attestations_path,
            run_id=run_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        ),
        "scoped_inspection": {
            "artifact_count": len(inspection["artifact_manifest"]["artifacts"]),
            "evaluation_run_count": len(inspection["evaluation_runs"]),
            "review_task_count": len(inspection["review_tasks"]),
            "connector_health_record_count": len(
                inspection["connector_health_records"]
            ),
            "connector_validation_record_count": len(
                inspection["connector_validation_records"]
            ),
            "readiness_result_count": len(inspection["readiness_check_results"]),
            "evidence_object_record_count": len(inspection["evidence_object_records"]),
            "retrieval_index_record_count": len(inspection["retrieval_index_records"]),
            "retrieval_run_record_count": len(inspection["retrieval_run_records"]),
            "production_research_memory_record_count": len(
                inspection["production_research_memory_records"]
            ),
            "evidence_methodology_run_record_count": len(
                inspection["evidence_methodology_run_records"]
            ),
            "evidence_methodology_assessment_record_count": len(
                inspection["evidence_methodology_assessment_records"]
            ),
            "reviewer_evidence_rating_record_count": len(
                inspection["reviewer_evidence_rating_records"]
            ),
            "external_evidence_grading_request_record_count": len(
                inspection["external_evidence_grading_request_records"]
            ),
            "external_evidence_grading_response_record_count": len(
                inspection["external_evidence_grading_response_records"]
            ),
            "production_trust_score_record_count": len(
                inspection["production_trust_score_records"]
            ),
            "production_governance_box_record_count": len(
                inspection["production_governance_box_records"]
            ),
            "reviewer_trust_score_override_record_count": len(
                inspection["reviewer_trust_score_override_records"]
            ),
            "external_governance_request_record_count": len(
                inspection["external_governance_request_records"]
            ),
            "external_governance_response_record_count": len(
                inspection["external_governance_response_records"]
            ),
            "audit_event_count": len(inspection["audit_events"]),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for relative_path in POLICY_DOCUMENTS:
        path = PROJECT_ROOT / relative_path
        present = path.is_file()
        documents.append(
            {
                "path": relative_path,
                "present": present,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                if present
                else None,
            }
        )
    return documents


def _source_approval(
    manifest: ArtifactManifest,
    source_registry_path: Path,
) -> dict[str, Any]:
    registry_payload = _read_json(source_registry_path)
    registry_sources = list(registry_payload.get("sources", []))
    manifest_sources = list(manifest.sources)
    approved_sources = [
        source
        for source in manifest_sources
        if source.get("approval_status") == "approved"
        and source.get("approved_by")
        and source.get("approved_at")
    ]
    return {
        "manifest_source_count": len(manifest_sources),
        "registry_source_count": len(registry_sources),
        "approved_source_count": len(approved_sources),
        "approved_source_ids": sorted(
            str(source["source_id"]) for source in approved_sources
        ),
        "unapproved_source_ids": sorted(
            str(source.get("source_id", ""))
            for source in manifest_sources
            if source not in approved_sources
        ),
    }


def _backup_counts(backup_payload: dict[str, Any]) -> dict[str, int]:
    return {
        "artifact_manifest_count": len(backup_payload.get("artifact_manifests", [])),
        "evaluation_run_count": len(backup_payload.get("evaluation_runs", [])),
        "review_task_count": len(backup_payload.get("review_tasks", [])),
        "connector_health_record_count": len(
            backup_payload.get("connector_health_records", [])
        ),
        "connector_validation_record_count": len(
            backup_payload.get("connector_validation_records", [])
        ),
        "privacy_approval_record_count": len(
            backup_payload.get("privacy_approval_records", [])
        ),
        "readiness_check_result_count": len(
            backup_payload.get("readiness_check_results", [])
        ),
        "evidence_object_record_count": len(
            backup_payload.get("evidence_object_records", [])
        ),
        "retrieval_index_record_count": len(
            backup_payload.get("retrieval_index_records", [])
        ),
        "retrieval_run_record_count": len(
            backup_payload.get("retrieval_run_records", [])
        ),
        "production_research_memory_record_count": len(
            backup_payload.get("production_research_memory_records", [])
        ),
        "evidence_methodology_run_record_count": len(
            backup_payload.get("evidence_methodology_run_records", [])
        ),
        "evidence_methodology_assessment_record_count": len(
            backup_payload.get("evidence_methodology_assessment_records", [])
        ),
        "reviewer_evidence_rating_record_count": len(
            backup_payload.get("reviewer_evidence_rating_records", [])
        ),
        "external_evidence_grading_request_record_count": len(
            backup_payload.get("external_evidence_grading_request_records", [])
        ),
        "external_evidence_grading_response_record_count": len(
            backup_payload.get("external_evidence_grading_response_records", [])
        ),
        "production_trust_score_record_count": len(
            backup_payload.get("production_trust_score_records", [])
        ),
        "production_governance_box_record_count": len(
            backup_payload.get("production_governance_box_records", [])
        ),
        "reviewer_trust_score_override_record_count": len(
            backup_payload.get("reviewer_trust_score_override_records", [])
        ),
        "external_governance_request_record_count": len(
            backup_payload.get("external_governance_request_records", [])
        ),
        "external_governance_response_record_count": len(
            backup_payload.get("external_governance_response_records", [])
        ),
        "audit_event_count": len(backup_payload.get("audit_events", [])),
    }


def _drill_summary(drill_payload: dict[str, Any]) -> dict[str, Any]:
    restore = dict(drill_payload.get("restore", {}))
    incident = dict(drill_payload.get("incident", {}))
    restored_observability = dict(drill_payload.get("restored_observability", {}))
    return {
        "path_status": "loaded",
        "status": drill_payload.get("status"),
        "incident_detected": bool(incident.get("detected", False)),
        "attention_reasons": list(incident.get("attention_reasons", [])),
        "restore_counts_match_backup": bool(
            restore.get("counts_match_backup", False)
        ),
        "restored_observability_status": restored_observability.get("status"),
    }


def _attestation_summary(
    attestations_path: Path | None,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    if attestations_path is None:
        return {
            "path": None,
            "record_count": 0,
            "decision_counts": {},
            "approver_roles": [],
            "latest_decision": None,
            "bundle_sha256_values": [],
        }
    records = _matching_attestation_records(
        attestations_path=attestations_path,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    decision_counts: dict[str, int] = {}
    for record in records:
        decision = str(record.get("decision", "unknown"))
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    latest = (
        max(records, key=lambda record: str(record.get("attested_at", "")))
        if records
        else None
    )
    return {
        "path": str(attestations_path),
        "record_count": len(records),
        "decision_counts": dict(sorted(decision_counts.items())),
        "approver_roles": sorted(
            {str(record.get("approver_role", "")) for record in records}
        ),
        "latest_decision": latest.get("decision") if latest else None,
        "bundle_sha256_values": sorted(
            {
                str(record.get("bundle_sha256", ""))
                for record in records
                if record.get("bundle_sha256")
            }
        ),
    }


def _matching_attestation_records(
    attestations_path: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> list[dict[str, Any]]:
    if not attestations_path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        attestations_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(
                f"Attestation record on line {line_number} is not a JSON object."
            )
        if (
            record.get("run_id") == run_id
            and record.get("tenant_id") == tenant_id
            and record.get("workspace_id") == workspace_id
        ):
            records.append(record)
    return records


def _attention_reasons(
    policy_documents: list[dict[str, Any]],
    source_approval: dict[str, Any],
    observability: dict[str, Any],
    drill_summary: dict[str, Any],
    backup_counts: dict[str, int],
) -> list[str]:
    reasons: list[str] = []
    if any(not document["present"] for document in policy_documents):
        reasons.append("policy_document_missing")
    if source_approval["manifest_source_count"] == 0:
        reasons.append("manifest_sources_missing")
    if source_approval["unapproved_source_ids"]:
        reasons.append("source_approval_missing")
    reasons.extend(str(reason) for reason in observability["attention_reasons"])
    if observability["readiness"]["latest_status"] != "pass":
        reason = "readiness_not_passing"
        if reason not in reasons:
            reasons.append(reason)
    if drill_summary["status"] != "pass":
        reasons.append("incident_recovery_drill_not_passing")
    if not drill_summary["restore_counts_match_backup"]:
        reasons.append("restore_counts_mismatch")
    if backup_counts["artifact_manifest_count"] == 0:
        reasons.append("backup_manifest_missing")
    return sorted(set(reasons))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a Vyu local compliance evidence bundle for pilot review."
    )
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--drill-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--attestations", type=Path)
    args = parser.parse_args()

    try:
        payload = build_compliance_evidence_bundle(
            sqlite_db=args.sqlite_db,
            artifact_manifest_path=args.artifact_manifest,
            source_registry_path=args.source_registry,
            backup_path=args.backup,
            drill_json_path=args.drill_json,
            output_path=args.output,
            run_id=args.run_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
            attestations_path=args.attestations,
        )
    except (json.JSONDecodeError, KeyError, PermissionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
