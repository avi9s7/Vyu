# Database and object restore runbook

Operator runbook for proving RDS point-in-time recovery (PITR) and S3 version restore in VYU staging before production pilot approval.

## Pilot recovery targets

| Target | Value | Infrastructure basis |
| --- | --- | --- |
| RPO | <= 15 minutes | RDS automated backups with PITR (5-minute restore granularity) |
| RTO | <= 4 hours | Restore to a new RDS instance, run isolated verification, and re-point verification tasks |

These targets are declared in `infra/terraform/modules/data/locals.tf` as `pilot_recovery_targets` and exported from the data module.

Creating a snapshot alone is **not** a restore test. A passing exercise must restore data to a chosen point in time and verify application fixtures.

## Prerequisites

- Staging AWS account with applied Terraform (`modules/data`)
- RDS automated backups enabled (`backup_retention_period > 0`)
- S3 versioning enabled on `evidence`, `exports`, and `audit` buckets
- Operator access to RDS, S3, ECS, and Secrets Manager
- Isolated security group for restore verification tasks (no production service traffic)
- Change ticket opened with operator name and UTC start time

## 1. Write the restore fixture

Before choosing a restore point, write known fixture data in staging:

1. Create tenant/workspace `restore-fixture` with a research submission and audit record.
2. Upload one evidence object to the evidence bucket and record:
   - object key
   - S3 `VersionId`
   - SHA-256 digest of the object bytes
3. Store the S3 `VersionId` and digest in the related audit event `details` (`s3_version_id`, `object_sha256`).
4. Create a second tenant/workspace used only for isolation checks.
5. After the restore point timestamp, create marker records that must **not** appear in the restored database:
   - one additional research run
   - one additional audit event

Capture fixture fingerprints:

```powershell
uv run python -c "from scripts.verify_restore import tenant_fingerprint, research_fingerprint; print(tenant_fingerprint(slug='restore-fixture', name='Restore Fixture Tenant')); print(research_fingerprint(question='What is the efficacy of VX-101 for episodic migraine prevention?'))"
```

Record:

- tenant/workspace UUIDs
- research run ID, job ID, audit event ID
- tenant and research fingerprints
- audit `payload_sha256`
- post-restore marker IDs
- restore point UTC timestamp

## 2. Restore RDS to a new instance

1. Choose the restore point immediately before the marker records were written.
2. Restore to a **new** RDS instance identifier, for example `vyu-staging-postgres-restore-20260706`.
3. Do not overwrite the live staging primary instance during the drill.
4. Record restore start and end timestamps for RTO measurement.

Example:

```powershell
aws rds restore-db-instance-to-point-in-time `
  --source-db-instance-identifier "vyu-staging-postgres" `
  --target-db-instance-identifier "vyu-staging-postgres-restore-20260706" `
  --restore-time "2026-07-06T09:15:00Z" `
  --db-subnet-group-name "vyu-staging-database" `
  --vpc-security-group-ids "<verification-sg-id>" `
  --no-publicly-accessible
```

Wait until the instance is `available`.

## 3. Point an isolated verification task at the restored database

1. Create a temporary database connection secret or environment override for the restored endpoint.
2. Run the migration verification ECS task or a one-off verification container against the restored instance only.
3. Do not attach production ECS services to the restored instance.

Set the verification URL in the environment variable expected by `verify_restore.py`:

```powershell
$env:VYU_VERIFY_RESTORE_DATABASE_URL = "postgresql+psycopg://vyu_app:<password>@<restore-endpoint>:5432/vyu"
```

## 4. Build the restore manifest

Create `restore-manifest.json`:

```json
{
  "expected_migration_revision": "0003",
  "restore_point_utc": "2026-07-06T09:15:00+00:00",
  "scope": {
    "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "workspace_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "isolation_tenant_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "isolation_workspace_id": "dddddddd-dddd-dddd-dddd-dddddddddddd"
  },
  "records": {
    "research_run_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
    "job_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
    "audit_event_id": "11111111-1111-1111-1111-111111111111",
    "tenant_fingerprint": "<sha256>",
    "research_fingerprint": "<sha256>",
    "audit_payload_sha256": "<sha256>"
  },
  "absent_after_restore": {
    "research_run_ids": ["22222222-2222-2222-2222-222222222222"],
    "audit_event_ids": ["33333333-3333-3333-3333-333333333333"]
  },
  "s3_objects": [
    {
      "bucket": "vyu-staging-evidence-<account-id>",
      "key": "tenant/<tenant-id>/fixture/object.bin",
      "expected_version_id": "<version-id>",
      "expected_sha256": "sha256:<digest>",
      "database_reference": {
        "resource_type": "audit_event",
        "resource_id": "11111111-1111-1111-1111-111111111111"
      }
    }
  ]
}
```

## 5. Run restore verification

```powershell
uv run python scripts/verify_restore.py `
  --manifest restore-manifest.json `
  --aws-region ap-south-1
```

`verify_restore.py` checks:

- Alembic migration revision
- Fixture tenant/research/audit hashes
- Job presence for the fixture research run
- Tenant isolation across the second tenant/workspace
- Absence of post-restore marker records
- Selected S3 object version digests
- Database audit references to restored object version/checksum

Store the JSON output in release evidence. A non-zero exit code blocks Plan 4 completion.

## 6. Restore selected S3 object versions

When an object was mutated after the restore point:

```powershell
aws s3api get-object `
  --bucket "vyu-staging-evidence-<account-id>" `
  --key "tenant/<tenant-id>/fixture/object.bin" `
  --version-id "<version-id>" `
  restored-object.bin
```

Compare the digest with the manifest `expected_sha256` and the audit event `details.object_sha256`.

Versioning and noncurrent version expiration are configured in `infra/terraform/modules/data/s3.tf`.

## 7. Record measured RPO/RTO and cleanup

Attach an evidence record:

```json
{
  "environment": "staging",
  "operator": "<name>",
  "owner_approval": "<name>",
  "restore_point_utc": "2026-07-06T09:15:00+00:00",
  "fixture_written_at_utc": "2026-07-06T09:10:00+00:00",
  "marker_written_at_utc": "2026-07-06T09:20:00+00:00",
  "rds_restore_started_at_utc": "<iso8601>",
  "rds_restore_available_at_utc": "<iso8601>",
  "measured_rpo_minutes": 5,
  "measured_rto_minutes": 95,
  "pilot_rpo_target_minutes": 15,
  "pilot_rto_target_hours": 4,
  "restored_instance_identifier": "vyu-staging-postgres-restore-20260706",
  "verify_restore_status": "pass",
  "migration_revision": "0003",
  "gaps": "",
  "cleanup_completed_at_utc": "<iso8601>"
}
```

Cleanup after evidence capture:

1. Delete the temporary restored RDS instance.
2. Remove temporary secrets and security-group rules.
3. Delete restored-object scratch files from operator workstations.

## 8. Abort conditions

Stop the drill and escalate if:

- Restored instance does not reach `available`
- `verify_restore.py` fails any check
- Post-restore marker records are present
- S3 version digest does not match the audit reference
- Measured RPO or RTO exceeds pilot targets without approved exception

Do not mark Plan 4 complete until dev/staging deploy, smoke, rollback, rotation, and restore exercises all pass with bound evidence.
