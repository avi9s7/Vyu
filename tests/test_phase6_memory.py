import unittest

from src.vyu.memory import (
    FollowUpDecision,
    InMemoryResearchMemoryStore,
    ResearchMemoryRecord,
    classify_follow_up,
)


class Phase6MemoryTests(unittest.TestCase):
    def test_memory_is_scoped_by_tenant_workspace_user_and_topic(self):
        store = InMemoryResearchMemoryStore()
        record = ResearchMemoryRecord(
            tenant_id="tenant-a",
            workspace_id="migraine",
            user_id="user-1",
            topic="VX-101",
            question="Does VX-101 reduce migraine days?",
            retrieved_document_ids=["DOC-001"],
            generated_output_ids=["answer-1"],
        )

        store.save(record)

        self.assertEqual(
            1,
            len(store.list_for_scope("tenant-a", "migraine", "user-1", "VX-101")),
        )
        self.assertEqual(
            [],
            store.list_for_scope("tenant-b", "migraine", "user-1", "VX-101"),
        )

    def test_follow_up_classifier_uses_question_intent(self):
        store = InMemoryResearchMemoryStore()

        self.assertEqual(
            FollowUpDecision.REUSE_EXISTING_EVIDENCE,
            classify_follow_up(
                "Based on that evidence, summarize the main result.", store
            ),
        )
        self.assertEqual(
            FollowUpDecision.SEARCH_NEW_EVIDENCE,
            classify_follow_up(
                "Now check whether any new preprints disagree.", store
            ),
        )


if __name__ == "__main__":
    unittest.main()
