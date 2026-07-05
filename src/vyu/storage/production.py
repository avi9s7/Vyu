from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.vyu.artifacts import ArtifactManifest
from src.vyu.connectors.health import (
    ConnectorHealthRecord,
    ConnectorHealthStatus,
    StagedConnectorValidationRecord,
)
from src.vyu.evaluation import EvaluationRun
from src.vyu.evidence.external import (
    ExternalEvidenceGradingRequestRecord,
    ExternalEvidenceGradingResponseRecord,
)
from src.vyu.evidence.methodology import (
    EvidenceMethodologyAssessmentRecord,
    EvidenceMethodologyRunRecord,
    ReviewerEvidenceRatingRecord,
)
from src.vyu.governance.external import (
    ExternalGovernanceRequestRecord,
    ExternalGovernanceResponseRecord,
)
from src.vyu.governance.production import (
    ProductionGovernanceBoxRecord,
    ProductionTrustScoreRecord,
    ReviewerTrustScoreOverrideRecord,
)
from src.vyu.memory.production import ProductionResearchMemoryRecord
from src.vyu.retrieval.production import (
    EvidenceObjectRecord,
    RetrievalIndexRecord,
    RetrievalRunRecord,
)
from src.vyu.research_mcp.contracts import (
    SearchPlan,
    ToolCallAuditRecord,
    ToolCallReplayRecord,
)
from src.vyu.review import ReviewTask


PRODUCTION_SCHEMA_VERSION = 9
BASELINE_MIGRATION_NAME = "baseline_production_schema"
REVIEW_TASKS_MIGRATION_NAME = "review_task_storage"
CONNECTOR_HEALTH_MIGRATION_NAME = "connector_health_storage"
PRIVACY_APPROVAL_MIGRATION_NAME = "privacy_approval_storage"
READINESS_RESULT_MIGRATION_NAME = "readiness_result_storage"
EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME = "evidence_memory_retrieval_storage"
EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME = "evidence_grading_methodology_storage"
GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME = "governance_box_trust_score_storage"
RESEARCH_MCP_MIGRATION_NAME = "research_mcp_storage"


