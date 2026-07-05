import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus


class Phase1LoaderTests(unittest.TestCase):
    def test_loader_validates_links_and_supports_keyword_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)

        self.assertEqual(30, len(corpus.documents))
        self.assertEqual(15, len(corpus.golden_questions))
        self.assertGreaterEqual(len(corpus.find_documents("retracted")), 1)


if __name__ == "__main__":
    unittest.main()
