from __future__ import annotations

import unittest

from src.vyu.research_mcp.hashing import stable_hash


class ModelSynthesisHashTests(unittest.TestCase):
    def test_policy_payload_hash_is_stable(self) -> None:
        payload = {
            "allowed_providers": ["deterministic"],
            "allowed_models": ["vyu-deterministic-v1"],
            "use_cases": ["grounded_synthesis"],
            "limits": {"max_output_tokens": 1000},
            "fallback_rules": {},
            "version_number": 1,
        }
        self.assertEqual(stable_hash(payload), stable_hash(payload))

    def test_prompt_payload_hash_changes_with_version(self) -> None:
        first = stable_hash(
            {
                "name": "grounded_answer_v1",
                "use_case": "grounded_synthesis",
                "version": 1,
                "template": "Answer using evidence only.",
                "output_schema": {"type": "object"},
            }
        )
        second = stable_hash(
            {
                "name": "grounded_answer_v1",
                "use_case": "grounded_synthesis",
                "version": 2,
                "template": "Answer using evidence only.",
                "output_schema": {"type": "object"},
            }
        )
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
