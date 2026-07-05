import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evidence import build_automated_evidence_profile, detect_contradictions
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase5EvidenceProfileTests(unittest.TestCase):
    def test_profile_flags_retracted_preprint_and_human_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)

            retracted = build_automated_evidence_profile(corpus, "DOC-029")
            preprint = build_automated_evidence_profile(corpus, "DOC-022")

        self.assertTrue(retracted.requires_human_review)
        self.assertIn("retracted", retracted.warnings)
        self.assertTrue(preprint.requires_human_review)
        self.assertIn("preprint", preprint.applicability_flags)

    def test_detector_finds_conflicting_primary_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            documents = [corpus.documents["DOC-001"], corpus.documents["DOC-002"]]

            conflicts = detect_contradictions(documents)

        self.assertGreaterEqual(len(conflicts), 1)
        self.assertEqual({"DOC-001", "DOC-002"}, set(conflicts[0].document_ids))


if __name__ == "__main__":
    unittest.main()
