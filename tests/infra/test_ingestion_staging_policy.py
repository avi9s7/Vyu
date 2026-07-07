from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING_SCRIPT = ROOT / "scripts" / "validate_ingestion_staging.py"
STAGING_EVIDENCE_TEMPLATE = ROOT / "docs" / "production" / "evidence" / "plan5-staging-validation.template.json"


def test_validate_ingestion_staging_script_contract() -> None:
    content = STAGING_SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "--environment",
        "--base-url",
        "VYU_INGESTION_STAGING_BEARER_TOKEN",
        "/v1/uploads/presign",
        "/v1/uploads/finalize",
        "/v1/ingestion-jobs/",
        "/v1/evidence-documents/",
        "clean_txt",
        "eicar_malware",
        "synthetic_phi",
        "presign_kms_required",
    ):
        assert marker in content


def test_plan5_staging_evidence_template_declares_operator_fields() -> None:
    content = STAGING_EVIDENCE_TEMPLATE.read_text(encoding="utf-8")
    for marker in (
        '"plan": 5',
        "validate_ingestion_staging.py",
        "runbook_exercised",
        "alarms_verified",
        "clean_txt_ready",
        "eicar_malware_blocked",
    ):
        assert marker in content
