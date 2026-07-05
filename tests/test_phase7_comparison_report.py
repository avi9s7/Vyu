import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evaluation import compare_workflows, render_adoption_report
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import BM25Retriever


class Phase7ComparisonReportTests(unittest.TestCase):
    def test_comparison_and_report_include_quality_cost_latency_auditability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            retriever = BM25Retriever.from_corpus(corpus)

            comparison = compare_workflows(
                corpus,
                retriever,
                questions=["Does VX-101 reduce migraine days?"],
            )
            report = render_adoption_report(comparison)

        self.assertIn("fixed_one_shot", comparison.workflow_metrics)
        self.assertIn("guided_deep_dive", comparison.workflow_metrics)
        self.assertIn("Quality", report)
        self.assertIn("Auditability", report)
