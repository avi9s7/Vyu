from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vyu.storage import ProductionStorage


def export_production_backup(sqlite_db: Path, backup_path: Path) -> dict[str, int]:
    storage = ProductionStorage(sqlite_db)
    backup = storage.export_backup()
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(
        json.dumps(backup, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _backup_counts(backup)


def restore_production_backup(backup_path: Path, sqlite_db: Path) -> dict[str, Any]:
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    storage = ProductionStorage(sqlite_db)
    restored_counts = storage.restore_backup(backup)
    return {
        "sqlite_db": str(sqlite_db),
        "restored_counts": restored_counts,
    }


def _backup_counts(backup: dict[str, Any]) -> dict[str, int]:
    return {
        "artifact_manifest_count": len(backup.get("artifact_manifests", [])),
        "evaluation_run_count": len(backup.get("evaluation_runs", [])),
        "review_task_count": len(backup.get("review_tasks", [])),
        "connector_health_record_count": len(
            backup.get("connector_health_records", [])
        ),
        "connector_validation_record_count": len(
            backup.get("connector_validation_records", [])
        ),
        "privacy_approval_record_count": len(
            backup.get("privacy_approval_records", [])
        ),
        "readiness_check_result_count": len(
            backup.get("readiness_check_results", [])
        ),
        "evidence_object_record_count": len(
            backup.get("evidence_object_records", [])
        ),
        "retrieval_index_record_count": len(
            backup.get("retrieval_index_records", [])
        ),
        "retrieval_run_record_count": len(
            backup.get("retrieval_run_records", [])
        ),
        "production_research_memory_record_count": len(
            backup.get("production_research_memory_records", [])
        ),
        "evidence_methodology_run_record_count": len(
            backup.get("evidence_methodology_run_records", [])
        ),
        "evidence_methodology_assessment_record_count": len(
            backup.get("evidence_methodology_assessment_records", [])
        ),
        "reviewer_evidence_rating_record_count": len(
            backup.get("reviewer_evidence_rating_records", [])
        ),
        "external_evidence_grading_request_record_count": len(
            backup.get("external_evidence_grading_request_records", [])
        ),
        "external_evidence_grading_response_record_count": len(
            backup.get("external_evidence_grading_response_records", [])
        ),
        "production_trust_score_record_count": len(
            backup.get("production_trust_score_records", [])
        ),
        "production_governance_box_record_count": len(
            backup.get("production_governance_box_records", [])
        ),
        "reviewer_trust_score_override_record_count": len(
            backup.get("reviewer_trust_score_override_records", [])
        ),
        "external_governance_request_record_count": len(
            backup.get("external_governance_request_records", [])
        ),
        "external_governance_response_record_count": len(
            backup.get("external_governance_response_records", [])
        ),
        "research_mcp_plan_count": len(
            backup.get("research_mcp_plans", [])
        ),
        "research_mcp_tool_call_count": len(
            backup.get("research_mcp_tool_calls", [])
        ),
        "research_mcp_replay_record_count": len(
            backup.get("research_mcp_replay_records", [])
        ),
        "audit_event_count": len(backup.get("audit_events", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or restore Vyu production store backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export SQLite production store to JSON.")
    export_parser.add_argument("--sqlite-db", type=Path, required=True)
    export_parser.add_argument("--backup", type=Path, required=True)

    restore_parser = subparsers.add_parser("restore", help="Restore JSON backup to SQLite.")
    restore_parser.add_argument("--backup", type=Path, required=True)
    restore_parser.add_argument("--sqlite-db", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "export":
        counts = export_production_backup(args.sqlite_db, args.backup)
        payload: dict[str, Any] = {
            "status": "exported",
            "sqlite_db": str(args.sqlite_db),
            "backup": str(args.backup),
            **counts,
        }
    else:
        restore_payload = restore_production_backup(args.backup, args.sqlite_db)
        payload = {
            "status": "restored",
            "backup": str(args.backup),
            **restore_payload,
        }

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
