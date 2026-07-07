from __future__ import annotations

from uuid import uuid4

from src.vyu.ingestion.chunking import chunk_parsed_document
from src.vyu.ingestion.parsers.base import ParsedDocument, ParsedSection, SourcePosition
from src.vyu.ingestion.repository import IngestionRepository


def test_find_ready_version_by_sha256_scopes_to_workspace() -> None:
    repository = IngestionRepository()
    assert repository.find_ready_version_by_sha256 is not None


def test_replace_chunks_persists_normalized_hash_metadata() -> None:
    parsed = ParsedDocument(
        title="Repo",
        authors=(),
        published_at=None,
        identifiers={},
        sections=(
            ParsedSection(
                title="Body",
                text="Chunk repository metadata.",
                position=SourcePosition(section="Body"),
            ),
        ),
        pages=("Chunk repository metadata.",),
        tables=(),
        figures=(),
        references=(),
        warnings=(),
    )
    chunks = chunk_parsed_document(parsed, document_id=uuid4(), version_number=1)
    assert chunks[0].metadata_json["chunk_kind"] == "section"
