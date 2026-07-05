import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evaluation import export_deep_dive_trajectory
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever
from src.vyu.workflow import run_guided_deep_dive


class Phase7TrajectoryTests(unittest.TestCase):
    def test_deep_dive_trajectory_is_json_serializable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            result = run_guided_deep_dive(
                "Does VX-101 reduce migraine days?",
                BM25Retriever.from_corpus(corpus),
                max_rounds=2,
            )

            trajectory = export_deep_dive_trajectory(result)

        self.assertEqual("guided_deep_dive", trajectory.workflow)
        self.assertGreaterEqual(len(trajectory.events), 1)
        self.assertIn("query", trajectory.to_json()["events"][0])
