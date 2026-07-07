# Connector Health Validation

## Purpose

This document defines the first production-shaped connector health and staged validation records for Vyu. The current implementation is local and deterministic, with replay validation available by default and live validation remaining environment-gated.

## Health Records

Connector health records capture:

- `source_id`
- connector name
- status: `ok` or `fail`
- check timestamp
- latency in milliseconds
- structured details
- error text for failures

The record model is implemented in `src/vyu/connectors/health.py`. Records can be persisted through `src/vyu/storage/production.py` with tenant/workspace scope, audit events, and backup/restore support.

## Staged Validation

Staged validation records capture PubMed connector behavior by stage:

| Stage | Meaning |
| --- | --- |
| `replay` | Offline replay validation using `PubMedReplayTransport` |
| `live` | Staging/live validation using the gated PubMed HTTP transport |

Each staged validation record includes:

- `source_id`
- connector name
- stage
- status
- check timestamp
- query
- limit
- document count
- latency
- error text for failures

## PubMed Validation Policy

- Replay validation should run in normal local and CI workflows.
- Live validation must remain opt-in through `VYU_RUN_LIVE_PUBMED_TESTS=1`.
- Scheduled staging probes use `scripts/probe_pubmed_staging.py` with replay by default and live execution gated by `VYU_RUN_LIVE_PUBMED_PROBE=1`.
- Live validation requires NCBI runtime settings such as `VYU_NCBI_EMAIL` and `VYU_NCBI_TOOL`.
- Failed validation records should be retained for staged connector triage.
- Production readiness requires at least one passing connector health record and at least one passing staged connector validation record for the run scope.

## Persistence

When `scripts/run_phase_outputs.py` runs with `--sqlite-db`, it records:

- a `DummyConnector` health record for the local synthetic corpus path
- a PubMed `replay` staged validation record using deterministic offline replay data
- production audit events named `connector_health_recorded` and `connector_validation_recorded`

The records are included in `scripts/backup_production_store.py` exports and restored into fresh production SQLite stores.

## Current Limitations

- There is no connector dashboard or source freshness monitor.
- Live connector readiness is still opt-in and not required for local deterministic readiness checks.
- Broader source freshness, dashboarding, and live staging promotion policies are not implemented.
