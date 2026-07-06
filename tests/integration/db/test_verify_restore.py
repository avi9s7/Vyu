from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from scripts.verify_restore import (
    research_fingerprint,
    tenant_fingerprint,
    verify_restore,
)
from src.vyu.db.repositories.audit import AuditRepository, NewAuditEvent
from src.vyu.db.repositories.tenancy import (
    IdentityUser,
    NewMembership,
    NewTenant,
    NewWorkspace,
    TenancyRepository,
)
from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.jobs.models import Job, ResearchRun


def _seed_restore_fixture(postgres_urls: dict[str, str]) -> dict[str, object]:
    tenant_id = uuid4()
    workspace_id = uuid4()
    other_tenant_id = uuid4()
    other_workspace_id = uuid4()
    user_id = uuid4()
    research_id = uuid4()
    job_id = uuid4()
    audit_id = uuid4()
    marker_research_id = uuid4()
    marker_audit_id = uuid4()

    migration_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )
    with migration_factory.begin() as session:
        repo = TenancyRepository(session)
        repo.add_tenant(
            NewTenant(id=tenant_id, slug="restore-fixture", name="Restore Fixture Tenant")
        )
        repo.add_tenant(NewTenant(id=other_tenant_id, slug="restore-other", name="Restore Other"))
        repo.upsert_user(
            IdentityUser(
                id=user_id,
                issuer="https://restore.example.invalid",
                subject="restore-user",
                email="restore@example.invalid",
            )
        )
    with migration_factory.begin() as session:
        repo = TenancyRepository(session)
        repo.add_workspace(
            NewWorkspace(
                id=workspace_id,
                tenant_id=tenant_id,
                slug="restore-ws",
                name="Restore Workspace",
            )
        )
        repo.add_workspace(
            NewWorkspace(
                id=other_workspace_id,
                tenant_id=other_tenant_id,
                slug="other-ws",
                name="Other Workspace",
            )
        )
        repo.add_membership(
            NewMembership(
                id=uuid4(),
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                user_id=user_id,
                role="reviewer",
            )
        )

    app_factory = build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["app"]))
    )
    scope = TenantScope(tenant_id=tenant_id, workspace_id=workspace_id)
    question = "What is the efficacy of VX-101 for episodic migraine prevention?"
    audit_payload_sha256 = "abc123fixture"
    object_bytes = bytes.fromhex("deadbeef")
    object_sha256 = f"sha256:{hashlib.sha256(object_bytes).hexdigest()}"
    with transaction(app_factory, scope=scope) as session:
        session.add(
            ResearchRun(
                id=research_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                created_by=user_id,
                question=question,
                intended_use="general_research",
                requested_sources=["pubmed"],
                status="queued",
                cancel_requested=False,
                policy_version="pilot-1",
            )
        )
        session.add(
            Job(
                id=job_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                kind="research.run",
                status="queued",
                payload={"research_run_id": str(research_id)},
            )
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=audit_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_type="user",
                actor_id="restore-user",
                request_id="restore-req-1",
                event_type="restore.fixture.created",
                resource_type="research_run",
                resource_id=str(research_id),
                outcome="success",
                payload_sha256=audit_payload_sha256,
                details={
                    "s3_version_id": "version-1",
                    "object_sha256": object_sha256,
                },
            )
        )
        session.add(
            ResearchRun(
                id=marker_research_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                created_by=user_id,
                question="post-restore marker",
                intended_use="general_research",
                requested_sources=["pubmed"],
                status="queued",
                cancel_requested=False,
                policy_version="pilot-1",
            )
        )
        AuditRepository(session).append(
            NewAuditEvent(
                id=marker_audit_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                actor_type="user",
                actor_id="restore-user",
                request_id="restore-req-2",
                event_type="restore.marker.created",
                resource_type="research_run",
                resource_id=str(marker_research_id),
                outcome="success",
                payload_sha256="marker",
            )
        )

    return {
        "scope": {
            "tenant_id": str(tenant_id),
            "workspace_id": str(workspace_id),
            "isolation_tenant_id": str(other_tenant_id),
            "isolation_workspace_id": str(other_workspace_id),
        },
        "records": {
            "research_run_id": str(research_id),
            "job_id": str(job_id),
            "audit_event_id": str(audit_id),
            "tenant_fingerprint": tenant_fingerprint(
                slug="restore-fixture",
                name="Restore Fixture Tenant",
            ),
            "research_fingerprint": research_fingerprint(question=question),
            "audit_payload_sha256": audit_payload_sha256,
        },
        "absent_after_restore": {
            "research_run_ids": [str(marker_research_id)],
            "audit_event_ids": [str(marker_audit_id)],
        },
        "s3_objects": [
            {
                "bucket": "vyu-staging-evidence-example",
                "key": "fixture/object.bin",
                "expected_version_id": "version-1",
                "expected_sha256": object_sha256,
                "database_reference": {
                    "resource_type": "audit_event",
                    "resource_id": str(audit_id),
                },
            }
        ],
    }


def test_verify_restore_passes_against_seeded_database(postgres_urls: dict[str, str]) -> None:
    fixture = _seed_restore_fixture(postgres_urls)
    manifest = {
        "expected_migration_revision": "0003",
        "restore_point_utc": datetime.now(tz=UTC).isoformat(),
        **fixture,
    }

    class _Body:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

    def _fake_get_object(*, Bucket: str, Key: str, VersionId: str) -> dict[str, object]:
        assert VersionId == "version-1"
        return {"Body": _Body(bytes.fromhex("deadbeef"))}

    with patch("scripts.verify_restore.boto3.client") as client_factory:
        client_factory.return_value.get_object.side_effect = _fake_get_object
        result = verify_restore(
            database_url=postgres_urls["app"],
            manifest=manifest,
            aws_region="ap-south-1",
        )

    payload = result.to_json()
    assert payload["status"] == "pass"
    assert all(check["passed"] for check in payload["checks"])


def test_verify_restore_fails_when_fixture_hash_does_not_match(
    postgres_urls: dict[str, str],
) -> None:
    fixture = _seed_restore_fixture(postgres_urls)
    manifest = {
        "expected_migration_revision": "0003",
        "restore_point_utc": datetime.now(tz=UTC).isoformat(),
        **fixture,
        "s3_objects": [],
    }
    manifest["records"]["tenant_fingerprint"] = "0" * 64

    result = verify_restore(
        database_url=postgres_urls["app"],
        manifest=manifest,
        aws_region="ap-south-1",
    )

    assert result.status == "fail"


def test_verify_restore_cli_prints_json(tmp_path, postgres_urls: dict[str, str], monkeypatch) -> None:
    fixture = _seed_restore_fixture(postgres_urls)
    manifest_path = tmp_path / "restore-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "expected_migration_revision": "0003",
                "restore_point_utc": datetime.now(tz=UTC).isoformat(),
                **fixture,
                "s3_objects": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VYU_VERIFY_RESTORE_DATABASE_URL", postgres_urls["app"])
    from scripts import verify_restore as verify_restore_module

    exit_code = verify_restore_module.main(["--manifest", str(manifest_path)])
    assert exit_code == 0
