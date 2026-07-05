import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import build_evidence_context
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase4ContextBuilderTests(unittest.TestCase):
    def test_context_assigns_stable_citation_ids_to_retrieved_passages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="VX-101 migraine trial", top_k=3)
            )

            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)

        self.assertEqual("Does VX-101 reduce migraine days?", context.question)
        self.assertEqual(3, len(context.items))
        self.assertEqual("CIT-001", context.items[0].citation_id)
        self.assertEqual(hits[0].passage_id, context.items[0].passage_id)


if __name__ == "__main__":
    unittest.main()
