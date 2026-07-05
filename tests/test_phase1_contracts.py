import unittest

from src.vyu.contracts import DocumentRecord, EvidenceProfile, StudyDesign


class Phase1ContractsTests(unittest.TestCase):
    def test_document_materializes_stable_citation_label(self):
        document = DocumentRecord(
            document_id="DOC-001",
            title="VX-101 Trial",
            year=2026,
            study_design=StudyDesign.RANDOMIZED_CONTROLLED_TRIAL,
            source_type="dummy_pubmed",
            publication_status="peer_reviewed",
        )

        self.assertEqual("DOC-001 (2026)", document.citation_label)

    def test_evidence_profile_flags_human_review_for_retracted_source(self):
        profile = EvidenceProfile(
            document_id="DOC-030",
            study_design=StudyDesign.CASE_REPORT,
            evidence_level="lower",
            bias_flags=[],
            applicability_flags=[],
            retraction_status="retracted",
            preprint_status=False,
            assessment_confidence=0.5,
        )

        self.assertTrue(profile.requires_human_review)


if __name__ == "__main__":
    unittest.main()
