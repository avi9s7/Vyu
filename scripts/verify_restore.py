#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.vyu.db.models.audit import AuditEvent
from src.vyu.db.models.tenancy import Tenant
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.models import Job, ResearchRun


class VerifyRestoreError(Exception):
    """Raised when restore verification input is invalid."""


@dataclass(frozen=True)
class RestoreCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerifyRestoreResult:
    status: str
    restore_point_utc: str
    checks: tuple[RestoreCheck, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "restore_point_utc": self.restore_point_utc,
            "checks": [asdict(check) for check in self.checks],
        }


def tenant_fingerprint(*, slug: str, name: str) -> str:
    return hashlib.sha256(f"{slug}\n{name}".encode("utf-8")).hexdigest()


def research_fingerprint(*, question: str) -> str:
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


def load_restore_manifest(raw: str) -> dict[str, Any]:
    manifest = json.loads(raw)
    required = (
        "expected_migration_revision",
        "restore_point_utc",
        "scope",
        "records",
        "absent_after_restore",
    )
    missing = [key for key in required if key not in manifest]
    if missing:
        raise VerifyRestoreError("Restore manifest missing keys: " + ", ".join(missing))
    return manifest


def _parse_uuid(value: str, *, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise VerifyRestoreError(f"Invalid UUID for {field}: {value}") from exc


def _scope_from_manifest(manifest: dict[str, Any]) -> TenantScope:
    scope = manifest["scope"]
    return TenantScope(
        tenant_id=_parse_uuid(scope["tenant_id"], field="scope.tenant_id"),
        workspace_id=_parse_uuid(scope["workspace_id"], field="scope.workspace_id"),
    )


def verify_migration_revision(engine: Engine, *, expected_revision: str) -> RestoreCheck:
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    passed = str(revision) == expected_revision
    return RestoreCheck(
        name="migration_revision",
        passed=passed,
        detail=f"expected={expected_revision} actual={revision}",
    )


def verify_fixture_hashes(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope,
    records: dict[str, Any],
) -> list[RestoreCheck]:
    checks: list[RestoreCheck] = []
    with transaction(factory, scope=scope) as session:
        tenant = session.get(Tenant, scope.tenant_id)
        research = session.get(
            ResearchRun,
            _parse_uuid(records["research_run_id"], field="records.research_run_id"),
        )
        job = session.get(Job, _parse_uuid(records["job_id"], field="records.job_id"))
        audit = session.get(
            AuditEvent,
            _parse_uuid(records["audit_event_id"], field="records.audit_event_id"),
        )

        tenant_ok = tenant is not None
        if tenant_ok:
            actual_tenant_hash = tenant_fingerprint(slug=tenant.slug, name=tenant.name)
            tenant_ok = actual_tenant_hash == records["tenant_fingerprint"]
        checks.append(
            RestoreCheck(
                name="tenant_fixture_hash",
                passed=tenant_ok,
                detail=(
                    f"expected={records['tenant_fingerprint']} "
                    f"actual={tenant_fingerprint(slug=tenant.slug, name=tenant.name) if tenant else 'missing'}"
                ),
            )
        )

        research_ok = research is not None
        if research_ok:
            actual_research_hash = research_fingerprint(question=research.question)
            research_ok = actual_research_hash == records["research_fingerprint"]
        checks.append(
            RestoreCheck(
                name="research_fixture_hash",
                passed=research_ok,
                detail=(
                    f"expected={records['research_fingerprint']} "
                    f"actual={research_fingerprint(question=research.question) if research else 'missing'}"
                ),
            )
        )

        checks.append(
            RestoreCheck(
                name="job_fixture_present",
                passed=job is not None,
                detail="present" if job is not None else "missing",
            )
        )

        audit_ok = audit is not None
        if audit_ok:
            audit_ok = audit.payload_sha256 == records["audit_payload_sha256"]
        checks.append(
            RestoreCheck(
                name="audit_fixture_hash",
                passed=audit_ok,
                detail=(
                    f"expected={records['audit_payload_sha256']} "
                    f"actual={audit.payload_sha256 if audit else 'missing'}"
                ),
            )
        )
    return checks


def verify_tenant_isolation(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope,
    records: dict[str, Any],
    isolation_scope: TenantScope,
) -> RestoreCheck:
    research_id = _parse_uuid(records["research_run_id"], field="records.research_run_id")
    with transaction(factory, scope=scope) as session:
        visible_in_fixture_scope = session.get(ResearchRun, research_id) is not None
    with transaction(factory, scope=isolation_scope) as session:
        visible_in_other_scope = session.get(ResearchRun, research_id) is not None
    passed = visible_in_fixture_scope and not visible_in_other_scope
    return RestoreCheck(
        name="tenant_isolation",
        passed=passed,
        detail=(
            f"fixture_scope_visible={visible_in_fixture_scope} "
            f"other_scope_visible={visible_in_other_scope}"
        ),
    )


def verify_absent_after_restore(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope,
    absent_after_restore: dict[str, Any],
) -> list[RestoreCheck]:
    checks: list[RestoreCheck] = []
    with transaction(factory, scope=scope) as session:
        for research_id in absent_after_restore.get("research_run_ids", []):
            parsed = _parse_uuid(research_id, field="absent_after_restore.research_run_id")
            present = session.get(ResearchRun, parsed) is not None
            checks.append(
                RestoreCheck(
                    name=f"absent_research_run_{parsed}",
                    passed=not present,
                    detail="present" if present else "absent",
                )
            )
        for audit_id in absent_after_restore.get("audit_event_ids", []):
            parsed = _parse_uuid(audit_id, field="absent_after_restore.audit_event_id")
            present = session.get(AuditEvent, parsed) is not None
            checks.append(
                RestoreCheck(
                    name=f"absent_audit_event_{parsed}",
                    passed=not present,
                    detail="present" if present else "absent",
                )
            )
    return checks


def verify_audit_presence(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope,
    records: dict[str, Any],
) -> RestoreCheck:
    audit_id = _parse_uuid(records["audit_event_id"], field="records.audit_event_id")
    with transaction(factory, scope=scope) as session:
        audit = session.get(AuditEvent, audit_id)
    return RestoreCheck(
        name="audit_presence",
        passed=audit is not None,
        detail="present" if audit is not None else "missing",
    )


def verify_s3_object_versions(
    *,
    objects: list[dict[str, Any]],
    region: str | None = None,
    factory: sessionmaker[Session] | None = None,
    scope: TenantScope | None = None,
) -> list[RestoreCheck]:
    if not objects:
        return []
    client = boto3.client("s3", region_name=region)
    checks: list[RestoreCheck] = []
    for item in objects:
        bucket = item["bucket"]
        key = item["key"]
        version_id = item["expected_version_id"]
        expected_sha256 = item["expected_sha256"]
        try:
            response = client.get_object(Bucket=bucket, Key=key, VersionId=version_id)
            body = response["Body"].read()
            actual_sha256 = hashlib.sha256(body).hexdigest()
            expected_digest = expected_sha256.removeprefix("sha256:").lower()
            passed = actual_sha256 == expected_digest
            checks.append(
                RestoreCheck(
                    name=f"s3_version_{bucket}/{key}",
                    passed=passed,
                    detail=f"version_id={version_id} sha256={actual_sha256}",
                )
            )
        except ClientError as exc:
            checks.append(
                RestoreCheck(
                    name=f"s3_version_{bucket}/{key}",
                    passed=False,
                    detail=str(exc),
                )
            )
            continue

        reference = item.get("database_reference")
        if reference and factory is not None and scope is not None:
            checks.extend(
                _verify_database_reference(
                    factory,
                    scope=scope,
                    reference=reference,
                    expected_version_id=version_id,
                    expected_sha256=expected_sha256,
                )
            )
    return checks


def _verify_database_reference(
    factory: sessionmaker[Session],
    *,
    scope: TenantScope,
    reference: dict[str, Any],
    expected_version_id: str,
    expected_sha256: str,
) -> list[RestoreCheck]:
    resource_type = reference["resource_type"]
    resource_id = reference["resource_id"]
    checks: list[RestoreCheck] = []
    if resource_type != "audit_event":
        return [
            RestoreCheck(
                name="database_reference",
                passed=False,
                detail=f"unsupported resource_type={resource_type}",
            )
        ]
    with transaction(factory, scope=scope) as session:
        audit = session.get(AuditEvent, _parse_uuid(resource_id, field="database_reference.resource_id"))
    if audit is None:
        return [
            RestoreCheck(
                name="database_reference",
                passed=False,
                detail="audit event missing",
            )
        ]
    details = audit.details or {}
    version_ok = details.get("s3_version_id") == expected_version_id
    checksum_ok = (
        str(details.get("object_sha256", "")).removeprefix("sha256:").lower()
        == expected_sha256.removeprefix("sha256:").lower()
    )
    checks.append(
        RestoreCheck(
            name="database_reference_version",
            passed=version_ok,
            detail=f"expected={expected_version_id} actual={details.get('s3_version_id')}",
        )
    )
    checks.append(
        RestoreCheck(
            name="database_reference_checksum",
            passed=checksum_ok,
            detail=f"expected={expected_sha256} actual={details.get('object_sha256')}",
        )
    )
    return checks


def verify_restore(
    *,
    database_url: str,
    manifest: dict[str, Any],
    aws_region: str | None = None,
) -> VerifyRestoreResult:
    scope = _scope_from_manifest(manifest)
    isolation_scope = TenantScope(
        tenant_id=_parse_uuid(
            manifest["scope"]["isolation_tenant_id"],
            field="scope.isolation_tenant_id",
        ),
        workspace_id=_parse_uuid(
            manifest["scope"]["isolation_workspace_id"],
            field="scope.isolation_workspace_id",
        ),
    )
    engine = build_engine(DatabaseSettings(database_url=database_url))
    factory = build_session_factory(engine)

    checks: list[RestoreCheck] = [
        verify_migration_revision(
            engine,
            expected_revision=manifest["expected_migration_revision"],
        ),
        verify_audit_presence(factory, scope=scope, records=manifest["records"]),
        *verify_fixture_hashes(factory, scope=scope, records=manifest["records"]),
        verify_tenant_isolation(
            factory,
            scope=scope,
            records=manifest["records"],
            isolation_scope=isolation_scope,
        ),
        *verify_absent_after_restore(
            factory,
            scope=scope,
            absent_after_restore=manifest["absent_after_restore"],
        ),
        *verify_s3_object_versions(
            objects=manifest.get("s3_objects", []),
            region=aws_region,
            factory=factory,
            scope=scope,
        ),
    ]
    status = "pass" if all(check.passed for check in checks) else "fail"
    return VerifyRestoreResult(
        status=status,
        restore_point_utc=manifest["restore_point_utc"],
        checks=tuple(checks),
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a restored RDS database and optional S3 object versions.",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="PostgreSQL URL for the isolated verification database.",
    )
    parser.add_argument(
        "--database-url-env",
        default="VYU_VERIFY_RESTORE_DATABASE_URL",
        help="Environment variable containing the verification database URL.",
    )
    parser.add_argument("--manifest", required=True, type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--aws-region", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = args.database_url.strip()
    if not database_url:
        import os

        database_url = os.environ.get(args.database_url_env, "").strip()
    if not database_url:
        print(
            "Database URL is required via --database-url or "
            f"{args.database_url_env}.",
            file=sys.stderr,
        )
        return 2
    try:
        manifest = json.load(args.manifest)
        result = verify_restore(
            database_url=database_url,
            manifest=manifest,
            aws_region=args.aws_region,
        )
    except (VerifyRestoreError, json.JSONDecodeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = result.to_json()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
