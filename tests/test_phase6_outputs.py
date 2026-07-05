import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.generation import (
    build_evidence_context,
    generate_grounded_answer,
    validate_citations,
)
from src.vyu.governance import build_governance_box, calculate_trust_score
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.reports import (
    render_evidence_brief,
    render_policy_output,
    render_research_report,
)
from src.vyu.retrieval import BM25Retriever, RetrievalQuery


class Phase6OutputTemplateTests(unittest.TestCase):
    def test_templates_include_answer_governance_and_review_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            hits = BM25Retriever.from_corpus(corpus).search(
                RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=3)
            )
            context = build_evidence_context("Does VX-101 reduce migraine days?", hits)
            answer = generate_grounded_answer(context)
            trust = calculate_trust_score(
                answer, context, validate_citations(answer, context)
            )
            box = build_governance_box(context.question, context, trust, ["dummy_corpus"])

            brief = render_evidence_brief(answer, trust, box)
            report = render_research_report(answer, context, trust, box)
            policy = render_policy_output(answer, trust, box)

        self.assertIn("Evidence Brief", brief)
        self.assertIn("Research Report", report)
        self.assertIn("Human review", policy)


if __name__ == "__main__":
    unittest.main()
