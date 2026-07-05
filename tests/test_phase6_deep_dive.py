import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever
from src.vyu.workflow import decompose_pico, run_guided_deep_dive


class Phase6DeepDiveTests(unittest.TestCase):
    def test_pico_decomposition_extracts_vx101_defaults(self):
        pico = decompose_pico(
            "Does VX-101 reduce migraine days in adults with episodic migraine compared with standard therapy?"
        )

        self.assertEqual("adults with episodic migraine", pico.population)
        self.assertEqual("VX-101", pico.intervention)
        self.assertEqual("standard therapy", pico.comparator)
        self.assertIn("migraine days", pico.outcomes)

    def test_deep_dive_runs_no_more_than_two_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            result = run_guided_deep_dive(
                "Does VX-101 reduce migraine days in adults with episodic migraine?",
                retriever,
                max_rounds=2,
            )

        self.assertGreaterEqual(len(result.rounds), 1)
        self.assertLessEqual(len(result.rounds), 2)
        self.assertIn(result.stopping_reason, {"enough_evidence", "max_rounds_reached"})


if __name__ == "__main__":
    unittest.main()
