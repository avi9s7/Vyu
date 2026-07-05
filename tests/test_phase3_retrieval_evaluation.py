import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever, evaluate_golden_questions


class Phase3RetrievalEvaluationTests(unittest.TestCase):
    def test_evaluation_reports_recall_mrr_and_ndcg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            metrics = evaluate_golden_questions(corpus, retriever, top_k=10)

        self.assertIn("recall_at_10", metrics)
        self.assertIn("mrr_at_10", metrics)
        self.assertIn("ndcg_at_10", metrics)
        self.assertGreaterEqual(metrics["recall_at_10"], 0.5)


if __name__ == "__main__":
    unittest.main()
