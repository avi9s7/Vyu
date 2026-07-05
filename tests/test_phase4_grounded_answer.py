import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import (
    build_evidence_context,
    generate_grounded_answer,
    validate_citations,
)
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase4GroundedAnswerTests(unittest.TestCase):
    def test_grounded_answer_claims_have_valid_passage_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=4)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)

            answer = generate_grounded_answer(context)
            validation = validate_citations(answer, context)

        self.assertFalse(answer.abstained)
        self.assertGreaterEqual(len(answer.claims), 1)
        self.assertTrue(all(claim.citation_ids for claim in answer.claims))
        self.assertTrue(validation.valid)

    def test_grounded_answer_abstains_without_evidence(self):
        context = build_evidence_context("Does VX-101 prevent chronic migraine?", [])

        answer = generate_grounded_answer(context)
        validation = validate_citations(answer, context)

        self.assertTrue(answer.abstained)
        self.assertEqual([], answer.claims)
        self.assertTrue(validation.valid)


if __name__ == "__main__":
    unittest.main()
