# Incident Recovery Drill

This document defines the first local incident-response and recovery drill evidence for Vyu. It exercises the production-shaped SQLite store without requiring deployed infrastructure.

The implementation is `scripts/run_incident_recovery_drill.py`. It composes existing operator controls:

- scoped observability snapshot of the primary store
- production backup export
- backup restore into a fresh SQLite store
- scoped inspection of the restored store
- scoped observability snapshot of the restored store

## Drill Command

```bash
python scripts/run_incident_recovery_drill.py --sqlite-db outputs/production.sqlite --backup outputs/drill_production_backup.json --restored-sqlite-db outputs/drill_restored_production.sqlite --run-id local-phase-output-run --tenant-id local_tenant --workspace-id local_workspace
```

The command returns JSON and rejects the request before backup export if the run is outside the requested tenant/workspace scope.

## Drill Evidence

| Field | Meaning |
| --- | --- |
| `incident.detected` | Whether the primary observability snapshot was in `attention` state |
| `incident.attention_reasons` | Primary attention reasons such as missing readiness, pending review, or missing allowed report export |
| `backup.counts` | Counts exported from the production backup |
| `restore.counts` | Counts restored into the fresh SQLite store |
| `restore.counts_match_backup` | Whether restored counts match backup counts |
| `restored_scope_inspection` | Confirmation that the restored run is inspectable within tenant/workspace scope |
| `restored_observability` | Observability snapshot from the restored store |

## Operator Interpretation

- `status: pass` means the drill completed and backup counts matched restored counts.
- `incident.detected: true` means the primary store had an attention state before recovery evidence was captured.
- `restored_scope_inspection.inspectable: true` means the restored store can serve scoped operator inspection for the run.
- A restored observability status of `attention` is acceptable when the primary incident was an unresolved readiness or review issue; the drill is proving detection and recovery evidence, not automatically resolving the incident.

## Current Limits

- The drill is local and deterministic; it does not exercise cloud infrastructure, object storage, managed databases, alert routing, pager workflows, or customer communications.
- The drill does not delete or corrupt the primary store.
- The drill restores into a caller-provided SQLite path. Use a fresh path for each run.
