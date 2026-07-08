from __future__ import annotations

import unittest
from uuid import uuid4

from src.vyu.synthesis.context import BuiltEvidenceContext, EvidenceContextItem
from src.vyu.synthesis.contracts import EVIDENCE_CONTEXT_BUILDER_VERSION
from src.vyu.synthesis.schema import parse_grounded_answer_output
from src.vyu.synthesis.validators import (
    required_abstention_reason,
    validate_synthesis_output,
)


def _item(*, citation_id: str = "CIT-001", excerpt: str = "Aspirin reduced cardiovascular events.") -> EvidenceContextItem:
    return EvidenceContextItem(
        citation_id=citation_id,
        title="Trial",
        source_id="pubmed",
        source_date="2024-01-01",
        evidence_type="rct",
        evidence_quality="high",
        is_retracted=False,
        has_correction=False,
        excerpt=excerpt,
        document_id="DOC-1",
        document_version_id=uuid4(),
        document_chunk_id=uuid4(),
        location="abstract",
        rank=1,
        token_count=12,
    )


def _context(*, items: tuple[EvidenceContextItem, ...] = ()) -> BuiltEvidenceContext:
    return BuiltEvidenceContext(
        builder_version=EVIDENCE_CONTEXT_BUILDER_VERSION,
        research_run_id=uuid4(),
        retrieval_run_id=uuid4(),
        retrieval_index_id=uuid4(),
        policy_version="policy-v1",
        manifest_checksum="manifest",
        items=items,
        exclusions=(),
        context_sha256="c" * 64,
        token_count=sum(item.token_count for item in items),
    )


class SynthesisValidatorTests(unittest.TestCase):
    def test_required_abstention_for_empty_context(self) -> None:
        self.assertEqual("insufficient_evidence", required_abstention_reason(_context()))

    def test_valid_answer_passes_validation(self) -> None:
        context = _context(items=(_item(),))
        output = parse_grounded_answer_output(
            {
                "answer_summary": "Aspirin reduced cardiovascular events in the cited trial.",
                "claims": [
                    {
                        "claim_text": "Aspirin reduced cardiovascular events.",
                        "citation_ids": ["CIT-001"],
                        "support": "supported",
                    }
                ],
                "uncertainty": "Single trial evidence.",
                "contradictions": [],
                "limitations": [],
                "abstained": False,
                "abstention_reason": None,
            }
        )
        result = validate_synthesis_output(
            output,
            context=context,
            required_abstention=None,
            max_answer_chars=10_000,
            max_claims=10,
        )
        self.assertTrue(result.valid)

    def test_rejects_unknown_citation(self) -> None:
        context = _context(items=(_item(),))
        output = parse_grounded_answer_output(
            {
                "answer_summary": "Summary.",
                "claims": [
                    {
                        "claim_text": "Claim.",
                        "citation_ids": ["CIT-999"],
                        "support": "supported",
                    }
                ],
                "uncertainty": "",
                "contradictions": [],
                "limitations": [],
                "abstained": False,
                "abstention_reason": None,
            }
        )
        result = validate_synthesis_output(
            output,
            context=context,
            required_abstention=None,
            max_answer_chars=10_000,
            max_claims=10,
        )
        self.assertFalse(result.valid)
        self.assertTrue(any("unknown citation_ids" in error for error in result.errors))

    def test_rejects_answer_when_context_requires_abstention(self) -> None:
        context = _context()
        output = parse_grounded_answer_output(
            {
                "answer_summary": "Summary.",
                "claims": [],
                "uncertainty": "",
                "contradictions": [],
                "limitations": [],
                "abstained": False,
                "abstention_reason": None,
            }
        )
        result = validate_synthesis_output(
            output,
            context=context,
            required_abstention="insufficient_evidence",
            max_answer_chars=10_000,
            max_claims=10,
        )
        self.assertFalse(result.valid)

    def test_rejects_patient_specific_content(self) -> None:
        context = _context(items=(_item(),))
        output = parse_grounded_answer_output(
            {
                "answer_summary": "You should take aspirin for your diagnosis.",
                "claims": [],
                "uncertainty": "",
                "contradictions": [],
                "limitations": [],
                "abstained": False,
                "abstention_reason": None,
            }
        )
        result = validate_synthesis_output(
            output,
            context=context,
            required_abstention=None,
            max_answer_chars=10_000,
            max_claims=10,
        )
        self.assertFalse(result.valid)
        self.assertIn("patient-specific", result.errors[0])

    def test_contradiction_disclosure_is_allowed(self) -> None:
        context = _context(items=(_item(),))
        output = parse_grounded_answer_output(
            {
                "answer_summary": "Evidence is mixed on the endpoint.",
                "claims": [
                    {
                        "claim_text": "One trial reported benefit.",
                        "citation_ids": ["CIT-001"],
                        "support": "mixed",
                    }
                ],
                "uncertainty": "Conflicting secondary endpoints.",
                "contradictions": ["Primary endpoint direction differs across trials."],
                "limitations": [],
                "abstained": False,
                "abstention_reason": None,
            }
        )
        result = validate_synthesis_output(
            output,
            context=context,
            required_abstention=None,
            max_answer_chars=10_000,
            max_claims=10,
        )
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
