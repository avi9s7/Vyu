import tempfile
import unittest
from pathlib import Path

from src.vyu.entrypoints import (
    PrivacyApprovalApiRequest,
    PrivacyApprovalPayload,
    PrivacyApprovalWorkerJob,
    handle_privacy_approval_api,
    run_privacy_approval_worker_job,
)
from src.vyu.privacy import DataClassification, PrivacyApproval
from src.vyu.sources import ProductionSourceRecord
from src.vyu.storage import ProductionScope, ProductionStorage


class PrivacyWorkflowEntrypointTests(unittest.TestCase):
    def test_api_adapter_blocks_phi_use_and_persists_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            response = handle_privacy_approval_api(
                PrivacyApprovalApiRequest(
                    request_id="privacy-request-001",
                    payload=_payload(
                        purpose="patient_specific_recommendation",
                        data_classification=DataClassification.EPHI,
                        approvals=(),
                    ),
                ),
                storage=storage,
                approval_id_factory=_approval_id,
                audit_event_id_factory=_audit_event_id,
                evaluated_at="2026-06-14T00:00:01Z",
            )
            records = storage.list_privacy_approval_records_for_scope(
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                run_id="run-001",
            )
            events = storage.list_audit_events(
                run_id="run-001",
                event_type="privacy_approval_recorded",
            )

        self.assertEqual(403, response.status_code)
        self.assertEqual("privacy-request-001", response.body["request_id"])
        self.assertFalse(response.body["privacy"]["allowed"])
        self.assertEqual("blocked", response.body["privacy"]["status"])
        self.assertIn("security", response.body["privacy"]["missing_approvals"])
        self.assertEqual(1, len(records))
        self.assertEqual("privacy-run-001", records[0].approval_id)
        self.assertFalse(records[0].allowed)
        self.assertEqual("blocked", records[0].decision_status)
        self.assertEqual(1, len(events))
        self.assertEqual("event-privacy_approval_recorded", events[0].event_id)

    def test_worker_adapter_allows_phi_use_when_approvals_are_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = ProductionStorage(Path(tmp) / "production.sqlite")
            storage.initialize()

            result = run_privacy_approval_worker_job(
                PrivacyApprovalWorkerJob(
                    job_id="privacy-job-001",
                    payload=_payload(
                        purpose="patient_specific_recommendation",
                        data_classification=DataClassification.EPHI,
                        approvals=(
                            PrivacyApproval(
                                "privacy",
                                "privacy-owner",
                                "2026-06-14T00:00:00Z",
                            ),
                            PrivacyApproval(
                                "security",
                                "security-owner",
                                "2026-06-14T00:00:00Z",
                            ),
                            PrivacyApproval(
                                "regulatory",
                                "regulatory-owner",
                                "2026-06-14T00:00:00Z",
                            ),
                            PrivacyApproval(
                                "clinical_safety",
                                "clinical-owner",
                                "2026-06-14T00:00:00Z",
                            ),
                        ),
                    ),
                ),
                storage=storage,
                approval_id_factory=_approval_id,
                audit_event_id_factory=_audit_event_id,
                evaluated_at="2026-06-14T00:00:01Z",
            )
            records = storage.list_privacy_approval_records_for_scope(
                ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a"),
                run_id="run-001",
            )

        self.assertEqual("privacy-job-001", result.job_id)
        self.assertEqual("completed", result.status)
        self.assertTrue(result.privacy["allowed"])
        self.assertEqual("approved", result.privacy["status"])
        self.assertEqual(1, len(records))
        self.assertTrue(records[0].allowed)
        self.assertEqual(
            "privacy-owner",
            records[0].approvals[0]["approved_by"],
        )


def _payload(
    purpose: str,
    data_classification: DataClassification,
    approvals: tuple[PrivacyApproval, ...],
) -> PrivacyApprovalPayload:
    return PrivacyApprovalPayload(
        run_id="run-001",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        purpose=purpose,
        data_classification=data_classification,
        sources=(
            ProductionSourceRecord(
                source_id="patient-data",
                display_name="Patient Data",
                source_type="patient_data",
                owner="Vyu",
                license_or_terms="customer agreement",
                allowed_uses=["patient_specific_recommendation"],
                phi_pii_status="ephi",
                approval_status="approved",
                approved_by="privacy-board",
                approved_at="2026-06-14T00:00:00Z",
            ),
        ),
        approvals=approvals,
    )


def _approval_id(run_id: str) -> str:
    return f"privacy-{run_id}"


def _audit_event_id(_run_id: str, event_type: str) -> str:
    return f"event-{event_type}"


if __name__ == "__main__":
    unittest.main()
