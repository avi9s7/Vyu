import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import (
    build_evidence_context,
    generate_grounded_answer,
    validate_citations,
)
from src.vyu.governance import (
    build_governance_box,
    calculate_trust_score,
    export_audit_record,
)
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase5GovernanceTests(unittest.TestCase):
    def test_trust_score_governance_box_and_audit_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=5)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)
            answer = generate_grounded_answer(context)
            validation = validate_citations(answer, context)

            trust = calculate_trust_score(answer, context, validation)
            box = build_governance_box(
                question=context.question,
                context=context,
                trust_score=trust,
                sources_searched=["dummy_corpus"],
            )
            audit = export_audit_record(answer, context, trust, box)

        self.assertGreaterEqual(trust.overall, 0)
        self.assertLessEqual(trust.overall, 100)
        self.assertIn("citation_coverage", trust.components)
        self.assertEqual("dummy_corpus", box.sources_searched[0])
        self.assertEqual(answer.question, audit["answer"]["question"])


if __name__ == "__main__":
    unittest.main()
