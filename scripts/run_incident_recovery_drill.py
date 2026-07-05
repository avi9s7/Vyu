from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_production_store import (
    export_production_backup,
    restore_production_backup,
)
from scripts.inspect_production_store import inspect_production_store
from scripts.summarize_production_observability import (
    summarize_production_observability,
)


def run_incident_recovery_drill(
    sqlite_db: Path,
    backup_path: Path,
    restored_sqlite_db: Path,
    run_id: str,
    tenant_id: str,
    workspace_id: str,
) -> dict[str, Any]:
    primary_observability = summarize_production_observability(
        sqlite_db=sqlite_db,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    backup_counts = export_production_backup(sqlite_db, backup_path)
    _reset_restored_sqlite_target(restored_sqlite_db)
    restore_payload = restore_production_backup(backup_path, restored_sqlite_db)
    restored_inspection = inspect_production_store(
        sqlite_db=restored_sqlite_db,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    restored_observability = summarize_production_observability(
        sqlite_db=restored_sqlite_db,
        run_id=run_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    restored_counts = dict(restore_payload["restored_counts"])
    counts_match = all(
        restored_counts.get(key) == value for key, value in backup_counts.items()
    )
    return {
        "status": "pass" if counts_match else "fail",
        "run_id": run_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "incident": {
            "detected": primary_observability["status"] == "attention",
            "attention_reasons": list(primary_observability["attention_reasons"]),
            "primary_observability_status": primary_observability["status"],
        },
        "backup": {
            "status": "exported",
            "path": str(backup_path),
            "counts": backup_counts,
        },
        "restore": {
            "status": "restored",
            "sqlite_db": str(restored_sqlite_db),
            "counts": restored_counts,
            "counts_match_backup": counts_match,
        },
        "restored_scope_inspection": {
            "inspectable": True,
            "artifact_manifest_run_id": restored_inspection["artifact_manifest"][
                "run_id"
            ],
            "review_task_ids": [
                str(task["review_id"]) for task in restored_inspection["review_tasks"]
            ],
            "audit_event_count": len(restored_inspection["audit_events"]),
            "readiness_result_count": len(
                restored_inspection["readiness_check_results"]
            ),
        },
        "restored_observability": restored_observability,
    }


def _reset_restored_sqlite_target(path: Path) -> None:
    if path.exists() and path.is_dir():
        raise IsADirectoryError(f"Restored SQLite target is a directory: {path}")
    for candidate in (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local Vyu incident-response and recovery drill."
    )
    parser.add_argument("--sqlite-db", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--restored-sqlite-db", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--workspace-id", required=True)
    args = parser.parse_args()

    try:
        payload = run_incident_recovery_drill(
            sqlite_db=args.sqlite_db,
            backup_path=args.backup,
            restored_sqlite_db=args.restored_sqlite_db,
            run_id=args.run_id,
            tenant_id=args.tenant_id,
            workspace_id=args.workspace_id,
        )
    except (KeyError, PermissionError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
