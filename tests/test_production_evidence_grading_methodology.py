import json
import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.evidence import (
    EvidenceAssessmentStatus,
    EvidenceStrengthBand,
    ExternalEvidenceGradingConnector,
    ExternalEvidenceGradingProviderConfig,
    apply_reviewer_rating,
    build_external_grading_request_record,
    build_methodology_assessment,
    build_methodology_assessments_from_hits,
    build_methodology_run_record,
    create_reviewer_evidence_rating,
    default_methodology_ruleset,
    parse_external_grading_webhook,
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


class ProductionEvidenceGradingMethodologyTests(unittest.TestCase):
    def test_local_methodology_scores_surface_retraction_preprint_and_review_need(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            service = ProductionHybridRetrievalService(
                lexical_retriever=BM25Retriever.from_corpus(corpus),
                semantic_retriever=DenseKeywordRetriever.from_corpus(corpus),
                index_versions=("hybrid-local-v1",),
            )
            _, retrieval_run = service.search_with_record(
                query=RetrievalQuery(text="Does VX-101 reduce migraine days in adults?", top_k=5),
                retrieval_run_id="retrieval-run-001",
                run_id="run-001",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                user_id="user-a",
                topic="vx101-migraine",
                created_at="2026-06-28T00:00:00Z",
            )
            ruleset = default_methodology_ruleset("migraine_neurology", created_at="2026-06-28T00:00:00Z")

            retracted = build_methodology_assessment(
                corpus=corpus,
                document_id="DOC-029",
                retrieval_run=retrieval_run,
                ruleset=ruleset,
                created_at="2026-06-28T00:00:00Z",
            )
            preprint = build_methodology_assessment(
                corpus=corpus,
                document_id="DOC-022",
                retrieval_run=retrieval_run,
                ruleset=ruleset,
                created_at="2026-06-28T00:00:00Z",
            )

        self.assertEqual(0, retracted.evidence_strength_score)
        self.assertEqual(EvidenceStrengthBand.UNSUITABLE, retracted.evidence_strength_band)
        self.assertIn("retracted_source", retracted.limitation_flags)
        self.assertTrue(retracted.requires_human_review)
        self.assertIn("preprint_not_peer_reviewed", preprint.limitation_flags)
        self.assertTrue(preprint.requires_human_review)
        self.assertFalse(retracted.metadata["formal_grade_completed"])

    def test_persists_methodology_assessments_external_connector_and_reviewer_rating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            storage = ProductionStorage(root / "production.sqlite")
            storage.initialize()
            service = ProductionHybridRetrievalService(
                lexical_retriever=BM25Retriever.from_corpus(corpus),
                semantic_retriever=DenseKeywordRetriever.from_corpus(corpus),
                index_versions=("hybrid-local-v1",),
            )
            hits, retrieval_run = service.search_with_record(
                query=RetrievalQuery(text="Does VX-101 reduce migraine days in adults?", top_k=5),
                retrieval_run_id="retrieval-run-001",
                run_id="run-001",
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                user_id="user-a",
                topic="vx101-migraine",
                created_at="2026-06-28T00:00:00Z",
            )
            ruleset = default_methodology_ruleset("migraine_neurology", created_at="2026-06-28T00:00:00Z")
            assessments = build_methodology_assessments_from_hits(
                corpus=corpus,
                hits=hits[:3],
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
            rating = create_reviewer_evidence_rating(
                rating_id="rating-001",
                assessment=assessments[0],
                reviewer_id="reviewer-a",
                reviewer_role="clinical_reviewer",
                adjusted_strength_score=72,
                adjusted_evidence_level="moderate_after_manual_review",
                adjustment_reasons=("manual_methodology_review",),
                comment="Adjusted after reviewer inspection of synthetic trial limitations.",
                created_at="2026-06-28T00:01:00Z",
            )
            adjusted_assessment = apply_reviewer_rating(assessments[0], rating)
            provider = ExternalEvidenceGradingProviderConfig(
                provider_id="aidea_like_evidence_grading_placeholder",
                endpoint_url="https://evidence-grading.example.invalid/v1/grade",
                webhook_url="https://api.vyu.example.invalid/webhooks/evidence-grading",
                auth_secret_ref="aws-secretsmanager:vyu/aidea-like-grading/token",
                webhook_secret_ref="aws-secretsmanager:vyu/aidea-like-grading/webhook",
                supported_specialties=("migraine_neurology",),
            )
            request = build_external_grading_request_record(
                request_id="external-request-001",
                retrieval_run=retrieval_run,
                corpus=corpus,
                document_ids=tuple(assessment.document_id for assessment in assessments),
                ruleset=ruleset,
                provider_config=provider,
                created_at="2026-06-28T00:00:00Z",
            )
            sent_request, ack = ExternalEvidenceGradingConnector(provider, _FakeTransport()).submit(
                request,
                sent_at="2026-06-28T00:00:10Z",
            )

            storage.record_evidence_methodology_assessment(
                adjusted_assessment,
                audit_event_id="event-assessment",
                audit_created_at="2026-06-28T00:00:00Z",
            )
            for assessment in assessments[1:]:
                storage.record_evidence_methodology_assessment(
                    assessment,
                    audit_event_id=f"event-assessment-{assessment.document_id}",
                    audit_created_at="2026-06-28T00:00:00Z",
                )
            storage.record_evidence_methodology_run(
                methodology_run,
                audit_event_id="event-methodology-run",
                audit_created_at="2026-06-28T00:00:00Z",
            )
            storage.record_reviewer_evidence_rating(
                rating,
                audit_event_id="event-rating",
                audit_created_at="2026-06-28T00:01:00Z",
            )
            storage.record_external_evidence_grading_request(
                sent_request,
                audit_event_id="event-external-request",
                audit_created_at="2026-06-28T00:00:10Z",
            )
            assert ack is not None
            storage.record_external_evidence_grading_response(
                ack,
                audit_event_id="event-external-response",
                audit_created_at="2026-06-28T00:00:10Z",
            )

            loaded_assessments = storage.list_evidence_methodology_assessment_records_for_scope(scope, run_id="run-001")
            loaded_runs = storage.list_evidence_methodology_run_records_for_scope(scope, run_id="run-001")
            loaded_ratings = storage.list_reviewer_evidence_rating_records_for_scope(scope, run_id="run-001")
            loaded_requests = storage.list_external_evidence_grading_request_records_for_scope(scope, run_id="run-001")
            loaded_responses = storage.list_external_evidence_grading_response_records_for_scope(scope, run_id="run-001")
            wrong_scope = ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a")
            wrong_scope_assessments = storage.list_evidence_methodology_assessment_records_for_scope(
                wrong_scope,
                run_id="run-001",
            )

        self.assertEqual(3, len(loaded_assessments))
        self.assertIn(
            EvidenceAssessmentStatus.REVIEWER_ADJUSTED,
            {assessment.status for assessment in loaded_assessments},
        )
        self.assertEqual([methodology_run.to_json()], [item.to_json() for item in loaded_runs])
        self.assertEqual([rating.to_json()], [item.to_json() for item in loaded_ratings])
        self.assertEqual([sent_request.to_json()], [item.to_json() for item in loaded_requests])
        self.assertEqual([ack.to_json()], [item.to_json() for item in loaded_responses])
        self.assertEqual([], wrong_scope_assessments)
        self.assertTrue(loaded_requests[0].payload["data_minimization"]["secrets_included"] is False)

    def test_external_webhook_signature_and_assessment_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            service = ProductionHybridRetrievalService(
                lexical_retriever=BM25Retriever.from_corpus(corpus),
                semantic_retriever=DenseKeywordRetriever.from_corpus(corpus),
                index_versions=("hybrid-local-v1",),
            )
            _, retrieval_run = service.search_with_record(
                query=RetrievalQuery(text="Does VX-101 reduce migraine days?", top_k=3),
                retrieval_run_id="retrieval-run-001",
                run_id="run-001",
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                user_id="user-a",
                topic="vx101-migraine",
                created_at="2026-06-28T00:00:00Z",
            )
            provider = ExternalEvidenceGradingProviderConfig(
                provider_id="aidea_like_evidence_grading_placeholder",
                endpoint_url="https://evidence-grading.example.invalid/v1/grade",
                webhook_url="https://api.vyu.example.invalid/webhooks/evidence-grading",
            )
            ruleset = default_methodology_ruleset("migraine_neurology", created_at="2026-06-28T00:00:00Z")
            request = build_external_grading_request_record(
                request_id="external-request-001",
                retrieval_run=retrieval_run,
                corpus=corpus,
                document_ids=("DOC-001",),
                ruleset=ruleset,
                provider_config=provider,
                created_at="2026-06-28T00:00:00Z",
            )
            webhook_payload = {
                "request_id": request.request_id,
                "response_id": "response-001",
                "status": "succeeded",
                "provider_version": "aidea-like-placeholder-v1",
                "assessments": [
                    {
                        "document_id": "DOC-001",
                        "study_design": "randomized_controlled_trial",
                        "evidence_strength_score": 84,
                        "evidence_strength_band": "high",
                        "source_reliability_score": 90,
                        "recency_score": 95,
                        "population_context_match_score": 88,
                        "methodology_domain_scores": {"study_design": 86},
                        "assessment_confidence": 0.82,
                        "requires_human_review": False,
                    }
                ],
            }
            raw = json.dumps(webhook_payload, sort_keys=True).encode("utf-8")
            signature = sign_webhook_payload(raw, "webhook-secret")

            response, assessments = parse_external_grading_webhook(
                request=request,
                raw_body=raw,
                signature=signature,
                webhook_secret="webhook-secret",
                received_at="2026-06-28T00:02:00Z",
            )

        self.assertTrue(response.webhook_signature_valid)
        self.assertEqual(("external-external-request-001-DOC-001",), response.assessment_ids)
        self.assertEqual("external_provider", assessments[0].assessment_source)
        self.assertEqual("aidea_like_evidence_grading_placeholder", assessments[0].provider_id)


class _FakeTransport:
    def post_json(self, url, payload, headers, timeout_seconds):
        self.url = url
        self.payload = payload
        self.headers = headers
        self.timeout_seconds = timeout_seconds
        return {
            "status": "accepted",
            "external_job_id": "job-001",
            "provider_version": "aidea-like-placeholder-v1",
            "assessment_ids": [],
        }


if __name__ == "__main__":
    unittest.main()