@dataclass(frozen=True)
class ProductionAuditEvent:
    event_id: str
    run_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProductionAuditEvent":
        return cls(
            event_id=str(payload["event_id"]),
            run_id=str(payload["run_id"]),
            event_type=str(payload["event_type"]),
            payload=dict(payload.get("payload", {})),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class ProductionScope:
    tenant_id: str
    workspace_id: str


@dataclass(frozen=True)
class PrivacyApprovalRecord:
    approval_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    purpose: str
    data_classification: str
    decision_status: str
    allowed: bool
    reasons: tuple[str, ...]
    missing_approvals: tuple[str, ...]
    approvals: tuple[dict[str, Any], ...]
    created_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "purpose": self.purpose,
            "data_classification": self.data_classification,
            "decision_status": self.decision_status,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "missing_approvals": list(self.missing_approvals),
            "approvals": [dict(approval) for approval in self.approvals],
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "PrivacyApprovalRecord":
        return cls(
            approval_id=str(payload["approval_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            purpose=str(payload["purpose"]),
            data_classification=str(payload["data_classification"]),
            decision_status=str(payload["decision_status"]),
            allowed=bool(payload["allowed"]),
            reasons=tuple(str(reason) for reason in payload.get("reasons", [])),
            missing_approvals=tuple(
                str(approval) for approval in payload.get("missing_approvals", [])
            ),
            approvals=tuple(dict(approval) for approval in payload.get("approvals", [])),
            created_at=str(payload["created_at"]),
        )


@dataclass(frozen=True)
class ReadinessCheckResultRecord:
    result_id: str
    run_id: str
    tenant_id: str
    workspace_id: str
    status: str
    checks: tuple[dict[str, Any], ...]
    artifact_manifest_path: str
    run_summary_path: str
    created_at: str

    @property
    def failed_checks(self) -> tuple[str, ...]:
        return tuple(
            str(check.get("name", ""))
            for check in self.checks
            if not bool(check.get("passed"))
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "status": self.status,
            "checks": [dict(check) for check in self.checks],
            "failed_checks": list(self.failed_checks),
            "artifact_manifest_path": self.artifact_manifest_path,
            "run_summary_path": self.run_summary_path,
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ReadinessCheckResultRecord":
        return cls(
            result_id=str(payload["result_id"]),
            run_id=str(payload["run_id"]),
            tenant_id=str(payload["tenant_id"]),
            workspace_id=str(payload["workspace_id"]),
            status=str(payload["status"]),
            checks=tuple(dict(check) for check in payload.get("checks", [])),
            artifact_manifest_path=str(payload["artifact_manifest_path"]),
            run_summary_path=str(payload["run_summary_path"]),
            created_at=str(payload["created_at"]),
        )


class ProductionStorage:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                pragma foreign_keys = on;

                create table if not exists artifact_manifests (
                    run_id text primary key,
                    environment text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    corpus_version text not null,
                    index_version text not null,
                    payload_json text not null
                );

                create table if not exists evaluation_runs (
                    run_id text primary key,
                    suite text not null,
                    subject text not null,
                    dataset_version text not null,
                    artifact_manifest_path text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists production_audit_events (
                    event_id text primary key,
                    run_id text not null,
                    event_type text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists review_tasks (
                    review_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists connector_health_records (
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    source_id text not null,
                    connector_name text not null,
                    status text not null,
                    checked_at text not null,
                    payload_json text not null,
                    primary key (
                        run_id,
                        source_id,
                        connector_name,
                        checked_at
                    )
                );

                create table if not exists staged_connector_validations (
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    source_id text not null,
                    connector_name text not null,
                    stage text not null,
                    status text not null,
                    checked_at text not null,
                    query text not null,
                    payload_json text not null,
                    primary key (
                        run_id,
                        source_id,
                        connector_name,
                        stage,
                        checked_at,
                        query
                    )
                );

                create table if not exists privacy_approvals (
                    approval_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    purpose text not null,
                    data_classification text not null,
                    decision_status text not null,
                    allowed integer not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists readiness_check_results (
                    result_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    status text not null,
                    created_at text not null,
                    artifact_manifest_path text not null,
                    run_summary_path text not null,
                    payload_json text not null
                );

                create table if not exists evidence_object_records (
                    object_id text primary key,
                    tenant_id text not null,
                    workspace_id text not null,
                    object_kind text not null,
                    object_uri text not null,
                    source_id text not null,
                    document_id text,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists retrieval_index_records (
                    tenant_id text not null,
                    workspace_id text not null,
                    index_version text not null,
                    index_kind text not null,
                    corpus_version text not null,
                    created_at text not null,
                    payload_json text not null,
                    primary key (tenant_id, workspace_id, index_version)
                );

                create table if not exists retrieval_run_records (
                    retrieval_run_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    user_id text not null,
                    topic text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists production_research_memory_records (
                    memory_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    user_id text not null,
                    topic text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists evidence_methodology_runs (
                    methodology_run_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists evidence_methodology_assessment_records (
                    assessment_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    document_id text not null,
                    status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists reviewer_evidence_rating_records (
                    rating_id text primary key,
                    assessment_id text not null,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    reviewer_id text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists external_evidence_grading_request_records (
                    request_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    provider_id text not null,
                    status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists external_evidence_grading_response_records (
                    response_id text primary key,
                    request_id text not null,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    provider_id text not null,
                    status text not null,
                    received_at text not null,
                    payload_json text not null
                );

                create table if not exists production_trust_score_records (
                    trust_score_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    methodology_run_id text,
                    status text not null,
                    overall integer not null,
                    decision_status text not null,
                    export_status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists production_governance_box_records (
                    governance_box_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    trust_score_id text not null,
                    methodology_run_id text,
                    decision_status text not null,
                    export_status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists reviewer_trust_score_override_records (
                    override_id text primary key,
                    trust_score_id text not null,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    reviewer_id text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists external_governance_request_records (
                    request_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    trust_score_id text not null,
                    governance_box_id text not null,
                    provider_id text not null,
                    status text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists external_governance_response_records (
                    response_id text primary key,
                    request_id text not null,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    retrieval_run_id text not null,
                    trust_score_id text not null,
                    governance_box_id text not null,
                    provider_id text not null,
                    status text not null,
                    received_at text not null,
                    payload_json text not null
                );

                create table if not exists research_mcp_plans (
                    plan_id text primary key,
                    run_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    user_id text not null,
                    intended_use text not null,
                    step_count integer not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists research_mcp_tool_calls (
                    call_id text primary key,
                    run_id text not null,
                    plan_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    user_id text not null,
                    tool_id text not null,
                    source_id text not null,
                    connector_name text not null,
                    action text not null,
                    status text not null,
                    request_hash text not null,
                    result_hash text not null,
                    result_count integer not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists research_mcp_replay_records (
                    request_hash text primary key,
                    result_hash text not null,
                    run_id text not null,
                    plan_id text not null,
                    tenant_id text not null,
                    workspace_id text not null,
                    user_id text not null,
                    tool_id text not null,
                    source_id text not null,
                    connector_name text not null,
                    action text not null,
                    created_at text not null,
                    payload_json text not null
                );

                create table if not exists production_metadata (
                    key text primary key,
                    value text not null
                );

                create table if not exists production_migrations (
                    version integer primary key,
                    name text not null,
                    applied_at text not null
                );

                create index if not exists idx_production_audit_events_run_id
                    on production_audit_events(run_id);

                create index if not exists idx_production_audit_events_event_type
                    on production_audit_events(event_type);

                create index if not exists idx_review_tasks_run_id
                    on review_tasks(run_id);

                create index if not exists idx_review_tasks_scope
                    on review_tasks(tenant_id, workspace_id);

                create index if not exists idx_connector_health_run_id
                    on connector_health_records(run_id);

                create index if not exists idx_connector_health_scope
                    on connector_health_records(tenant_id, workspace_id);

                create index if not exists idx_connector_validation_run_id
                    on staged_connector_validations(run_id);

                create index if not exists idx_connector_validation_scope
                    on staged_connector_validations(tenant_id, workspace_id);

                create index if not exists idx_privacy_approvals_run_id
                    on privacy_approvals(run_id);

                create index if not exists idx_privacy_approvals_scope
                    on privacy_approvals(tenant_id, workspace_id);

                create index if not exists idx_readiness_results_run_id
                    on readiness_check_results(run_id);

                create index if not exists idx_readiness_results_scope
                    on readiness_check_results(tenant_id, workspace_id);

                create index if not exists idx_evidence_objects_scope
                    on evidence_object_records(tenant_id, workspace_id);

                create index if not exists idx_evidence_objects_source
                    on evidence_object_records(source_id, document_id);

                create index if not exists idx_retrieval_indexes_scope
                    on retrieval_index_records(tenant_id, workspace_id);

                create index if not exists idx_retrieval_runs_run_id
                    on retrieval_run_records(run_id);

                create index if not exists idx_retrieval_runs_scope
                    on retrieval_run_records(tenant_id, workspace_id, user_id, topic);

                create index if not exists idx_research_memory_run_id
                    on production_research_memory_records(run_id);

                create index if not exists idx_research_memory_scope
                    on production_research_memory_records(tenant_id, workspace_id, user_id, topic);

                create index if not exists idx_evidence_methodology_runs_scope
                    on evidence_methodology_runs(tenant_id, workspace_id, run_id);

                create index if not exists idx_evidence_methodology_assessments_scope
                    on evidence_methodology_assessment_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_evidence_methodology_assessments_document
                    on evidence_methodology_assessment_records(document_id, retrieval_run_id);

                create index if not exists idx_reviewer_evidence_ratings_scope
                    on reviewer_evidence_rating_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_external_evidence_grading_requests_scope
                    on external_evidence_grading_request_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_external_evidence_grading_responses_scope
                    on external_evidence_grading_response_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_production_trust_scores_scope
                    on production_trust_score_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_production_trust_scores_retrieval_run
                    on production_trust_score_records(retrieval_run_id);

                create index if not exists idx_production_governance_boxes_scope
                    on production_governance_box_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_production_governance_boxes_trust_score
                    on production_governance_box_records(trust_score_id);

                create index if not exists idx_reviewer_trust_score_overrides_scope
                    on reviewer_trust_score_override_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_external_governance_requests_scope
                    on external_governance_request_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_external_governance_responses_scope
                    on external_governance_response_records(tenant_id, workspace_id, run_id);

                create index if not exists idx_research_mcp_plans_run_id
                    on research_mcp_plans(run_id);

                create index if not exists idx_research_mcp_plans_scope
                    on research_mcp_plans(tenant_id, workspace_id);

                create index if not exists idx_research_mcp_tool_calls_run_id
                    on research_mcp_tool_calls(run_id);

                create index if not exists idx_research_mcp_tool_calls_scope
                    on research_mcp_tool_calls(tenant_id, workspace_id);

                create index if not exists idx_research_mcp_tool_calls_plan
                    on research_mcp_tool_calls(plan_id);

                create index if not exists idx_research_mcp_replay_scope
                    on research_mcp_replay_records(tenant_id, workspace_id);
                """
            )
            connection.execute(
                """
                insert into production_metadata (key, value)
                values ('schema_version', ?)
                on conflict(key) do update set value = excluded.value
                """,
                (str(PRODUCTION_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    1,
                    BASELINE_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    2,
                    REVIEW_TASKS_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    3,
                    CONNECTOR_HEALTH_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    4,
                    PRIVACY_APPROVAL_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    5,
                    READINESS_RESULT_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    6,
                    EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    7,
                    EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    8,
                    GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.execute(
                """
                insert into production_migrations (version, name, applied_at)
                values (?, ?, ?)
                on conflict(version) do nothing
                """,
                (
                    9,
                    RESEARCH_MCP_MIGRATION_NAME,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_schema_version(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "select value from production_metadata where key = 'schema_version'"
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError("Production schema version is not recorded.")
        return int(row["value"])

    def list_migrations(self) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                select version, name, applied_at
                from production_migrations
                order by version
                """
            ).fetchall()
        finally:
            connection.close()
        return [
            {
                "version": int(row["version"]),
                "name": str(row["name"]),
                "applied_at": str(row["applied_at"]),
            }
            for row in rows
        ]

    def save_artifact_manifest(self, manifest: ArtifactManifest) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into artifact_manifests (
                    run_id,
                    environment,
                    tenant_id,
                    workspace_id,
                    corpus_version,
                    index_version,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id) do update set
                    environment = excluded.environment,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    corpus_version = excluded.corpus_version,
                    index_version = excluded.index_version,
                    payload_json = excluded.payload_json
                """,
                (
                    manifest.run_id,
                    manifest.environment,
                    manifest.tenant_id,
                    manifest.workspace_id,
                    manifest.corpus_version,
                    manifest.index_version,
                    json.dumps(manifest.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_artifact_manifest(self, run_id: str) -> ArtifactManifest:
        connection = self._connect()
        try:
            row = connection.execute(
                "select payload_json from artifact_manifests where run_id = ?",
                (run_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"Unknown artifact manifest run_id: {run_id}")
        return ArtifactManifest.from_json(json.loads(row["payload_json"]))

    def get_artifact_manifest_for_scope(
        self, run_id: str, scope: ProductionScope
    ) -> ArtifactManifest:
        manifest = self.get_artifact_manifest(run_id)
        _require_scope(manifest, scope)
        return manifest

    def list_artifact_manifests(self) -> list[ArtifactManifest]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "select payload_json from artifact_manifests order by run_id"
            ).fetchall()
        finally:
            connection.close()
        return [ArtifactManifest.from_json(json.loads(row["payload_json"])) for row in rows]

    def save_evaluation_run(self, run: EvaluationRun) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into evaluation_runs (
                    run_id,
                    suite,
                    subject,
                    dataset_version,
                    artifact_manifest_path,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id) do update set
                    suite = excluded.suite,
                    subject = excluded.subject,
                    dataset_version = excluded.dataset_version,
                    artifact_manifest_path = excluded.artifact_manifest_path,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    run.run_id,
                    run.suite,
                    run.subject,
                    run.dataset_version,
                    run.artifact_manifest_path,
                    run.created_at,
                    json.dumps(run.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def list_evaluation_runs(self, suite: str | None = None) -> list[EvaluationRun]:
        if suite is None:
            sql = "select payload_json from evaluation_runs order by run_id"
            params: tuple[str, ...] = ()
        else:
            sql = "select payload_json from evaluation_runs where suite = ? order by run_id"
            params = (suite,)
        connection = self._connect()
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        return [EvaluationRun.from_json(json.loads(row["payload_json"])) for row in rows]

    def append_audit_event(self, event: ProductionAuditEvent) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into production_audit_events (
                    event_id,
                    run_id,
                    event_type,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.run_id,
                    event.event_type,
                    event.created_at,
                    json.dumps(event.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Duplicate audit event_id: {event.event_id}") from exc
        finally:
            connection.close()

    def list_audit_events(
        self,
        run_id: str | None = None,
        event_type: str | None = None,
    ) -> list[ProductionAuditEvent]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if event_type is not None:
            conditions.append("event_type = ?")
            params.append(event_type)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"select payload_json from production_audit_events{where_clause} order by created_at, rowid",
                tuple(params),
            ).fetchall()
        finally:
            connection.close()
        return [
            ProductionAuditEvent.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_audit_events_for_scope(
        self,
        scope: ProductionScope,
        run_id: str,
        event_type: str | None = None,
    ) -> list[ProductionAuditEvent]:
        self.get_artifact_manifest_for_scope(run_id, scope)
        return self.list_audit_events(run_id=run_id, event_type=event_type)

    def save_review_task(self, task: ReviewTask) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into review_tasks (
                    review_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(review_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    task.review_id,
                    task.run_id,
                    task.scope.tenant_id,
                    task.scope.workspace_id,
                    task.status.value,
                    task.created_at,
                    json.dumps(task.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_review_task(
        self,
        task: ReviewTask,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_review_task(task)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=task.run_id,
                event_type="review_task_created",
                payload={
                    "review_id": task.review_id,
                    "tenant_id": task.scope.tenant_id,
                    "workspace_id": task.scope.workspace_id,
                    "status": task.status.value,
                    "reason": task.reason,
                },
                created_at=audit_created_at,
            )
        )

    def record_review_decision(
        self,
        task: ReviewTask,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        if task.decision is None:
            raise ValueError("Review decision task must include a decision record.")
        self.save_review_task(task)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=task.run_id,
                event_type="review_decision_recorded",
                payload={
                    "review_id": task.review_id,
                    "tenant_id": task.scope.tenant_id,
                    "workspace_id": task.scope.workspace_id,
                    "status": task.status.value,
                    "reviewer_id": task.decision.reviewer_id,
                    "decision": task.decision.decision.value,
                },
                created_at=audit_created_at,
            )
        )

    def get_review_task(self, review_id: str) -> ReviewTask:
        connection = self._connect()
        try:
            row = connection.execute(
                "select payload_json from review_tasks where review_id = ?",
                (review_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"Unknown review task: {review_id}")
        return ReviewTask.from_json(json.loads(row["payload_json"]))

    def list_review_tasks(self, run_id: str | None = None) -> list[ReviewTask]:
        if run_id is None:
            sql = "select payload_json from review_tasks order by created_at, review_id"
            params: tuple[str, ...] = ()
        else:
            sql = "select payload_json from review_tasks where run_id = ? order by created_at, review_id"
            params = (run_id,)
        connection = self._connect()
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        return [ReviewTask.from_json(json.loads(row["payload_json"])) for row in rows]

    def list_review_tasks_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ReviewTask]:
        tasks = self.list_review_tasks(run_id=run_id)
        for task in tasks:
            _require_review_scope(task, scope)
        return tasks

    def save_connector_health_record(
        self,
        run_id: str,
        scope: ProductionScope,
        record: ConnectorHealthRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into connector_health_records (
                    run_id,
                    tenant_id,
                    workspace_id,
                    source_id,
                    connector_name,
                    status,
                    checked_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(run_id, source_id, connector_name, checked_at) do update set
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    status = excluded.status,
                    payload_json = excluded.payload_json
                """,
                (
                    run_id,
                    scope.tenant_id,
                    scope.workspace_id,
                    record.source_id,
                    record.connector_name,
                    record.status.value,
                    record.checked_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_connector_health(
        self,
        run_id: str,
        scope: ProductionScope,
        record: ConnectorHealthRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_connector_health_record(run_id, scope, record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=run_id,
                event_type="connector_health_recorded",
                payload={
                    "source_id": record.source_id,
                    "connector_name": record.connector_name,
                    "tenant_id": scope.tenant_id,
                    "workspace_id": scope.workspace_id,
                    "status": record.status.value,
                    "checked_at": record.checked_at,
                    "latency_ms": record.latency_ms,
                },
                created_at=audit_created_at,
            )
        )

    def list_connector_health_records(
        self,
        run_id: str | None = None,
    ) -> list[ConnectorHealthRecord]:
        rows = self._list_connector_health_rows(run_id=run_id)
        return [
            ConnectorHealthRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_connector_health_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ConnectorHealthRecord]:
        rows = self._list_connector_health_rows(run_id=run_id)
        for row in rows:
            _require_row_scope(row, scope, "Connector health record")
        return [
            ConnectorHealthRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_staged_connector_validation_record(
        self,
        run_id: str,
        scope: ProductionScope,
        record: StagedConnectorValidationRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into staged_connector_validations (
                    run_id,
                    tenant_id,
                    workspace_id,
                    source_id,
                    connector_name,
                    stage,
                    status,
                    checked_at,
                    query,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(
                    run_id,
                    source_id,
                    connector_name,
                    stage,
                    checked_at,
                    query
                ) do update set
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    status = excluded.status,
                    payload_json = excluded.payload_json
                """,
                (
                    run_id,
                    scope.tenant_id,
                    scope.workspace_id,
                    record.source_id,
                    record.connector_name,
                    record.stage.value,
                    record.status.value,
                    record.checked_at,
                    record.query,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_staged_connector_validation(
        self,
        run_id: str,
        scope: ProductionScope,
        record: StagedConnectorValidationRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_staged_connector_validation_record(run_id, scope, record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=run_id,
                event_type="connector_validation_recorded",
                payload={
                    "source_id": record.source_id,
                    "connector_name": record.connector_name,
                    "tenant_id": scope.tenant_id,
                    "workspace_id": scope.workspace_id,
                    "stage": record.stage.value,
                    "status": record.status.value,
                    "checked_at": record.checked_at,
                    "query": record.query,
                    "document_count": record.document_count,
                },
                created_at=audit_created_at,
            )
        )

    def list_staged_connector_validation_records(
        self,
        run_id: str | None = None,
    ) -> list[StagedConnectorValidationRecord]:
        rows = self._list_staged_connector_validation_rows(run_id=run_id)
        return [
            StagedConnectorValidationRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_staged_connector_validation_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[StagedConnectorValidationRecord]:
        rows = self._list_staged_connector_validation_rows(run_id=run_id)
        for row in rows:
            _require_row_scope(row, scope, "Staged connector validation record")
        return [
            StagedConnectorValidationRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def connector_readiness_for_scope(
        self,
        scope: ProductionScope,
        run_id: str,
    ) -> dict[str, bool]:
        health = self.list_connector_health_records_for_scope(scope, run_id=run_id)
        validations = self.list_staged_connector_validation_records_for_scope(
            scope,
            run_id=run_id,
        )
        return {
            "health_ok": any(record.status == ConnectorHealthStatus.OK for record in health),
            "validation_ok": any(
                record.status == ConnectorHealthStatus.OK
                for record in validations
            ),
        }

    def save_privacy_approval_record(self, record: PrivacyApprovalRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into privacy_approvals (
                    approval_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    purpose,
                    data_classification,
                    decision_status,
                    allowed,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(approval_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    purpose = excluded.purpose,
                    data_classification = excluded.data_classification,
                    decision_status = excluded.decision_status,
                    allowed = excluded.allowed,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.approval_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.purpose,
                    record.data_classification,
                    record.decision_status,
                    1 if record.allowed else 0,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_privacy_approval(
        self,
        record: PrivacyApprovalRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_privacy_approval_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="privacy_approval_recorded",
                payload={
                    "approval_id": record.approval_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "purpose": record.purpose,
                    "data_classification": record.data_classification,
                    "decision_status": record.decision_status,
                    "allowed": record.allowed,
                    "missing_approvals": list(record.missing_approvals),
                },
                created_at=audit_created_at,
            )
        )

    def list_privacy_approval_records(
        self,
        run_id: str | None = None,
    ) -> list[PrivacyApprovalRecord]:
        rows = self._list_privacy_approval_rows(run_id=run_id)
        return [
            PrivacyApprovalRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_privacy_approval_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[PrivacyApprovalRecord]:
        rows = self._list_privacy_approval_rows(run_id=run_id)
        for row in rows:
            _require_row_scope(row, scope, "Privacy approval record")
        return [
            PrivacyApprovalRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_readiness_check_result(
        self,
        record: ReadinessCheckResultRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into readiness_check_results (
                    result_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    status,
                    created_at,
                    artifact_manifest_path,
                    run_summary_path,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(result_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    artifact_manifest_path = excluded.artifact_manifest_path,
                    run_summary_path = excluded.run_summary_path,
                    payload_json = excluded.payload_json
                """,
                (
                    record.result_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.status,
                    record.created_at,
                    record.artifact_manifest_path,
                    record.run_summary_path,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_readiness_check_result(
        self,
        record: ReadinessCheckResultRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_readiness_check_result(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="readiness_check_result_recorded",
                payload={
                    "result_id": record.result_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "status": record.status,
                    "check_count": len(record.checks),
                    "failed_checks": list(record.failed_checks),
                    "artifact_manifest_path": record.artifact_manifest_path,
                    "run_summary_path": record.run_summary_path,
                },
                created_at=audit_created_at,
            )
        )

    def list_readiness_check_results(
        self,
        run_id: str | None = None,
    ) -> list[ReadinessCheckResultRecord]:
        rows = self._list_readiness_check_result_rows(run_id=run_id)
        return [
            ReadinessCheckResultRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_readiness_check_results_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ReadinessCheckResultRecord]:
        rows = self._list_readiness_check_result_rows(run_id=run_id)
        for row in rows:
            _require_row_scope(row, scope, "Readiness check result")
        return [
            ReadinessCheckResultRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]


    def save_evidence_object_record(self, record: EvidenceObjectRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into evidence_object_records (
                    object_id,
                    tenant_id,
                    workspace_id,
                    object_kind,
                    object_uri,
                    source_id,
                    document_id,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(object_id) do update set
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    object_kind = excluded.object_kind,
                    object_uri = excluded.object_uri,
                    source_id = excluded.source_id,
                    document_id = excluded.document_id,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.object_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.object_kind.value,
                    record.object_uri,
                    record.source_id,
                    record.document_id,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_evidence_object(
        self,
        record: EvidenceObjectRecord,
        run_id: str,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_evidence_object_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=run_id,
                event_type="evidence_object_recorded",
                payload={
                    "object_id": record.object_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "object_kind": record.object_kind.value,
                    "source_id": record.source_id,
                    "document_id": record.document_id,
                    "object_uri": record.object_uri,
                    "checksum_sha256": record.checksum_sha256,
                },
                created_at=audit_created_at,
            )
        )

    def list_evidence_object_records(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[EvidenceObjectRecord]:
        rows = self._list_evidence_object_rows(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return [
            EvidenceObjectRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_evidence_object_records_for_scope(
        self,
        scope: ProductionScope,
    ) -> list[EvidenceObjectRecord]:
        rows = self._list_evidence_object_rows(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Evidence object record")
        return [
            EvidenceObjectRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_retrieval_index_record(self, record: RetrievalIndexRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into retrieval_index_records (
                    tenant_id,
                    workspace_id,
                    index_version,
                    index_kind,
                    corpus_version,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(tenant_id, workspace_id, index_version) do update set
                    index_kind = excluded.index_kind,
                    corpus_version = excluded.corpus_version,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.tenant_id,
                    record.workspace_id,
                    record.index_version,
                    record.index_kind.value,
                    record.corpus_version,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_retrieval_index(
        self,
        record: RetrievalIndexRecord,
        run_id: str,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_retrieval_index_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=run_id,
                event_type="retrieval_index_recorded",
                payload={
                    "index_version": record.index_version,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "index_kind": record.index_kind.value,
                    "corpus_version": record.corpus_version,
                    "source_ids": list(record.source_ids),
                    "document_count": record.document_count,
                    "passage_count": record.passage_count,
                },
                created_at=audit_created_at,
            )
        )

    def list_retrieval_index_records(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[RetrievalIndexRecord]:
        rows = self._list_retrieval_index_rows(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        return [
            RetrievalIndexRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_retrieval_index_records_for_scope(
        self,
        scope: ProductionScope,
    ) -> list[RetrievalIndexRecord]:
        rows = self._list_retrieval_index_rows(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Retrieval index record")
        return [
            RetrievalIndexRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def get_retrieval_index_record_for_scope(
        self,
        scope: ProductionScope,
        index_version: str,
    ) -> RetrievalIndexRecord:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                select * from retrieval_index_records
                where tenant_id = ? and workspace_id = ? and index_version = ?
                """,
                (scope.tenant_id, scope.workspace_id, index_version),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"Unknown retrieval index for scope: {index_version}")
        _require_row_scope(row, scope, "Retrieval index record")
        return RetrievalIndexRecord.from_json(json.loads(row["payload_json"]))

    def save_retrieval_run_record(self, record: RetrievalRunRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into retrieval_run_records (
                    retrieval_run_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    topic,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(retrieval_run_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    topic = excluded.topic,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.retrieval_run_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.user_id,
                    record.topic,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_retrieval_run(
        self,
        record: RetrievalRunRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_retrieval_run_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="retrieval_run_recorded",
                payload={
                    "retrieval_run_id": record.retrieval_run_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "user_id": record.user_id,
                    "topic": record.topic,
                    "retrieval_mode": record.retrieval_mode,
                    "index_versions": list(record.index_versions),
                    "retrieved_document_count": len(record.retrieved_document_ids),
                    "top_k": record.top_k,
                },
                created_at=audit_created_at,
            )
        )

    def list_retrieval_run_records(
        self,
        run_id: str | None = None,
    ) -> list[RetrievalRunRecord]:
        rows = self._list_retrieval_run_rows(run_id=run_id)
        return [
            RetrievalRunRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_retrieval_run_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
        user_id: str | None = None,
        topic: str | None = None,
    ) -> list[RetrievalRunRecord]:
        rows = self._list_retrieval_run_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            user_id=user_id,
            topic=topic,
        )
        for row in rows:
            _require_row_scope(row, scope, "Retrieval run record")
        return [
            RetrievalRunRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_production_research_memory_record(
        self,
        record: ProductionResearchMemoryRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into production_research_memory_records (
                    memory_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    topic,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(memory_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    topic = excluded.topic,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.memory_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.user_id,
                    record.topic,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_production_research_memory(
        self,
        record: ProductionResearchMemoryRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_production_research_memory_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="production_research_memory_saved",
                payload={
                    "memory_id": record.memory_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "user_id": record.user_id,
                    "topic": record.topic,
                    "retrieval_run_id": record.retrieval_run_id,
                    "follow_up_decision": record.follow_up_decision.value,
                    "retrieved_document_count": len(record.retrieved_document_ids),
                },
                created_at=audit_created_at,
            )
        )

    def list_production_research_memory_records(
        self,
        run_id: str | None = None,
    ) -> list[ProductionResearchMemoryRecord]:
        rows = self._list_production_research_memory_rows(run_id=run_id)
        return [
            ProductionResearchMemoryRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_production_research_memory_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
        user_id: str | None = None,
        topic: str | None = None,
    ) -> list[ProductionResearchMemoryRecord]:
        rows = self._list_production_research_memory_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            user_id=user_id,
            topic=topic,
        )
        for row in rows:
            _require_row_scope(row, scope, "Production research memory record")
        return [
            ProductionResearchMemoryRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def latest_production_research_memory_for_scope(
        self,
        scope: ProductionScope,
        user_id: str,
        topic: str,
    ) -> ProductionResearchMemoryRecord | None:
        records = self.list_production_research_memory_records_for_scope(
            scope,
            user_id=user_id,
            topic=topic,
        )
        return records[-1] if records else None

    def save_evidence_methodology_run_record(
        self,
        record: EvidenceMethodologyRunRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into evidence_methodology_runs (
                    methodology_run_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(methodology_run_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.methodology_run_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_evidence_methodology_run(
        self,
        record: EvidenceMethodologyRunRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_evidence_methodology_run_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="evidence_methodology_run_recorded",
                payload={
                    "methodology_run_id": record.methodology_run_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "retrieval_run_id": record.retrieval_run_id,
                    "assessment_count": len(record.assessment_ids),
                    "overall_strength_score": record.overall_strength_score,
                    "overall_strength_band": record.overall_strength_band.value,
                    "requires_human_review": record.requires_human_review,
                },
                created_at=audit_created_at,
            )
        )

    def list_evidence_methodology_run_records(
        self,
        run_id: str | None = None,
    ) -> list[EvidenceMethodologyRunRecord]:
        rows = self._list_evidence_methodology_run_rows(run_id=run_id)
        return [
            EvidenceMethodologyRunRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_evidence_methodology_run_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[EvidenceMethodologyRunRecord]:
        rows = self._list_evidence_methodology_run_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Evidence methodology run")
        return [
            EvidenceMethodologyRunRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_evidence_methodology_assessment_record(
        self,
        record: EvidenceMethodologyAssessmentRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into evidence_methodology_assessment_records (
                    assessment_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    document_id,
                    status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(assessment_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    document_id = excluded.document_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.assessment_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.document_id,
                    record.status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_evidence_methodology_assessment(
        self,
        record: EvidenceMethodologyAssessmentRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_evidence_methodology_assessment_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="evidence_methodology_assessment_recorded",
                payload={
                    "assessment_id": record.assessment_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "retrieval_run_id": record.retrieval_run_id,
                    "document_id": record.document_id,
                    "evidence_strength_score": record.evidence_strength_score,
                    "evidence_strength_band": record.evidence_strength_band.value,
                    "assessment_source": record.assessment_source,
                    "requires_human_review": record.requires_human_review,
                },
                created_at=audit_created_at,
            )
        )

    def list_evidence_methodology_assessment_records(
        self,
        run_id: str | None = None,
    ) -> list[EvidenceMethodologyAssessmentRecord]:
        rows = self._list_evidence_methodology_assessment_rows(run_id=run_id)
        return [
            EvidenceMethodologyAssessmentRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_evidence_methodology_assessment_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
        retrieval_run_id: str | None = None,
    ) -> list[EvidenceMethodologyAssessmentRecord]:
        rows = self._list_evidence_methodology_assessment_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            retrieval_run_id=retrieval_run_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Evidence methodology assessment")
        return [
            EvidenceMethodologyAssessmentRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_reviewer_evidence_rating_record(
        self,
        record: ReviewerEvidenceRatingRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into reviewer_evidence_rating_records (
                    rating_id,
                    assessment_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    reviewer_id,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(rating_id) do update set
                    assessment_id = excluded.assessment_id,
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    reviewer_id = excluded.reviewer_id,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.rating_id,
                    record.assessment_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.reviewer_id,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_reviewer_evidence_rating(
        self,
        record: ReviewerEvidenceRatingRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_reviewer_evidence_rating_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="reviewer_evidence_rating_recorded",
                payload={
                    "rating_id": record.rating_id,
                    "assessment_id": record.assessment_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "reviewer_id": record.reviewer_id,
                    "adjusted_strength_score": record.adjusted_strength_score,
                    "adjusted_strength_band": record.adjusted_strength_band.value,
                },
                created_at=audit_created_at,
            )
        )

    def list_reviewer_evidence_rating_records(
        self,
        run_id: str | None = None,
    ) -> list[ReviewerEvidenceRatingRecord]:
        rows = self._list_reviewer_evidence_rating_rows(run_id=run_id)
        return [
            ReviewerEvidenceRatingRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_reviewer_evidence_rating_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ReviewerEvidenceRatingRecord]:
        rows = self._list_reviewer_evidence_rating_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Reviewer evidence rating")
        return [
            ReviewerEvidenceRatingRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_external_evidence_grading_request_record(
        self,
        record: ExternalEvidenceGradingRequestRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into external_evidence_grading_request_records (
                    request_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    provider_id,
                    status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(request_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    provider_id = excluded.provider_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.request_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.provider_id,
                    record.status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_external_evidence_grading_request(
        self,
        record: ExternalEvidenceGradingRequestRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_external_evidence_grading_request_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="external_evidence_grading_request_recorded",
                payload={
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "retrieval_run_id": record.retrieval_run_id,
                    "provider_id": record.provider_id,
                    "status": record.status.value,
                    "request_payload_hash": record.request_payload_hash,
                },
                created_at=audit_created_at,
            )
        )

    def list_external_evidence_grading_request_records(
        self,
        run_id: str | None = None,
    ) -> list[ExternalEvidenceGradingRequestRecord]:
        rows = self._list_external_evidence_grading_request_rows(run_id=run_id)
        return [
            ExternalEvidenceGradingRequestRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_external_evidence_grading_request_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ExternalEvidenceGradingRequestRecord]:
        rows = self._list_external_evidence_grading_request_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "External evidence grading request")
        return [
            ExternalEvidenceGradingRequestRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_external_evidence_grading_response_record(
        self,
        record: ExternalEvidenceGradingResponseRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into external_evidence_grading_response_records (
                    response_id,
                    request_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    provider_id,
                    status,
                    received_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(response_id) do update set
                    request_id = excluded.request_id,
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    provider_id = excluded.provider_id,
                    status = excluded.status,
                    received_at = excluded.received_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.response_id,
                    record.request_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.provider_id,
                    record.status.value,
                    record.received_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_external_evidence_grading_response(
        self,
        record: ExternalEvidenceGradingResponseRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_external_evidence_grading_response_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="external_evidence_grading_response_recorded",
                payload={
                    "response_id": record.response_id,
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "provider_id": record.provider_id,
                    "status": record.status.value,
                    "assessment_count": len(record.assessment_ids),
                    "webhook_signature_valid": record.webhook_signature_valid,
                },
                created_at=audit_created_at,
            )
        )

    def list_external_evidence_grading_response_records(
        self,
        run_id: str | None = None,
    ) -> list[ExternalEvidenceGradingResponseRecord]:
        rows = self._list_external_evidence_grading_response_rows(run_id=run_id)
        return [
            ExternalEvidenceGradingResponseRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_external_evidence_grading_response_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ExternalEvidenceGradingResponseRecord]:
        rows = self._list_external_evidence_grading_response_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "External evidence grading response")
        return [
            ExternalEvidenceGradingResponseRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_production_trust_score_record(
        self,
        record: ProductionTrustScoreRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into production_trust_score_records (
                    trust_score_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    methodology_run_id,
                    status,
                    overall,
                    decision_status,
                    export_status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(trust_score_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    methodology_run_id = excluded.methodology_run_id,
                    status = excluded.status,
                    overall = excluded.overall,
                    decision_status = excluded.decision_status,
                    export_status = excluded.export_status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.trust_score_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.methodology_run_id,
                    record.status.value,
                    record.overall,
                    record.decision_status.value,
                    record.export_status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_production_trust_score(
        self,
        record: ProductionTrustScoreRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_production_trust_score_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="production_trust_score_recorded",
                payload={
                    "trust_score_id": record.trust_score_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "retrieval_run_id": record.retrieval_run_id,
                    "methodology_run_id": record.methodology_run_id,
                    "overall": record.overall,
                    "decision_status": record.decision_status.value,
                    "export_status": record.export_status.value,
                    "review_required": record.review_required,
                },
                created_at=audit_created_at,
            )
        )

    def list_production_trust_score_records(
        self,
        run_id: str | None = None,
    ) -> list[ProductionTrustScoreRecord]:
        rows = self._list_production_trust_score_rows(run_id=run_id)
        return [
            ProductionTrustScoreRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_production_trust_score_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ProductionTrustScoreRecord]:
        rows = self._list_production_trust_score_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Production trust score")
        return [
            ProductionTrustScoreRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_production_governance_box_record(
        self,
        record: ProductionGovernanceBoxRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into production_governance_box_records (
                    governance_box_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    trust_score_id,
                    methodology_run_id,
                    decision_status,
                    export_status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(governance_box_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    trust_score_id = excluded.trust_score_id,
                    methodology_run_id = excluded.methodology_run_id,
                    decision_status = excluded.decision_status,
                    export_status = excluded.export_status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.governance_box_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.trust_score_id,
                    record.methodology_run_id,
                    record.decision_status.value,
                    record.export_status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_production_governance_box(
        self,
        record: ProductionGovernanceBoxRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_production_governance_box_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="production_governance_box_recorded",
                payload={
                    "governance_box_id": record.governance_box_id,
                    "trust_score_id": record.trust_score_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "decision_status": record.decision_status.value,
                    "export_status": record.export_status.value,
                    "human_review_required": record.human_review_required,
                    "audit_id": record.audit_id,
                },
                created_at=audit_created_at,
            )
        )

    def list_production_governance_box_records(
        self,
        run_id: str | None = None,
    ) -> list[ProductionGovernanceBoxRecord]:
        rows = self._list_production_governance_box_rows(run_id=run_id)
        return [
            ProductionGovernanceBoxRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_production_governance_box_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ProductionGovernanceBoxRecord]:
        rows = self._list_production_governance_box_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Production governance box")
        return [
            ProductionGovernanceBoxRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_reviewer_trust_score_override_record(
        self,
        record: ReviewerTrustScoreOverrideRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into reviewer_trust_score_override_records (
                    override_id,
                    trust_score_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    reviewer_id,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(override_id) do update set
                    trust_score_id = excluded.trust_score_id,
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    reviewer_id = excluded.reviewer_id,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.override_id,
                    record.trust_score_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.reviewer_id,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_reviewer_trust_score_override(
        self,
        record: ReviewerTrustScoreOverrideRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_reviewer_trust_score_override_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="reviewer_trust_score_override_recorded",
                payload={
                    "override_id": record.override_id,
                    "trust_score_id": record.trust_score_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "reviewer_id": record.reviewer_id,
                    "adjusted_overall": record.adjusted_overall,
                    "adjusted_decision_status": record.adjusted_decision_status.value,
                },
                created_at=audit_created_at,
            )
        )

    def list_reviewer_trust_score_override_records(
        self,
        run_id: str | None = None,
    ) -> list[ReviewerTrustScoreOverrideRecord]:
        rows = self._list_reviewer_trust_score_override_rows(run_id=run_id)
        return [
            ReviewerTrustScoreOverrideRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_reviewer_trust_score_override_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ReviewerTrustScoreOverrideRecord]:
        rows = self._list_reviewer_trust_score_override_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Reviewer trust score override")
        return [
            ReviewerTrustScoreOverrideRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_external_governance_request_record(
        self,
        record: ExternalGovernanceRequestRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into external_governance_request_records (
                    request_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    trust_score_id,
                    governance_box_id,
                    provider_id,
                    status,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(request_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    trust_score_id = excluded.trust_score_id,
                    governance_box_id = excluded.governance_box_id,
                    provider_id = excluded.provider_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.request_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.trust_score_id,
                    record.governance_box_id,
                    record.provider_id,
                    record.status.value,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_external_governance_request(
        self,
        record: ExternalGovernanceRequestRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_external_governance_request_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="external_governance_request_recorded",
                payload={
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "retrieval_run_id": record.retrieval_run_id,
                    "trust_score_id": record.trust_score_id,
                    "governance_box_id": record.governance_box_id,
                    "provider_id": record.provider_id,
                    "status": record.status.value,
                    "request_payload_hash": record.request_payload_hash,
                },
                created_at=audit_created_at,
            )
        )

    def list_external_governance_request_records(
        self,
        run_id: str | None = None,
    ) -> list[ExternalGovernanceRequestRecord]:
        rows = self._list_external_governance_request_rows(run_id=run_id)
        return [
            ExternalGovernanceRequestRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_external_governance_request_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ExternalGovernanceRequestRecord]:
        rows = self._list_external_governance_request_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "External governance request")
        return [
            ExternalGovernanceRequestRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_external_governance_response_record(
        self,
        record: ExternalGovernanceResponseRecord,
    ) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into external_governance_response_records (
                    response_id,
                    request_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    retrieval_run_id,
                    trust_score_id,
                    governance_box_id,
                    provider_id,
                    status,
                    received_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(response_id) do update set
                    request_id = excluded.request_id,
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    retrieval_run_id = excluded.retrieval_run_id,
                    trust_score_id = excluded.trust_score_id,
                    governance_box_id = excluded.governance_box_id,
                    provider_id = excluded.provider_id,
                    status = excluded.status,
                    received_at = excluded.received_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.response_id,
                    record.request_id,
                    record.run_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.retrieval_run_id,
                    record.trust_score_id,
                    record.governance_box_id,
                    record.provider_id,
                    record.status.value,
                    record.received_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_external_governance_response(
        self,
        record: ExternalGovernanceResponseRecord,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_external_governance_response_record(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=record.run_id,
                event_type="external_governance_response_recorded",
                payload={
                    "response_id": record.response_id,
                    "request_id": record.request_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "trust_score_id": record.trust_score_id,
                    "governance_box_id": record.governance_box_id,
                    "provider_id": record.provider_id,
                    "status": record.status.value,
                    "external_decision_status": record.external_decision_status.value
                    if record.external_decision_status is not None
                    else None,
                    "external_export_status": record.external_export_status.value
                    if record.external_export_status is not None
                    else None,
                    "webhook_signature_valid": record.webhook_signature_valid,
                },
                created_at=audit_created_at,
            )
        )

    def list_external_governance_response_records(
        self,
        run_id: str | None = None,
    ) -> list[ExternalGovernanceResponseRecord]:
        rows = self._list_external_governance_response_rows(run_id=run_id)
        return [
            ExternalGovernanceResponseRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def list_external_governance_response_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ExternalGovernanceResponseRecord]:
        rows = self._list_external_governance_response_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "External governance response")
        return [
            ExternalGovernanceResponseRecord.from_json(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save_research_mcp_plan(self, plan: SearchPlan) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into research_mcp_plans (
                    plan_id,
                    run_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    intended_use,
                    step_count,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(plan_id) do update set
                    run_id = excluded.run_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    intended_use = excluded.intended_use,
                    step_count = excluded.step_count,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    plan.plan_id,
                    plan.run_id,
                    plan.scope.tenant_id,
                    plan.scope.workspace_id,
                    plan.scope.user_id,
                    plan.intended_use,
                    len(plan.steps),
                    plan.created_at,
                    json.dumps(plan.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_research_mcp_plan(
        self,
        plan: SearchPlan,
        audit_event_id: str,
        audit_created_at: str,
    ) -> None:
        self.save_research_mcp_plan(plan)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=audit_event_id,
                run_id=plan.run_id,
                event_type="research_mcp_plan_recorded",
                payload={
                    "plan_id": plan.plan_id,
                    "tenant_id": plan.scope.tenant_id,
                    "workspace_id": plan.scope.workspace_id,
                    "user_id": plan.scope.user_id,
                    "intended_use": plan.intended_use,
                    "step_count": len(plan.steps),
                    "tool_ids": sorted({step.tool_id for step in plan.steps}),
                    "source_ids": sorted({step.source_id for step in plan.steps}),
                    "policy_version": plan.policy_version,
                },
                created_at=audit_created_at,
            )
        )

    def get_research_mcp_plan(self, plan_id: str) -> SearchPlan:
        connection = self._connect()
        try:
            row = connection.execute(
                "select payload_json from research_mcp_plans where plan_id = ?",
                (plan_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"Unknown Research MCP plan_id: {plan_id}")
        return SearchPlan.from_json(json.loads(row["payload_json"]))

    def get_research_mcp_plan_for_scope(
        self,
        plan_id: str,
        scope: ProductionScope,
    ) -> SearchPlan:
        plan = self.get_research_mcp_plan(plan_id)
        if plan.scope.tenant_id != scope.tenant_id or plan.scope.workspace_id != scope.workspace_id:
            raise PermissionError("Research MCP plan is outside the requested tenant/workspace scope.")
        return plan

    def list_research_mcp_plans(self, run_id: str | None = None) -> list[SearchPlan]:
        rows = self._list_research_mcp_plan_rows(run_id=run_id)
        return [SearchPlan.from_json(json.loads(row["payload_json"])) for row in rows]

    def list_research_mcp_plans_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[SearchPlan]:
        rows = self._list_research_mcp_plan_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Research MCP plan")
        return [SearchPlan.from_json(json.loads(row["payload_json"])) for row in rows]

    def save_research_mcp_tool_call(self, record: ToolCallAuditRecord) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into research_mcp_tool_calls (
                    call_id,
                    run_id,
                    plan_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    tool_id,
                    source_id,
                    connector_name,
                    action,
                    status,
                    request_hash,
                    result_hash,
                    result_count,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(call_id) do update set
                    run_id = excluded.run_id,
                    plan_id = excluded.plan_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    tool_id = excluded.tool_id,
                    source_id = excluded.source_id,
                    connector_name = excluded.connector_name,
                    action = excluded.action,
                    status = excluded.status,
                    request_hash = excluded.request_hash,
                    result_hash = excluded.result_hash,
                    result_count = excluded.result_count,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.call_id,
                    record.run_id,
                    record.plan_id,
                    record.tenant_id,
                    record.workspace_id,
                    record.user_id,
                    record.tool_id,
                    record.source_id,
                    record.connector_name,
                    record.action,
                    record.status,
                    record.request_hash,
                    record.result_hash,
                    record.result_count,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def record_research_mcp_tool_call(self, record: ToolCallAuditRecord) -> None:
        self.save_research_mcp_tool_call(record)
        self.append_audit_event(
            ProductionAuditEvent(
                event_id=f"audit-{record.call_id}",
                run_id=record.run_id,
                event_type="research_mcp_tool_call_recorded",
                payload={
                    "call_id": record.call_id,
                    "plan_id": record.plan_id,
                    "tenant_id": record.tenant_id,
                    "workspace_id": record.workspace_id,
                    "user_id": record.user_id,
                    "tool_id": record.tool_id,
                    "source_id": record.source_id,
                    "connector_name": record.connector_name,
                    "action": record.action,
                    "status": record.status,
                    "request_hash": record.request_hash,
                    "result_hash": record.result_hash,
                    "result_count": record.result_count,
                    "replayed": record.replayed,
                    "policy_version": record.policy_version,
                },
                created_at=record.created_at,
            )
        )

    def list_research_mcp_tool_calls(
        self,
        run_id: str | None = None,
        plan_id: str | None = None,
    ) -> list[ToolCallAuditRecord]:
        rows = self._list_research_mcp_tool_call_rows(run_id=run_id, plan_id=plan_id)
        return [ToolCallAuditRecord.from_json(json.loads(row["payload_json"])) for row in rows]

    def list_research_mcp_tool_calls_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
        plan_id: str | None = None,
    ) -> list[ToolCallAuditRecord]:
        rows = self._list_research_mcp_tool_call_rows(
            run_id=run_id,
            plan_id=plan_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Research MCP tool call")
        return [ToolCallAuditRecord.from_json(json.loads(row["payload_json"])) for row in rows]

    def save_research_mcp_replay_record(self, record: ToolCallReplayRecord) -> None:
        request_payload = dict(record.request_payload)
        scope_payload = dict(request_payload.get("scope", {}))
        run_id = str(request_payload.get("run_id", ""))
        plan_id = str(request_payload.get("plan_id", ""))
        tenant_id = str(scope_payload.get("tenant_id", ""))
        workspace_id = str(scope_payload.get("workspace_id", ""))
        user_id = str(scope_payload.get("user_id", ""))
        tool_id = str(request_payload.get("tool_id", ""))
        source_id = str(request_payload.get("source_id", ""))
        connector_name = str(request_payload.get("connector_name", ""))
        action = str(request_payload.get("action", ""))
        connection = self._connect()
        try:
            connection.execute(
                """
                insert into research_mcp_replay_records (
                    request_hash,
                    result_hash,
                    run_id,
                    plan_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    tool_id,
                    source_id,
                    connector_name,
                    action,
                    created_at,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(request_hash) do update set
                    result_hash = excluded.result_hash,
                    run_id = excluded.run_id,
                    plan_id = excluded.plan_id,
                    tenant_id = excluded.tenant_id,
                    workspace_id = excluded.workspace_id,
                    user_id = excluded.user_id,
                    tool_id = excluded.tool_id,
                    source_id = excluded.source_id,
                    connector_name = excluded.connector_name,
                    action = excluded.action,
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (
                    record.request_hash,
                    record.result_hash,
                    run_id,
                    plan_id,
                    tenant_id,
                    workspace_id,
                    user_id,
                    tool_id,
                    source_id,
                    connector_name,
                    action,
                    record.created_at,
                    json.dumps(record.to_json(), sort_keys=True),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def get_research_mcp_replay_record(
        self,
        request_hash: str,
        scope: ProductionScope | None = None,
    ) -> ToolCallReplayRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "select * from research_mcp_replay_records where request_hash = ?",
                (request_hash,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        if scope is not None:
            _require_row_scope(row, scope, "Research MCP replay record")
        return ToolCallReplayRecord.from_json(json.loads(row["payload_json"]))

    def list_research_mcp_replay_records(
        self,
        run_id: str | None = None,
    ) -> list[ToolCallReplayRecord]:
        rows = self._list_research_mcp_replay_rows(run_id=run_id)
        return [ToolCallReplayRecord.from_json(json.loads(row["payload_json"])) for row in rows]

    def list_research_mcp_replay_records_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> list[ToolCallReplayRecord]:
        rows = self._list_research_mcp_replay_rows(
            run_id=run_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        for row in rows:
            _require_row_scope(row, scope, "Research MCP replay record")
        return [ToolCallReplayRecord.from_json(json.loads(row["payload_json"])) for row in rows]

    def research_mcp_readiness_for_scope(
        self,
        scope: ProductionScope,
        run_id: str | None = None,
    ) -> dict[str, bool]:
        return {
            "plan_ok": bool(self.list_research_mcp_plans_for_scope(scope, run_id=run_id)),
            "tool_call_ok": bool(self.list_research_mcp_tool_calls_for_scope(scope, run_id=run_id)),
            "replay_ok": bool(self.list_research_mcp_replay_records_for_scope(scope, run_id=run_id)),
        }


    def export_backup(self) -> dict[str, Any]:
        return {
            "backup_schema_version": 1,
            "production_schema_version": self.get_schema_version(),
            "production_migrations": self.list_migrations(),
            "artifact_manifests": [
                manifest.to_json() for manifest in self.list_artifact_manifests()
            ],
            "evaluation_runs": [
                run.to_json() for run in self.list_evaluation_runs()
            ],
            "review_tasks": [
                task.to_json() for task in self.list_review_tasks()
            ],
            "connector_health_records": self._connector_health_backup_payloads(),
            "connector_validation_records": self._connector_validation_backup_payloads(),
            "privacy_approval_records": [
                record.to_json() for record in self.list_privacy_approval_records()
            ],
            "readiness_check_results": [
                record.to_json() for record in self.list_readiness_check_results()
            ],
            "evidence_object_records": [
                record.to_json() for record in self.list_evidence_object_records()
            ],
            "retrieval_index_records": [
                record.to_json() for record in self.list_retrieval_index_records()
            ],
            "retrieval_run_records": [
                record.to_json() for record in self.list_retrieval_run_records()
            ],
            "production_research_memory_records": [
                record.to_json()
                for record in self.list_production_research_memory_records()
            ],
            "evidence_methodology_run_records": [
                record.to_json() for record in self.list_evidence_methodology_run_records()
            ],
            "evidence_methodology_assessment_records": [
                record.to_json()
                for record in self.list_evidence_methodology_assessment_records()
            ],
            "reviewer_evidence_rating_records": [
                record.to_json() for record in self.list_reviewer_evidence_rating_records()
            ],
            "external_evidence_grading_request_records": [
                record.to_json()
                for record in self.list_external_evidence_grading_request_records()
            ],
            "external_evidence_grading_response_records": [
                record.to_json()
                for record in self.list_external_evidence_grading_response_records()
            ],
            "production_trust_score_records": [
                record.to_json() for record in self.list_production_trust_score_records()
            ],
            "production_governance_box_records": [
                record.to_json() for record in self.list_production_governance_box_records()
            ],
            "reviewer_trust_score_override_records": [
                record.to_json()
                for record in self.list_reviewer_trust_score_override_records()
            ],
            "external_governance_request_records": [
                record.to_json() for record in self.list_external_governance_request_records()
            ],
            "external_governance_response_records": [
                record.to_json() for record in self.list_external_governance_response_records()
            ],
            "research_mcp_plans": [
                plan.to_json() for plan in self.list_research_mcp_plans()
            ],
            "research_mcp_tool_calls": [
                record.to_json() for record in self.list_research_mcp_tool_calls()
            ],
            "research_mcp_replay_records": [
                record.to_json() for record in self.list_research_mcp_replay_records()
            ],
            "audit_events": [
                event.to_json() for event in self.list_audit_events()
            ],
        }

    def restore_backup(self, payload: dict[str, Any]) -> dict[str, int]:
        if payload.get("backup_schema_version") != 1:
            raise ValueError("Unsupported production backup schema version.")
        if payload.get("production_schema_version") != PRODUCTION_SCHEMA_VERSION:
            raise ValueError("Unsupported production storage schema version.")
        self.initialize()
        self._restore_migrations(payload.get("production_migrations", []))
        artifact_manifests = payload.get("artifact_manifests", [])
        evaluation_runs = payload.get("evaluation_runs", [])
        review_tasks = payload.get("review_tasks", [])
        connector_health_records = payload.get("connector_health_records", [])
        connector_validation_records = payload.get("connector_validation_records", [])
        privacy_approval_records = payload.get("privacy_approval_records", [])
        readiness_check_results = payload.get("readiness_check_results", [])
        evidence_object_records = payload.get("evidence_object_records", [])
        retrieval_index_records = payload.get("retrieval_index_records", [])
        retrieval_run_records = payload.get("retrieval_run_records", [])
        production_research_memory_records = payload.get(
            "production_research_memory_records",
            [],
        )
        evidence_methodology_run_records = payload.get(
            "evidence_methodology_run_records",
            [],
        )
        evidence_methodology_assessment_records = payload.get(
            "evidence_methodology_assessment_records",
            [],
        )
        reviewer_evidence_rating_records = payload.get(
            "reviewer_evidence_rating_records",
            [],
        )
        external_evidence_grading_request_records = payload.get(
            "external_evidence_grading_request_records",
            [],
        )
        external_evidence_grading_response_records = payload.get(
            "external_evidence_grading_response_records",
            [],
        )
        production_trust_score_records = payload.get(
            "production_trust_score_records",
            [],
        )
        production_governance_box_records = payload.get(
            "production_governance_box_records",
            [],
        )
        reviewer_trust_score_override_records = payload.get(
            "reviewer_trust_score_override_records",
            [],
        )
        external_governance_request_records = payload.get(
            "external_governance_request_records",
            [],
        )
        external_governance_response_records = payload.get(
            "external_governance_response_records",
            [],
        )
        research_mcp_plans = payload.get("research_mcp_plans", [])
        research_mcp_tool_calls = payload.get("research_mcp_tool_calls", [])
        research_mcp_replay_records = payload.get("research_mcp_replay_records", [])
        audit_events = payload.get("audit_events", [])
        for manifest_payload in artifact_manifests:
            self.save_artifact_manifest(ArtifactManifest.from_json(manifest_payload))
        for run_payload in evaluation_runs:
            self.save_evaluation_run(EvaluationRun.from_json(run_payload))
        for task_payload in review_tasks:
            self.save_review_task(ReviewTask.from_json(task_payload))
        for record_payload in connector_health_records:
            self.save_connector_health_record(
                run_id=str(record_payload["run_id"]),
                scope=ProductionScope(
                    tenant_id=str(record_payload["tenant_id"]),
                    workspace_id=str(record_payload["workspace_id"]),
                ),
                record=ConnectorHealthRecord.from_json(record_payload),
            )
        for record_payload in connector_validation_records:
            self.save_staged_connector_validation_record(
                run_id=str(record_payload["run_id"]),
                scope=ProductionScope(
                    tenant_id=str(record_payload["tenant_id"]),
                    workspace_id=str(record_payload["workspace_id"]),
                ),
                record=StagedConnectorValidationRecord.from_json(record_payload),
            )
        for record_payload in privacy_approval_records:
            self.save_privacy_approval_record(
                PrivacyApprovalRecord.from_json(record_payload)
            )
        for record_payload in readiness_check_results:
            self.save_readiness_check_result(
                ReadinessCheckResultRecord.from_json(record_payload)
            )
        for record_payload in evidence_object_records:
            self.save_evidence_object_record(
                EvidenceObjectRecord.from_json(record_payload)
            )
        for record_payload in retrieval_index_records:
            self.save_retrieval_index_record(
                RetrievalIndexRecord.from_json(record_payload)
            )
        for record_payload in retrieval_run_records:
            self.save_retrieval_run_record(
                RetrievalRunRecord.from_json(record_payload)
            )
        for record_payload in production_research_memory_records:
            self.save_production_research_memory_record(
                ProductionResearchMemoryRecord.from_json(record_payload)
            )
        for record_payload in evidence_methodology_run_records:
            self.save_evidence_methodology_run_record(
                EvidenceMethodologyRunRecord.from_json(record_payload)
            )
        for record_payload in evidence_methodology_assessment_records:
            self.save_evidence_methodology_assessment_record(
                EvidenceMethodologyAssessmentRecord.from_json(record_payload)
            )
        for record_payload in reviewer_evidence_rating_records:
            self.save_reviewer_evidence_rating_record(
                ReviewerEvidenceRatingRecord.from_json(record_payload)
            )
        for record_payload in external_evidence_grading_request_records:
            self.save_external_evidence_grading_request_record(
                ExternalEvidenceGradingRequestRecord.from_json(record_payload)
            )
        for record_payload in external_evidence_grading_response_records:
            self.save_external_evidence_grading_response_record(
                ExternalEvidenceGradingResponseRecord.from_json(record_payload)
            )
        for record_payload in production_trust_score_records:
            self.save_production_trust_score_record(
                ProductionTrustScoreRecord.from_json(record_payload)
            )
        for record_payload in production_governance_box_records:
            self.save_production_governance_box_record(
                ProductionGovernanceBoxRecord.from_json(record_payload)
            )
        for record_payload in reviewer_trust_score_override_records:
            self.save_reviewer_trust_score_override_record(
                ReviewerTrustScoreOverrideRecord.from_json(record_payload)
            )
        for record_payload in external_governance_request_records:
            self.save_external_governance_request_record(
                ExternalGovernanceRequestRecord.from_json(record_payload)
            )
        for record_payload in external_governance_response_records:
            self.save_external_governance_response_record(
                ExternalGovernanceResponseRecord.from_json(record_payload)
            )
        for plan_payload in research_mcp_plans:
            self.save_research_mcp_plan(SearchPlan.from_json(plan_payload))
        for record_payload in research_mcp_tool_calls:
            self.save_research_mcp_tool_call(ToolCallAuditRecord.from_json(record_payload))
        for record_payload in research_mcp_replay_records:
            self.save_research_mcp_replay_record(ToolCallReplayRecord.from_json(record_payload))
        for event_payload in audit_events:
            self.append_audit_event(ProductionAuditEvent.from_json(event_payload))
        return {
            "artifact_manifest_count": len(artifact_manifests),
            "evaluation_run_count": len(evaluation_runs),
            "review_task_count": len(review_tasks),
            "connector_health_record_count": len(connector_health_records),
            "connector_validation_record_count": len(connector_validation_records),
            "privacy_approval_record_count": len(privacy_approval_records),
            "readiness_check_result_count": len(readiness_check_results),
            "evidence_object_record_count": len(evidence_object_records),
            "retrieval_index_record_count": len(retrieval_index_records),
            "retrieval_run_record_count": len(retrieval_run_records),
            "production_research_memory_record_count": len(
                production_research_memory_records
            ),
            "evidence_methodology_run_record_count": len(
                evidence_methodology_run_records
            ),
            "evidence_methodology_assessment_record_count": len(
                evidence_methodology_assessment_records
            ),
            "reviewer_evidence_rating_record_count": len(
                reviewer_evidence_rating_records
            ),
            "external_evidence_grading_request_record_count": len(
                external_evidence_grading_request_records
            ),
            "external_evidence_grading_response_record_count": len(
                external_evidence_grading_response_records
            ),
            "production_trust_score_record_count": len(
                production_trust_score_records
            ),
            "production_governance_box_record_count": len(
                production_governance_box_records
            ),
            "reviewer_trust_score_override_record_count": len(
                reviewer_trust_score_override_records
            ),
            "external_governance_request_record_count": len(
                external_governance_request_records
            ),
            "external_governance_response_record_count": len(
                external_governance_response_records
            ),
            "research_mcp_plan_count": len(research_mcp_plans),
            "research_mcp_tool_call_count": len(research_mcp_tool_calls),
            "research_mcp_replay_record_count": len(research_mcp_replay_records),
            "audit_event_count": len(audit_events),
        }

    def _restore_migrations(self, migrations: list[dict[str, Any]]) -> None:
        connection = self._connect()
        try:
            for migration in migrations:
                connection.execute(
                    """
                    insert into production_migrations (version, name, applied_at)
                    values (?, ?, ?)
                    on conflict(version) do update set
                        name = excluded.name,
                        applied_at = excluded.applied_at
                    """,
                    (
                        int(migration["version"]),
                        str(migration["name"]),
                        str(migration["applied_at"]),
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def _list_connector_health_rows(
        self,
        run_id: str | None = None,
    ) -> list[sqlite3.Row]:
        if run_id is None:
            sql = """
                select * from connector_health_records
                order by checked_at, source_id, connector_name
            """
            params: tuple[str, ...] = ()
        else:
            sql = """
                select * from connector_health_records
                where run_id = ?
                order by checked_at, source_id, connector_name
            """
            params = (run_id,)
        connection = self._connect()
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    def _list_staged_connector_validation_rows(
        self,
        run_id: str | None = None,
    ) -> list[sqlite3.Row]:
        if run_id is None:
            sql = """
                select * from staged_connector_validations
                order by checked_at, source_id, connector_name, stage, query
            """
            params: tuple[str, ...] = ()
        else:
            sql = """
                select * from staged_connector_validations
                where run_id = ?
                order by checked_at, source_id, connector_name, stage, query
            """
            params = (run_id,)
        connection = self._connect()
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    def _list_privacy_approval_rows(
        self,
        run_id: str | None = None,
    ) -> list[sqlite3.Row]:
        if run_id is None:
            sql = """
                select * from privacy_approvals
                order by created_at, approval_id
            """
            params: tuple[str, ...] = ()
        else:
            sql = """
                select * from privacy_approvals
                where run_id = ?
                order by created_at, approval_id
            """
            params = (run_id,)
        connection = self._connect()
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    def _list_readiness_check_result_rows(
        self,
        run_id: str | None = None,
    ) -> list[sqlite3.Row]:
        if run_id is None:
            sql = """
                select * from readiness_check_results
                order by created_at, result_id
            """
            params: tuple[str, ...] = ()
        else:
            sql = """
                select * from readiness_check_results
                where run_id = ?
                order by created_at, result_id
            """
            params = (run_id,)
        connection = self._connect()
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()


    def _list_evidence_object_rows(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from evidence_object_records{where_clause}
                order by created_at, object_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_retrieval_index_rows(
        self,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from retrieval_index_records{where_clause}
                order by created_at, index_version
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_retrieval_run_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        topic: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if topic is not None:
            conditions.append("topic = ?")
            params.append(topic)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from retrieval_run_records{where_clause}
                order by created_at, retrieval_run_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_production_research_memory_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        user_id: str | None = None,
        topic: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if topic is not None:
            conditions.append("topic = ?")
            params.append(topic)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from production_research_memory_records{where_clause}
                order by created_at, memory_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_evidence_methodology_run_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from evidence_methodology_runs{where_clause}
                order by created_at, methodology_run_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_evidence_methodology_assessment_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        retrieval_run_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        if retrieval_run_id is not None:
            conditions.append("retrieval_run_id = ?")
            params.append(retrieval_run_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from evidence_methodology_assessment_records{where_clause}
                order by created_at, assessment_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_reviewer_evidence_rating_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from reviewer_evidence_rating_records{where_clause}
                order by created_at, rating_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_external_evidence_grading_request_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from external_evidence_grading_request_records{where_clause}
                order by created_at, request_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_external_evidence_grading_response_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from external_evidence_grading_response_records{where_clause}
                order by received_at, response_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_production_trust_score_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from production_trust_score_records{where_clause}
                order by created_at, trust_score_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_production_governance_box_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from production_governance_box_records{where_clause}
                order by created_at, governance_box_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_reviewer_trust_score_override_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from reviewer_trust_score_override_records{where_clause}
                order by created_at, override_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_external_governance_request_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from external_governance_request_records{where_clause}
                order by created_at, request_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_external_governance_response_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from external_governance_response_records{where_clause}
                order by received_at, response_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_research_mcp_plan_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from research_mcp_plans{where_clause}
                order by created_at, plan_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_research_mcp_tool_call_rows(
        self,
        run_id: str | None = None,
        plan_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if plan_id is not None:
            conditions.append("plan_id = ?")
            params.append(plan_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from research_mcp_tool_calls{where_clause}
                order by created_at, call_id
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()

    def _list_research_mcp_replay_rows(
        self,
        run_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[sqlite3.Row]:
        conditions: list[str] = []
        params: list[str] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(run_id)
        if tenant_id is not None:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if workspace_id is not None:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where_clause = f" where {' and '.join(conditions)}" if conditions else ""
        connection = self._connect()
        try:
            return connection.execute(
                f"""
                select * from research_mcp_replay_records{where_clause}
                order by created_at, request_hash
                """,
                tuple(params),
            ).fetchall()
        finally:
            connection.close()


    def _connector_health_backup_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for row in self._list_connector_health_rows():
            record_payload = ConnectorHealthRecord.from_json(
                json.loads(row["payload_json"])
            ).to_json()
            payloads.append(
                {
                    "run_id": str(row["run_id"]),
                    "tenant_id": str(row["tenant_id"]),
                    "workspace_id": str(row["workspace_id"]),
                    **record_payload,
                }
            )
        return payloads

    def _connector_validation_backup_payloads(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for row in self._list_staged_connector_validation_rows():
            record_payload = StagedConnectorValidationRecord.from_json(
                json.loads(row["payload_json"])
            ).to_json()
            payloads.append(
                {
                    "run_id": str(row["run_id"]),
                    "tenant_id": str(row["tenant_id"]),
                    "workspace_id": str(row["workspace_id"]),
                    **record_payload,
                }
            )
        return payloads

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def _require_scope(manifest: ArtifactManifest, scope: ProductionScope) -> None:
    if manifest.tenant_id != scope.tenant_id or manifest.workspace_id != scope.workspace_id:
        raise PermissionError(
            "Artifact manifest is outside the requested tenant/workspace scope."
        )


def _require_review_scope(task: ReviewTask, scope: ProductionScope) -> None:
    if task.scope.tenant_id != scope.tenant_id or task.scope.workspace_id != scope.workspace_id:
        raise PermissionError(
            "Review task is outside the requested tenant/workspace scope."
        )


def _require_row_scope(
    row: sqlite3.Row,
    scope: ProductionScope,
    resource_name: str,
) -> None:
    if row["tenant_id"] != scope.tenant_id or row["workspace_id"] != scope.workspace_id:
        raise PermissionError(
            f"{resource_name} is outside the requested tenant/workspace scope."
        )
