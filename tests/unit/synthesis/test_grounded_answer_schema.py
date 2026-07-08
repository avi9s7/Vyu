from __future__ import annotations

import unittest

from src.vyu.research_mcp.hashing import stable_hash
from src.vyu.synthesis.contracts import (
    GROUNDED_ANSWER_PROMPT_VERSION,
    GROUNDED_ANSWER_SCHEMA_VERSION,
)
from src.vyu.synthesis.prompt_config import (
    CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256,
    GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA,
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    grounded_answer_prompt_bundle,
    grounded_answer_prompt_sha256,
    render_grounded_answer_user_prompt,
)
from src.vyu.synthesis.schema import (
    GroundedAnswerOutput,
    GroundedAnswerSemanticValidationError,
    parse_grounded_answer_output,
    validate_grounded_answer_semantics,
)


class GroundedAnswerPromptConfigTests(unittest.TestCase):
    def test_canonical_prompt_hash_is_stable(self) -> None:
        self.assertEqual(grounded_answer_prompt_sha256(), CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256)
        self.assertEqual(grounded_answer_prompt_sha256(), stable_hash(grounded_answer_prompt_bundle()))

    def test_prompt_bundle_versions_schema_and_template_together(self) -> None:
        bundle = grounded_answer_prompt_bundle()
        self.assertEqual(bundle["version"], GROUNDED_ANSWER_PROMPT_VERSION)
        self.assertEqual(bundle["schema_version"], GROUNDED_ANSWER_SCHEMA_VERSION)
        self.assertEqual(bundle["template"], GROUNDED_ANSWER_SYSTEM_PROMPT)
        self.assertEqual(bundle["output_schema"], GROUNDED_ANSWER_OUTPUT_JSON_SCHEMA)

    def test_prompt_or_schema_change_requires_version_bump(self) -> None:
        bundle = grounded_answer_prompt_bundle()
        changed_template = dict(bundle)
        changed_template["template"] = str(bundle["template"]) + "\n"
        changed_schema = dict(bundle)
        changed_schema["output_schema"] = {
            **dict(bundle["output_schema"]),
            "title": "grounded_answer_v1",
        }
        bumped_version = dict(bundle)
        bumped_version["version"] = int(bundle["version"]) + 1

        self.assertNotEqual(stable_hash(changed_template), CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256)
        self.assertNotEqual(stable_hash(changed_schema), CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256)
        self.assertNotEqual(stable_hash(bumped_version), CANONICAL_GROUNDED_ANSWER_PROMPT_SHA256)

    def test_system_prompt_states_required_safety_rules(self) -> None:
        prompt = GROUNDED_ANSWER_SYSTEM_PROMPT.lower()
        self.assertIn("patient-specific", prompt)
        self.assertIn("untrusted", prompt)
        self.assertIn("abstain", prompt)
        self.assertIn("citation_id", prompt)
        self.assertIn("contradiction", prompt)
        self.assertIn("uncertainty", prompt)
        self.assertIn("do not reveal hidden reasoning", prompt)

    def test_user_prompt_renders_question_and_evidence(self) -> None:
        rendered = render_grounded_answer_user_prompt(
            question="What is the effect?",
            evidence_block="<<<EVIDENCE_ITEM citation_id=CIT-1>>>",
        )
        self.assertIn("What is the effect?", rendered)
        self.assertIn("CIT-1", rendered)
        self.assertIn(GROUNDED_ANSWER_SCHEMA_VERSION, rendered)


class GroundedAnswerSchemaTests(unittest.TestCase):
    def _valid_payload(self, *, abstained: bool = False) -> dict[str, object]:
        if abstained:
            return {
                "answer_summary": "Insufficient non-retracted evidence to answer safely.",
                "claims": [],
                "uncertainty": "No usable passages were provided.",
                "contradictions": [],
                "limitations": [],
                "abstained": True,
                "abstention_reason": "insufficient_evidence",
            }
        return {
            "answer_summary": "Evidence suggests a modest benefit based on one trial.",
            "claims": [
                {
                    "claim_text": "A randomized trial reported improved outcomes.",
                    "citation_ids": ["CIT-001"],
                    "support": "supported",
                }
            ],
            "uncertainty": "Single-study evidence with limited follow-up.",
            "contradictions": [],
            "limitations": ["Pilot synthesis only."],
            "abstained": False,
            "abstention_reason": None,
        }

    def test_parse_valid_abstained_and_non_abstained_outputs(self) -> None:
        abstained = parse_grounded_answer_output(self._valid_payload(abstained=True))
        self.assertTrue(abstained.abstained)
        self.assertEqual(abstained.abstention_reason, "insufficient_evidence")

        answered = parse_grounded_answer_output(self._valid_payload())
        self.assertFalse(answered.abstained)
        self.assertEqual(len(answered.claims), 1)

    def test_rejects_unknown_citation_ids(self) -> None:
        output = parse_grounded_answer_output(self._valid_payload())
        with self.assertRaises(GroundedAnswerSemanticValidationError) as ctx:
            validate_grounded_answer_semantics(
                output,
                allowed_citation_ids=frozenset({"CIT-999"}),
            )
        self.assertIn("unknown citation_ids", str(ctx.exception))

    def test_rejects_missing_citations_on_factual_claim(self) -> None:
        payload = self._valid_payload()
        payload["claims"] = [{"claim_text": "A claim", "citation_ids": [], "support": "supported"}]
        output = parse_grounded_answer_output(payload)
        with self.assertRaises(GroundedAnswerSemanticValidationError) as ctx:
            validate_grounded_answer_semantics(
                output,
                allowed_citation_ids=frozenset({"CIT-001"}),
            )
        self.assertIn("missing citation_ids", str(ctx.exception))

    def test_rejects_unsupported_claim_repeated_in_summary(self) -> None:
        payload = self._valid_payload()
        payload["claims"] = [
            {
                "claim_text": "No benefit was observed in the primary endpoint.",
                "citation_ids": ["CIT-001"],
                "support": "unsupported",
            }
        ]
        payload["answer_summary"] = "No benefit was observed in the primary endpoint."
        output = parse_grounded_answer_output(payload)
        with self.assertRaises(GroundedAnswerSemanticValidationError) as ctx:
            validate_grounded_answer_semantics(
                output,
                allowed_citation_ids=frozenset({"CIT-001"}),
            )
        self.assertIn("unsupported claim", str(ctx.exception))

    def test_accepts_supported_claim_with_valid_citations(self) -> None:
        output = parse_grounded_answer_output(self._valid_payload())
        validate_grounded_answer_semantics(
            output,
            allowed_citation_ids=frozenset({"CIT-001"}),
        )
        self.assertIsInstance(output, GroundedAnswerOutput)


if __name__ == "__main__":
    unittest.main()
