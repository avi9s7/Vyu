import unittest

from src.vyu.privacy import (
    DataClassification,
    PrivacyApproval,
    PrivacyGate,
    PrivacyReviewStatus,
    WorkflowDataUse,
)
from src.vyu.sources import ProductionSourceRecord


class PrivacyGateTests(unittest.TestCase):
    def test_blocks_phi_source_without_privacy_approval(self):
        gate = PrivacyGate()
        source = _source(
            source_type="patient_data",
            phi_pii_status="ephi",
            allowed_uses=["patient_specific_recommendation"],
        )

        decision = gate.evaluate(
            WorkflowDataUse(
                purpose="patient_specific_recommendation",
                data_classification=DataClassification.EPHI,
                sources=(source,),
                approvals=(),
            )
        )

        self.assertFalse(decision.allowed)
        self.assertEqual("blocked", decision.status.value)
        self.assertIn("PHI/ePHI requires approved privacy clearance.", decision.reasons)
        self.assertIn("security", decision.missing_approvals)

    def test_blocks_patient_specific_recommendation_even_without_phi(self):
        gate = PrivacyGate()
        source = _source(
            source_type="public_literature",
            phi_pii_status="none",
            allowed_uses=["patient_specific_recommendation"],
        )

        decision = gate.evaluate(
            WorkflowDataUse(
                purpose="patient_specific_recommendation",
                data_classification=DataClassification.PUBLIC_LITERATURE,
                sources=(source,),
                approvals=(),
            )
        )

        self.assertFalse(decision.allowed)
        self.assertIn(
            "Patient-specific recommendations require regulatory and clinical safety clearance.",
            decision.reasons,
        )
        self.assertIn("clinical_safety", decision.missing_approvals)

    def test_allows_public_literature_research_without_phi_approval(self):
        gate = PrivacyGate()
        source = _source(
            source_type="public_literature",
            phi_pii_status="none",
            allowed_uses=["literature_search"],
        )

        decision = gate.evaluate(
            WorkflowDataUse(
                purpose="literature_search",
                data_classification=DataClassification.PUBLIC_LITERATURE,
                sources=(source,),
                approvals=(),
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual("approved", decision.status.value)
        self.assertEqual((), decision.missing_approvals)

    def test_allows_phi_only_when_all_required_approvals_are_present(self):
        gate = PrivacyGate()
        source = _source(
            source_type="patient_data",
            phi_pii_status="ephi",
            allowed_uses=["patient_specific_recommendation"],
        )

        decision = gate.evaluate(
            WorkflowDataUse(
                purpose="patient_specific_recommendation",
                data_classification=DataClassification.EPHI,
                sources=(source,),
                approvals=(
                    PrivacyApproval("privacy", "privacy-owner", "2026-06-14T00:00:00Z"),
                    PrivacyApproval("security", "security-owner", "2026-06-14T00:00:00Z"),
                    PrivacyApproval("regulatory", "regulatory-owner", "2026-06-14T00:00:00Z"),
                    PrivacyApproval("clinical_safety", "clinical-owner", "2026-06-14T00:00:00Z"),
                ),
            )
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(PrivacyReviewStatus.APPROVED, decision.status)
        self.assertEqual((), decision.missing_approvals)

    def test_blocks_model_provider_use_when_phi_is_present(self):
        gate = PrivacyGate()

        decision = gate.evaluate(
            WorkflowDataUse(
                purpose="model_provider_call",
                data_classification=DataClassification.PHI,
                sources=(),
                approvals=(
                    PrivacyApproval("privacy", "privacy-owner", "2026-06-14T00:00:00Z"),
                    PrivacyApproval("security", "security-owner", "2026-06-14T00:00:00Z"),
                ),
            )
        )

        self.assertFalse(decision.allowed)
        self.assertIn(
            "PHI/ePHI cannot be sent to a model provider without provider-specific approval.",
            decision.reasons,
        )
        self.assertIn("model_provider", decision.missing_approvals)


def _source(
    source_type: str,
    phi_pii_status: str,
    allowed_uses: list[str],
) -> ProductionSourceRecord:
    return ProductionSourceRecord(
        source_id="source-1",
        display_name="Source 1",
        source_type=source_type,
        owner="Vyu",
        license_or_terms="test",
        allowed_uses=allowed_uses,
        phi_pii_status=phi_pii_status,
        approval_status="approved",
        approved_by="review-board",
        approved_at="2026-06-14T00:00:00Z",
    )


if __name__ == "__main__":
    unittest.main()
