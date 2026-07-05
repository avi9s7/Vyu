import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus


class Phase1CorpusGenerationTests(unittest.TestCase):
    def test_generator_creates_required_phase1_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)

            documents = [
                json.loads(line)
                for line in (root / "data/dummy_articles/documents.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            passages = [
                json.loads(line)
                for line in (root / "data/dummy_articles/passages.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]
            questions = [
                json.loads(line)
                for line in (root / "data/golden_questions/questions.jsonl").read_text(
                    encoding="utf-8"
                ).splitlines()
            ]

        self.assertEqual(30, len(documents))
        self.assertGreaterEqual(len(passages), 60)
        self.assertEqual(15, len(questions))


if __name__ == "__main__":
    unittest.main()
