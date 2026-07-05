from pathlib import Path
from src.vyu.storage.production import (
    PRODUCTION_SCHEMA_VERSION,
    CONNECTOR_HEALTH_MIGRATION_NAME,
    EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME,
    EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME,
    GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME,
    PRIVACY_APPROVAL_MIGRATION_NAME,
    READINESS_RESULT_MIGRATION_NAME,
    RESEARCH_MCP_MIGRATION_NAME,
    REVIEW_TASKS_MIGRATION_NAME,
    BASELINE_MIGRATION_NAME,
    ProductionAuditEvent,
    PrivacyApprovalRecord,
    ProductionScope,
    ProductionStorage,
    ReadinessCheckResultRecord,
)


def load_schema_sql() -> str:
    return (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")


__all__ = [
    "BASELINE_MIGRATION_NAME",
    "CONNECTOR_HEALTH_MIGRATION_NAME",
    "EVIDENCE_GRADING_METHODOLOGY_MIGRATION_NAME",
    "EVIDENCE_MEMORY_RETRIEVAL_MIGRATION_NAME",
    "GOVERNANCE_BOX_TRUST_SCORE_MIGRATION_NAME",
    "PRIVACY_APPROVAL_MIGRATION_NAME",
    "READINESS_RESULT_MIGRATION_NAME",
    "RESEARCH_MCP_MIGRATION_NAME",
    "PRODUCTION_SCHEMA_VERSION",
    "PrivacyApprovalRecord",
    "REVIEW_TASKS_MIGRATION_NAME",
    "ProductionAuditEvent",
    "ProductionScope",
    "ProductionStorage",
    "ReadinessCheckResultRecord",
    "load_schema_sql",
]
