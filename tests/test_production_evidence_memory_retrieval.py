import tempfile
import unittest
from pathlib import Path

from scripts.generate_phase1_corpus import generate_phase1_corpus
from src.vyu.ingestion.dummy_corpus import load_dummy_corpus
from src.vyu.memory import (
    FollowUpDecision,
    ProductionResearchMemoryRecord,
    classify_production_follow_up,
)
from src.vyu.retrieval import (
    BM25Retriever,
    DenseKeywordRetriever,
    EvidenceObjectKind,
    EvidenceObjectRecord,
    MetadataFilter,
    ProductionHybridRetrievalService,
    RetrievalIndexKind,
    RetrievalIndexRecord,
    RetrievalQuery,
)
from src.vyu.storage import ProductionScope, ProductionStorage


class ProductionEvidenceMemoryRetrievalTests(unittest.TestCase):
    def test_records_object_index_retrieval_run_and_memory_with_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generate_phase1_corpus(root)
            corpus = load_dummy_corpus(root)
            scope = ProductionScope(tenant_id="tenant-a", workspace_id="workspace-a")
            storage = ProductionStorage(root / "production.sqlite")
            storage.initialize()
            evidence_object = EvidenceObjectRecord(
                object_id="object-vx101-pack-v1",
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                object_uri="s3://vyu-evidence-placeholder/tenant-a/workspace-a/vx101-pack-v1.jsonl",
                object_kind=EvidenceObjectKind.EVIDENCE_PACK,
                content_type="application/jsonl",
                checksum_sha256="sha256-placeholder-evidence-pack",
                size_bytes=2048,
                source_id="dummy_corpus",
                evidence_pack_id="vx101-pack-v1",
                created_at="2026-06-28T00:00:00Z",
                metadata={"storage_backend": "s3_placeholder"},
            )
            index_record = RetrievalIndexRecord(
                index_version="idx-hybrid-vx101-v1",
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                index_kind=RetrievalIndexKind.HYBRID,
                corpus_version="synthetic-vx101-v1",
                source_ids=("dummy_corpus",),
                object_uri="s3://vyu-index-placeholder/tenant-a/workspace-a/idx-hybrid-vx101-v1/",
                checksum_sha256="sha256-placeholder-index",
                document_count=len(corpus.documents),
                passage_count=len(corpus.passages),
                created_at="2026-06-28T00:01:00Z",
                embedding_model="deterministic-dense-keyword-placeholder-v1",
                lexical_config={"backend": "bm25", "tokenizer": "vyu_tokenizer_v1"},
                semantic_config={"backend": "pgvector_placeholder"},
            )
            service = ProductionHybridRetrievalService(
                lexical_retriever=BM25Retriever.from_corpus(corpus),
                semantic_retriever=DenseKeywordRetriever.from_corpus(corpus),
                index_versions=(index_record.index_version,),
            )
            hits, retrieval_run = service.search_with_record(
                query=RetrievalQuery(
                    text="Does VX-101 reduce migraine days in adults?",
                    top_k=5,
                    metadata_filter=MetadataFilter(include_retracted=False),
                ),
                retrieval_run_id="retrieval-run-001",
                run_id="run-001",
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                user_id="user-a",
                topic="vx101-migraine",
                created_at="2026-06-28T00:02:00Z",
            )
            memory = ProductionResearchMemoryRecord(
                memory_id="memory-run-001",
                run_id="run-001",
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                user_id="user-a",
                topic="vx101-migraine",
                question="Does VX-101 reduce migraine days in adults?",
                generated_search_queries=("VX-101 migraine days adults",),
                retrieved_document_ids=retrieval_run.retrieved_document_ids,
                included_document_ids=retrieval_run.retrieved_document_ids[:2],
                excluded_documents=(
                    {"document_id": "VX101-RETRACTED-01", "reason": "retracted"},
                ),
                generated_report_ids=("report-run-001",),
                model_versions={"generator": "deterministic-poc-v1"},
                policy_versions={"retrieval_policy": "retrieval_policy_v1"},
                follow_up_decision=FollowUpDecision.SEARCH_NEW_EVIDENCE,
                source_permissions=("dummy_corpus",),
                access_labels=("public_synthetic",),
                retention_policy_id="pilot_research_memory_90d",
                retrieval_run_id=retrieval_run.retrieval_run_id,
                created_at="2026-06-28T00:03:00Z",
            )

            storage.record_evidence_object(
                evidence_object,
                run_id="run-001",
                audit_event_id="event-evidence-object",
                audit_created_at="2026-06-28T00:00:01Z",
            )
            storage.record_retrieval_index(
                index_record,
                run_id="run-001",
                audit_event_id="event-retrieval-index",
                audit_created_at="2026-06-28T00:01:01Z",
            )
            storage.record_retrieval_run(
                retrieval_run,
                audit_event_id="event-retrieval-run",
                audit_created_at="2026-06-28T00:02:01Z",
            )
            storage.record_production_research_memory(
                memory,
                audit_event_id="event-research-memory",
                audit_created_at="2026-06-28T00:03:01Z",
            )

            loaded_objects = storage.list_evidence_object_records_for_scope(scope)
            loaded_indexes = storage.list_retrieval_index_records_for_scope(scope)
            loaded_runs = storage.list_retrieval_run_records_for_scope(
                scope,
                run_id="run-001",
                user_id="user-a",
                topic="vx101-migraine",
            )
            loaded_memory = storage.latest_production_research_memory_for_scope(
                scope,
                user_id="user-a",
                topic="vx101-migraine",
            )
            wrong_scope = ProductionScope(tenant_id="tenant-b", workspace_id="workspace-a")
            wrong_scope_runs = storage.list_retrieval_run_records_for_scope(
                wrong_scope,
                run_id="run-001",
            )
            events = storage.list_audit_events(run_id="run-001")

        self.assertGreaterEqual(len(hits), 1)
        self.assertTrue(all(not hit.document.is_retracted for hit in hits))
        self.assertEqual([evidence_object.to_json()], [item.to_json() for item in loaded_objects])
        self.assertEqual([index_record.to_json()], [item.to_json() for item in loaded_indexes])
        self.assertEqual([retrieval_run.to_json()], [item.to_json() for item in loaded_runs])
        self.assertIsNotNone(loaded_memory)
        assert loaded_memory is not None
        self.assertEqual(memory.to_json(), loaded_memory.to_json())
        self.assertEqual(
            [
                "evidence_object_recorded",
                "retrieval_index_recorded",
                "retrieval_run_recorded",
                "production_research_memory_saved",
            ],
            [event.event_type for event in events],
        )
        self.assertEqual([], wrong_scope_runs)

    def test_memory_visibility_requires_user_workspace_access_labels_and_permissions(self):
        record = ProductionResearchMemoryRecord(
            memory_id="memory-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            user_id="user-a",
            topic="vx101-migraine",
            question="Summarize the evidence.",
            source_permissions=("pubmed", "internal_guidelines"),
            access_labels=("approved_public", "customer_internal"),
            created_at="2026-06-28T00:00:00Z",
        )

        self.assertTrue(
            record.is_visible_to(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                user_id="user-a",
                topic="vx101-migraine",
                allowed_source_permissions={"pubmed", "internal_guidelines"},
                access_labels={"approved_public", "customer_internal"},
            )
        )
        self.assertFalse(
            record.is_visible_to(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                user_id="user-b",
                topic="vx101-migraine",
                allowed_source_permissions={"pubmed", "internal_guidelines"},
                access_labels={"approved_public", "customer_internal"},
            )
        )
        self.assertFalse(
            record.is_visible_to(
                tenant_id="tenant-a",
                workspace_id="workspace-a",
                user_id="user-a",
                topic="vx101-migraine",
                allowed_source_permissions={"pubmed"},
                access_labels={"approved_public", "customer_internal"},
            )
        )

    def test_follow_up_decision_uses_prior_production_memory(self):
        prior = ProductionResearchMemoryRecord(
            memory_id="memory-001",
            run_id="run-001",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            user_id="user-a",
            topic="vx101-migraine",
            question="Does VX-101 reduce migraine days?",
            created_at="2026-06-28T00:00:00Z",
        )

        self.assertEqual(
            FollowUpDecision.REUSE_EXISTING_EVIDENCE,
            classify_production_follow_up("Summarize that evidence for a brief.", prior),
        )
        self.assertEqual(
            FollowUpDecision.SEARCH_NEW_EVIDENCE,
            classify_production_follow_up("Search latest preprints on VX-101.", prior),
        )
        self.assertEqual(
            FollowUpDecision.GENERATE_NEW_OUTPUT_FROM_EXISTING_EVIDENCE,
            classify_production_follow_up("Write a policy memo.", prior),
        )


if __name__ == "__main__":
    unittest.main()
