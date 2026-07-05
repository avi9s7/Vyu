import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase3BM25RetrievalTests(unittest.TestCase):
    def test_bm25_returns_ranked_hits_with_trace_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            hits = retriever.search(RetrievalQuery(text="retracted VX-101 trial", top_k=5))

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual("bm25", hits[0].score.source)
        self.assertGreater(hits[0].score.value, 0)
        self.assertIn(hits[0].document_id, {"DOC-029", "DOC-030"})
        self.assertEqual(1, hits[0].trace.original_rank)


if __name__ == "__main__":
    unittest.main()
