import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evidence import (
    build_methodology_assessments_from_hits,
    build_methodology_run_record,
    default_methodology_ruleset,
)
from src.vyu.generation import build_evidence_context, generate_grounded_answer, validate_citations
from src.vyu.governance import (
    ExternalGovernanceConnector,
    ExternalGovernanceProviderConfig,
    ExternalGovernanceStatus,
    GovernanceDecisionStatus,
    GovernanceExportStatus,
    build_external_governance_request_record,
    build_production_governance_box_record,
    build_production_trust_score_record,
    default_trust_score_policy,
    parse_external_governance_webhook,
    sign_webhook_payload,
)
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.retrieval import (
    BM25Retriever,
    DenseKeywordRetriever,
    ProductionHybridRetrievalService,
    RetrievalQuery,
)
from src.vyu.storage import ProductionScope, ProductionStorage


class ProductionGovernanceBoxTrustScoreTests(unittest.TestCase):
    def test_builds_production_trust_score_and_governance_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _build_governance_bundle(root)

        trust_score = bundle["trust_score"]
        governance_box = bundle["governance_box"]
        self.assertEqual("trust_score_policy_v1", trust_score.policy_version)
        self.assertTrue(0 <= trust_score.overall <= 100)
        self.assertIn("citation_coverage", trust_score.components)
        self.assertIn(trust_score.decision_status, set(GovernanceDecisionStatus))
        self.assertEqual(trust_score.trust_score_id, governance_box.trust_score_id)
        self.assertEqual("audit-run-001", governance_box.audit_id)
        self.assertIn(governance_box.export_status, set(GovernanceExportStatus))
        self.assertIn("trust_score", governance_box.governance_box)

    def test_persists_governance_records_and_rejects_wrong_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _build_governance_bundle(root)
            storage = ProductionStorage(root / "production.sqlite")
            storage.initialize()
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            storage.record_production_trust_score(
                bundle["trust_score"],
                audit_event_id="event-trust-score",
                audit_created_at="2026-06-28T00:00:00Z",
            )
            storage.record_production_governance_box(
                bundle["governance_box"],
                audit_event_id="event-governance-box",
                audit_created_at="2026-06-28T00:00:00Z",
            )
            loaded_scores = storage.list_production_trust_score_records_for_scope(
                scope,
                run_id="run-001",
            )
            loaded_boxes = storage.list_production_governance_box_records_for_scope(
                scope,
                run_id="run-001",
            )
            wrong_scope = ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a")
            wrong_scores = storage.list_production_trust_score_records_for_scope(
                wrong_scope,
                run_id="run-001",
            )

        self.assertEqual([bundle["trust_score"].to_json()], [item.to_json() for item in loaded_scores])
        self.assertEqual([bundle["governance_box"].to_json()], [item.to_json() for item in loaded_boxes])
        self.assertEqual([], wrong_scores)

    def test_external_governance_connector_and_webhook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = _build_governance_bundle(root)
            provider = ExternalGovernanceProviderConfig(
                provider_id="evide_xa_like_governance_placeholder",
                endpoint_url="https://governance.example.invalid/v1/evaluate-output",
                webhook_url="https://api.vyu.example.invalid/webhooks/governance",
                auth_secret_ref="aws-secretsmanager:vyu/evide-xa-like-governance/token",
                webhook_secret_ref="aws-secretsmanager:vyu/evide-xa-like-governance/webhook",
            )
            request = build_external_governance_request_record(
                request_id="external-governance-001",
                answer=bundle["answer"],
                context=bundle["context"],
                retrieval_run=bundle["retrieval_run"],
                trust_score=bundle["trust_score"],
                governance_box=bundle["governance_box"],
                methodology_run=bundle["methodology_run"],
                assessments=bundle["assessments"],
                provider_config=provider,
                created_at="2026-06-28T00:00:00Z",
            )
            sent, ack = ExternalGovernanceConnector(provider, _FakeGovernanceTransport()).submit(
                request,
                sent_at="2026-06-28T00:00:10Z",
            )
            webhook_payload = {
                "response_id": "external-governance-response-001",
                "status": "succeeded",
                "provider_version": "evide-xa-like-placeholder-v1",
                "decision_status": "review_required",
                "export_status": "pending_review",
                "review_required": True,
            }
            signature = sign_webhook_payload(webhook_payload, "secret")
            webhook = parse_external_governance_webhook(
                request=sent,
                payload=webhook_payload,
                signature=signature,
                webhook_secret="secret",
                received_at="2026-06-28T00:01:00Z",
            )

        self.assertEqual(ExternalGovernanceStatus.ACCEPTED_ASYNC, sent.status)
        self.assertIsNotNone(ack)
        assert ack is not None
        self.assertEqual("evide_xa_like_governance_placeholder", ack.provider_id)
        self.assertEqual(False, request.payload["evidence"]["items"][0]["passage_text"] is not None)
        self.assertEqual(ExternalGovernanceStatus.SUCCEEDED, webhook.status)
        self.assertEqual(GovernanceDecisionStatus.REVIEW_REQUIRED, webhook.external_decision_status)
        self.assertEqual(GovernanceExportStatus.PENDING_REVIEW, webhook.external_export_status)
        self.assertTrue(webhook.webhook_signature_valid)


