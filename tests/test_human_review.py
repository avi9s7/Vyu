import unittest

from src.vyu.authz import Principal, Role, WorkspaceMembership
from src.vyu.governance.box import GovernanceBox
from src.vyu.governance.trust import TrustScore
from src.vyu.review import (
    ReviewDecision,
    ReviewStatus,
    create_review_task,
    decide_review,
    evaluate_export_gate,
)


class HumanReviewTests(unittest.TestCase):
    def test_governance_box_requiring_review_creates_pending_task(self):
        box = _governance_box(human_review_required=True)

        task = create_review_task(
            run_id="run-001",
            governance_box=box,
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        self.assertEqual("review-run-001", task.review_id)
        self.assertEqual(ReviewStatus.PENDING, task.status)
        self.assertEqual("Preprint evidence is present", task.reason)
        self.assertEqual("tenant-a", task.scope.tenant_id)
        self.assertEqual("workspace-a", task.scope.workspace_id)

    def test_export_gate_blocks_required_review_until_approved(self):
        reviewer = _principal(Role.REVIEWER)
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        pending_gate = evaluate_export_gate(reviewer, task)
        approved = decide_review(
            reviewer,
            task,
            decision=ReviewDecision.APPROVE,
            comment="Evidence reviewed for pilot export.",
            decided_at="2026-06-14T00:05:00Z",
        )
        approved_gate = evaluate_export_gate(reviewer, approved)

        self.assertFalse(pending_gate.allowed)
        self.assertEqual("review_required", pending_gate.reason)
        self.assertTrue(approved_gate.allowed)
        self.assertEqual("review_approved", approved_gate.reason)

    def test_reviewer_can_reject_and_rejected_review_blocks_export(self):
        reviewer = _principal(Role.REVIEWER)
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        rejected = decide_review(
            reviewer,
            task,
            decision=ReviewDecision.REJECT,
            comment="Preprint cannot support export.",
            decided_at="2026-06-14T00:05:00Z",
        )
        gate = evaluate_export_gate(reviewer, rejected)

        self.assertEqual(ReviewStatus.REJECTED, rejected.status)
        self.assertFalse(gate.allowed)
        self.assertEqual("review_rejected", gate.reason)

    def test_researcher_cannot_decide_review_or_export_reviewed_report(self):
        researcher = _principal(Role.RESEARCHER)
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=True),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        with self.assertRaises(PermissionError):
            decide_review(
                researcher,
                task,
                decision=ReviewDecision.APPROVE,
                comment="Not authorized.",
                decided_at="2026-06-14T00:05:00Z",
            )

        gate = evaluate_export_gate(researcher, task)
        self.assertFalse(gate.allowed)
        self.assertEqual("export_not_authorized", gate.reason)

    def test_review_not_required_allows_authorized_export(self):
        reviewer = _principal(Role.REVIEWER)
        task = create_review_task(
            run_id="run-001",
            governance_box=_governance_box(human_review_required=False),
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            created_at="2026-06-14T00:00:00Z",
        )

        gate = evaluate_export_gate(reviewer, task)

        self.assertEqual(ReviewStatus.NOT_REQUIRED, task.status)
        self.assertTrue(gate.allowed)
        self.assertEqual("review_not_required", gate.reason)


def _principal(role: Role) -> Principal:
    return Principal(
        user_id=f"{role.value}-user",
        memberships=(
            WorkspaceMembership(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                roles=(role,),
            ),
        ),
    )


def _governance_box(human_review_required: bool) -> GovernanceBox:
    return GovernanceBox(
        question="Does VX-101 reduce migraine days?",
        sources_searched=["dummy_corpus"],
        search_run_at="2026-06-14T00:00:00Z",
        retrieved_count=5,
        included_count=5,
        excluded_count=0,
        evidence_mix={"reviewed": 4, "preprint": 1},
        conflicts=[],
        models={"generator": "deterministic_grounded_answer_v1"},
        policy_versions={"governance_policy": "governance_policy_v1"},
        human_review_required=human_review_required,
        human_review_reason=(
            "Preprint evidence is present"
            if human_review_required
            else "No POC governance warnings"
        ),
        trust_score=TrustScore(
            overall=84 if human_review_required else 92,
            components={"citation_coverage": 100},
            warnings=["Preprint evidence is present"] if human_review_required else [],
        ),
    )


if __name__ == "__main__":
    unittest.main()
