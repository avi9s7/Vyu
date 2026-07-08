from __future__ import annotations

from uuid import uuid4

import pytest

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION
from src.vyu.ingestion.models import Document, DocumentChunk, DocumentVersion
from src.vyu.jobs.models import ResearchRun
from src.vyu.retrieval.index_contracts import DocumentVersionRef, IndexManifest, IndexStatus
from src.vyu.retrieval.repository import RetrievalHitDraft, RetrievalIndexRepository
from src.vyu.synthesis.context import EvidenceContextBuilder, EvidenceContextBuildError


@pytest.fixture
def synthesis_factory(postgres_urls: dict[str, str]):
    return build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )


def test_builder_loads_persisted_retrieval_run_and_hashes_context(synthesis_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()
    chunk_text = "Aspirin reduces cardiovascular risk in selected populations."
    research_run_id = uuid4()

    with transaction(synthesis_factory, scope=scope) as session:
        session.add(
            ResearchRun(
                id=research_run_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                created_by=uuid4(),
                question="What is the cardiovascular evidence?",
                intended_use="research",
                requested_sources=["internal_documents"],
                status="retrieving",
                policy_version="source-policy-v1",
            )
        )
        session.add(
            Document(
                id=document_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                source_id="internal_documents",
                status="ready",
                created_by=uuid4(),
                current_version_id=version_id,
                title="Aspirin trial",
            )
        )
        session.add(
            DocumentVersion(
                id=version_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                document_id=document_id,
                version=1,
                sha256="a" * 64,
            )
        )
        session.add(
            DocumentChunk(
                id=chunk_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                document_version_id=version_id,
                ordinal=0,
                citation_id="doc:test:v:1:chunk:0",
                text=chunk_text,
                text_sha256=__import__("hashlib").sha256(chunk_text.encode("utf-8")).hexdigest(),
                token_count=10,
            )
        )
        session.flush()

        manifest = IndexManifest(
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            use_case="evidence_memory",
            source_ids=("internal_documents",),
            document_versions=(
                DocumentVersionRef(
                    document_id=str(document_id),
                    version_number=1,
                    document_version_id=str(version_id),
                ),
            ),
            chunker_name=CHUNKER_NAME,
            chunker_version=CHUNKER_VERSION,
            embedding_provider="deterministic",
            embedding_model="vyu-deterministic-v1",
            embedding_dimensions=1536,
            build_git_sha="test-sha",
            policy_version="source-policy-v1",
        )
        repository = RetrievalIndexRepository()
        index = repository.create_index(
            session,
            manifest=manifest,
            document_count=1,
            chunk_count=1,
            status=IndexStatus.ACTIVE,
        )
        retrieval_run = repository.save_retrieval_run(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            retrieval_run_key="retrieval-run-1",
            workflow_run_id=str(research_run_id),
            retrieval_index_id=index.index_id,
            user_id="reviewer-1",
            topic="cardiovascular",
            question="What is the cardiovascular evidence?",
            retrieval_mode="hybrid",
            top_k=5,
            query_metadata_filter={},
            retriever_versions={"lexical": "v1", "vector": "v1"},
            latency_ms=12,
            evaluation_suite=None,
            hits=(
                RetrievalHitDraft(
                    document_id=str(document_id),
                    passage_id="doc:test:v:1:chunk:0",
                    document_chunk_id=chunk_id,
                    rank=1,
                    score_source="hybrid",
                    score_value=0.91,
                    score_components={"rrf": 0.91},
                    trace={"rank": 1},
                ),
            ),
        )

        builder = EvidenceContextBuilder()
        context = builder.build_from_session(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            research_run_id=research_run_id,
            retrieval_run_id=retrieval_run.id,
            max_tokens=100,
        )
        assert len(context.items) == 1
        assert context.items[0].citation_id == "doc:test:v:1:chunk:0"
        assert context.context_sha256
        assert "Aspirin reduces cardiovascular risk" in context.to_prompt_block()

        with pytest.raises(EvidenceContextBuildError):
            builder.build_from_session(
                session,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                research_run_id=uuid4(),
                retrieval_run_id=retrieval_run.id,
                max_tokens=100,
            )