def _build_governance_bundle(root: Path):
    generate_phase1_corpus(root)
    corpus = load_dummy_corpus(root)
    service = ProductionHybridRetrievalService(
        lexical_retriever=BM25Retriever.from_corpus(corpus),
        semantic_retriever=DenseKeywordRetriever.from_corpus(corpus),
        index_versions=("hybrid-local-v1",),
    )
    hits, retrieval_run = service.search_with_record(
        query=RetrievalQuery(text="Does VX-101 reduce migraine days in adults?", top_k=5),
        retrieval_run_id="retrieval-run-001",
        run_id="run-001",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        user_id="user-a",
        topic="vx101-migraine",
        created_at="2026-06-28T00:00:00Z",
    )
    context = build_evidence_context(retrieval_run.question, hits[:5])
    answer = generate_grounded_answer(context)
    validation = validate_citations(answer, context)
    ruleset = default_methodology_ruleset("migraine_neurology", created_at="2026-06-28T00:00:00Z")
    assessments = build_methodology_assessments_from_hits(
        corpus=corpus,
        hits=hits[:5],
        retrieval_run=retrieval_run,
        ruleset=ruleset,
        created_at="2026-06-28T00:00:00Z",
    )
    methodology_run = build_methodology_run_record(
        methodology_run_id="methodology-run-001",
        retrieval_run=retrieval_run,
        assessments=assessments,
        ruleset=ruleset,
        created_at="2026-06-28T00:00:00Z",
    )
    trust_score = build_production_trust_score_record(
        trust_score_id="trust-score-001",
        answer=answer,
        context=context,
        validation=validation,
        retrieval_run=retrieval_run,
        methodology_run=methodology_run,
        assessments=assessments,
        policy=default_trust_score_policy(created_at="2026-06-28T00:00:00Z"),
        created_at="2026-06-28T00:00:00Z",
    )
    governance_box = build_production_governance_box_record(
        governance_box_id="governance-box-001",
        answer=answer,
        context=context,
        retrieval_run=retrieval_run,
        trust_score_record=trust_score,
        methodology_run=methodology_run,
        assessments=assessments,
        sources_searched=("dummy_corpus",),
        audit_id="audit-run-001",
        created_at="2026-06-28T00:00:00Z",
    )
    return {
        "answer": answer,
        "context": context,
        "retrieval_run": retrieval_run,
        "assessments": assessments,
        "methodology_run": methodology_run,
        "trust_score": trust_score,
        "governance_box": governance_box,
    }


class _FakeGovernanceTransport:
    def post_json(self, url, payload, headers, timeout_seconds):
        return {
            "status": "accepted",
            "external_job_id": "external-governance-job-001",
            "provider_version": "evide-xa-like-placeholder-v1",
            "decision_status": payload["trust_score"]["decision_status"],
            "export_status": payload["governance_box"]["export_status"],
            "review_required": payload["governance_box"]["human_review_required"],
            "request_id": headers["X-Vyu-Request-Id"],
        }


if __name__ == "__main__":
    unittest.main()
