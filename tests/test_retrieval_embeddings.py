from __future__ import annotations

import unittest
from uuid import uuid4

from src.vyu.retrieval.embeddings import (
    DeterministicEmbeddingProvider,
    EmbeddingDimensionMismatchError,
    embedding_cache_key,
    text_sha256,
    validate_embedding_dimensions,
)
from src.vyu.retrieval.index_contracts import (
    APPROVED_EMBEDDING_DIMENSIONS,
    DocumentVersionRef,
    IndexManifest,
    manifest_checksum,
)


class RetrievalEmbeddingsTests(unittest.TestCase):
    def test_text_sha256_is_stable(self) -> None:
        value = text_sha256("aspirin efficacy")
        assert value == text_sha256("aspirin efficacy")
        assert len(value) == 64

    def test_embedding_cache_key_includes_provider_model_dimensions(self) -> None:
        text_hash = text_sha256("sample")
        first = embedding_cache_key(
            text_sha256_value=text_hash,
            provider="deterministic",
            model="vyu-deterministic-v1",
            dimensions=APPROVED_EMBEDDING_DIMENSIONS,
        )
        second = embedding_cache_key(
            text_sha256_value=text_hash,
            provider="deterministic",
            model="other-model",
            dimensions=APPROVED_EMBEDDING_DIMENSIONS,
        )
        assert first != second

    def test_validate_embedding_dimensions_rejects_mismatch(self) -> None:
        with self.assertRaises(EmbeddingDimensionMismatchError):
            validate_embedding_dimensions(768)

    def test_deterministic_provider_returns_batch_contract(self) -> None:
        provider = DeterministicEmbeddingProvider()
        batch = provider.embed(
            ["aspirin", "efficacy"],
            model="vyu-deterministic-v1",
            dimensions=APPROVED_EMBEDDING_DIMENSIONS,
        )
        self.assertEqual(batch.provider, "deterministic")
        self.assertEqual(batch.model, "vyu-deterministic-v1")
        self.assertEqual(batch.dimensions, APPROVED_EMBEDDING_DIMENSIONS)
        self.assertEqual(len(batch.input_hashes), 2)
        self.assertEqual(len(batch.vectors), 2)
        self.assertEqual(batch.vectors[0].text_sha256, batch.input_hashes[0])
        self.assertEqual(len(batch.vectors[0].values), APPROVED_EMBEDDING_DIMENSIONS)
        self.assertIsNotNone(batch.provider_request_id)
        self.assertGreaterEqual(batch.latency_ms, 0)
        self.assertGreater(batch.usage.total_tokens, 0)

    def test_manifest_checksum_is_stable(self) -> None:
        tenant_id = uuid4()
        workspace_id = uuid4()
        manifest = IndexManifest(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            use_case="evidence_memory",
            source_ids=("pubmed",),
            document_versions=(
                DocumentVersionRef(
                    document_id="doc-1",
                    version_number=1,
                    document_version_id=str(uuid4()),
                ),
            ),
            chunker_name="vyu_section_chunker",
            chunker_version="1.0.0",
            embedding_provider="deterministic",
            embedding_model="vyu-deterministic-v1",
            embedding_dimensions=APPROVED_EMBEDDING_DIMENSIONS,
            build_git_sha="abc123",
            policy_version="source-policy-v1",
        )
        first = manifest_checksum(manifest)
        second = manifest_checksum(manifest)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
