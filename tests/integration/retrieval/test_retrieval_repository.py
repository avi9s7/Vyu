from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.vyu.db.session import TenantScope, build_engine, build_session_factory, transaction
from src.vyu.db.settings import DatabaseSettings
from src.vyu.ingestion.chunking import CHUNKER_NAME, CHUNKER_VERSION
from src.vyu.ingestion.models import Document, DocumentChunk, DocumentVersion
from src.vyu.retrieval.embeddings import APPROVED_EMBEDDING_DIMENSIONS, DeterministicEmbeddingProvider
from src.vyu.retrieval.index_contracts import (
    DocumentVersionRef,
    IndexActivationError,
    IndexEvaluationResult,
    IndexManifest,
    IndexStatus,
    manifest_checksum,
)
from src.vyu.retrieval.models import ChunkEmbedding, RetrievalIndex, RetrievalRun
from src.vyu.retrieval.repository import RetrievalHitDraft, RetrievalIndexRepository


@pytest.fixture
def retrieval_factory(postgres_urls: dict[str, str]):
    return build_session_factory(
        build_engine(DatabaseSettings(database_url=postgres_urls["migration"]))
    )


def _seed_document_chunk(scope: TenantScope, factory) -> tuple:
    document_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()
    chunk_text = "Aspirin reduces cardiovascular risk in selected populations."
    with transaction(factory, scope=scope) as session:
        session.add(
            Document(
                id=document_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                source_id="internal_documents",
                status="ready",
                created_by=uuid4(),
                current_version_id=version_id,
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
    return document_id, version_id, chunk_id, chunk_text


def _build_manifest(scope: TenantScope, *, version_id, document_id) -> IndexManifest:
    return IndexManifest(
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
        embedding_dimensions=APPROVED_EMBEDDING_DIMENSIONS,
        build_git_sha="test-sha",
        policy_version="source-policy-v1",
    )


def test_repository_creates_index_and_reuses_manifest_checksum(retrieval_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    document_id, version_id, _chunk_id, _chunk_text = _seed_document_chunk(scope, retrieval_factory)
    manifest = _build_manifest(scope, version_id=version_id, document_id=document_id)
    repository = RetrievalIndexRepository()
    with transaction(retrieval_factory, scope=scope) as session:
        first = repository.create_index(
            session,
            manifest=manifest,
            document_count=1,
            chunk_count=1,
        )
        second = repository.create_index(
            session,
            manifest=manifest,
            document_count=1,
            chunk_count=1,
        )
        rows = session.scalars(select(RetrievalIndex)).all()
    assert first.index_id == second.index_id
    assert first.manifest_checksum == manifest_checksum(manifest)
    assert len(rows) == 1


def test_embedding_cache_is_scoped_to_tenant(retrieval_factory) -> None:
    scope_a = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    scope_b = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    _, version_a, chunk_a_id, chunk_a_text = _seed_document_chunk(scope_a, retrieval_factory)
    _, version_b, chunk_b_id, chunk_b_text = _seed_document_chunk(scope_b, retrieval_factory)
    provider = DeterministicEmbeddingProvider()
    batch = provider.embed([chunk_a_text], dimensions=APPROVED_EMBEDDING_DIMENSIONS)
    repository = RetrievalIndexRepository()

    manifest_a = _build_manifest(scope_a, version_id=version_a, document_id=uuid4())
    manifest_b = _build_manifest(scope_b, version_id=version_b, document_id=uuid4())
    with transaction(retrieval_factory, scope=scope_a) as session:
        index_a = repository.create_index(session, manifest=manifest_a, document_count=1, chunk_count=1)
        repository.save_embedding_batch(
            session,
            tenant_id=scope_a.tenant_id,
            workspace_id=scope_a.workspace_id,
            retrieval_index_id=index_a.index_id,
            document_chunk_id=chunk_a_id,
            batch=batch,
            vector_index=0,
        )
    with transaction(retrieval_factory, scope=scope_b) as session:
        index_b = repository.create_index(session, manifest=manifest_b, document_count=1, chunk_count=1)
        saved_b = repository.save_embedding_batch(
            session,
            tenant_id=scope_b.tenant_id,
            workspace_id=scope_b.workspace_id,
            retrieval_index_id=index_b.index_id,
            document_chunk_id=chunk_b_id,
            batch=batch,
            vector_index=0,
        )
        cached = repository.lookup_cached_embeddings(
            session,
            tenant_id=scope_b.tenant_id,
            text_hashes=(batch.vectors[0].text_sha256,),
            provider=batch.provider,
            model=batch.model,
            dimensions=batch.dimensions,
        )
        rows = session.scalars(select(ChunkEmbedding)).all()
    assert saved_b.id not in {row.id for row in rows if row.tenant_id == scope_a.tenant_id}
    assert batch.vectors[0].text_sha256 in cached
    assert len(rows) == 2


def test_activate_index_is_transactional_and_retires_previous_active(retrieval_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    document_id, version_id, _chunk_id, _chunk_text = _seed_document_chunk(scope, retrieval_factory)
    repository = RetrievalIndexRepository()
    evaluation = IndexEvaluationResult(suite="retrieval_baseline", passed=True, metrics={"ndcg": 0.9})

    manifest_one = _build_manifest(scope, version_id=version_id, document_id=document_id)
    manifest_two = IndexManifest(
        tenant_id=scope.tenant_id,
        workspace_id=scope.workspace_id,
        use_case="evidence_memory",
        source_ids=("internal_documents",),
        document_versions=manifest_one.document_versions,
        chunker_name=CHUNKER_NAME,
        chunker_version=CHUNKER_VERSION,
        embedding_provider="deterministic",
        embedding_model="vyu-deterministic-v1",
        embedding_dimensions=APPROVED_EMBEDDING_DIMENSIONS,
        build_git_sha="test-sha-2",
        policy_version="source-policy-v1",
    )

    with transaction(retrieval_factory, scope=scope) as session:
        first = repository.create_index(session, manifest=manifest_one, document_count=1, chunk_count=1)
        repository.update_status(session, index_id=first.index_id, status=IndexStatus.VALIDATING)
        repository.update_status(
            session,
            index_id=first.index_id,
            status=IndexStatus.VALIDATING,
            evaluation_result=evaluation,
        )
        activated_first = repository.activate_index(
            session,
            index_id=first.index_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        second = repository.create_index(session, manifest=manifest_two, document_count=1, chunk_count=1)
        repository.update_status(
            session,
            index_id=second.index_id,
            status=IndexStatus.VALIDATING,
            evaluation_result=evaluation,
        )
        activated_second = repository.activate_index(
            session,
            index_id=second.index_id,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
        rows = session.scalars(select(RetrievalIndex).order_by(RetrievalIndex.created_at.asc())).all()

    assert activated_first.status == IndexStatus.ACTIVE
    assert activated_second.status == IndexStatus.ACTIVE
    assert rows[0].status == IndexStatus.RETIRED.value
    assert rows[1].status == IndexStatus.ACTIVE.value
    with transaction(retrieval_factory, scope=scope) as session:
        active = repository.get_active_index(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
        )
    assert active is not None
    assert active.index_id == activated_second.index_id


def test_activate_index_fails_without_passing_evaluation(retrieval_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    document_id, version_id, _chunk_id, _chunk_text = _seed_document_chunk(scope, retrieval_factory)
    repository = RetrievalIndexRepository()
    manifest = _build_manifest(scope, version_id=version_id, document_id=document_id)
    with transaction(retrieval_factory, scope=scope) as session:
        created = repository.create_index(session, manifest=manifest, document_count=1, chunk_count=1)
        repository.update_status(session, index_id=created.index_id, status=IndexStatus.VALIDATING)
        with pytest.raises(IndexActivationError):
            repository.activate_index(
                session,
                index_id=created.index_id,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
            )


def test_save_retrieval_run_is_idempotent(retrieval_factory) -> None:
    scope = TenantScope(tenant_id=uuid4(), workspace_id=uuid4())
    document_id, version_id, chunk_id, _chunk_text = _seed_document_chunk(scope, retrieval_factory)
    repository = RetrievalIndexRepository()
    manifest = _build_manifest(scope, version_id=version_id, document_id=document_id)
    with transaction(retrieval_factory, scope=scope) as session:
        index = repository.create_index(session, manifest=manifest, document_count=1, chunk_count=1)
        first = repository.save_retrieval_run(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            retrieval_run_key="retrieval-run-001",
            workflow_run_id="workflow-001",
            retrieval_index_id=index.index_id,
            user_id="user-1",
            topic="cardiology",
            question="aspirin efficacy",
            retrieval_mode="hybrid_rrf_v1",
            top_k=5,
            query_metadata_filter={},
            retriever_versions={"bm25": "v1"},
            latency_ms=12,
            evaluation_suite=None,
            hits=(
                RetrievalHitDraft(
                    document_id=str(document_id),
                    passage_id="doc:test:v:1:chunk:0",
                    document_chunk_id=chunk_id,
                    rank=1,
                    score_source="bm25",
                    score_value=0.9,
                    score_components={"bm25": 0.9},
                    trace={"retriever": "bm25"},
                ),
            ),
        )
        second = repository.save_retrieval_run(
            session,
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            retrieval_run_key="retrieval-run-001",
            workflow_run_id="workflow-001",
            retrieval_index_id=index.index_id,
            user_id="user-1",
            topic="cardiology",
            question="aspirin efficacy",
            retrieval_mode="hybrid_rrf_v1",
            top_k=5,
            query_metadata_filter={},
            retriever_versions={"bm25": "v1"},
            latency_ms=12,
            evaluation_suite=None,
            hits=(),
        )
        rows = session.scalars(select(RetrievalRun)).all()
    assert first.id == second.id
    assert len(rows) == 1
