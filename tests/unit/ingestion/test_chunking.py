from __future__ import annotations

from uuid import uuid4

from src.vyu.ingestion.chunking import (
    TARGET_TOKENS,
    build_citation_id,
    chunk_parsed_document,
    count_tokens,
)
from src.vyu.ingestion.parsers.base import ParsedDocument, ParsedSection, ParsedTable, SourcePosition


def test_count_tokens_uses_whitespace_tokens() -> None:
    assert count_tokens("one two three") == 3


def test_build_citation_id_format() -> None:
    document_id = uuid4()
    assert (
        build_citation_id(document_id=document_id, version_number=2, ordinal=3)
        == f"doc:{document_id}:v:2:chunk:3"
    )


def test_chunker_splits_oversized_section_with_overlap() -> None:
    words = [f"word{i}" for i in range(1000)]
    text = " ".join(words)
    parsed = ParsedDocument(
        title="Large Section",
        authors=(),
        published_at=None,
        identifiers={},
        sections=(
            ParsedSection(
                title="Section A",
                text=text,
                position=SourcePosition(section="Section A", page=1),
            ),
        ),
        pages=(text,),
        tables=(),
        figures=(),
        references=(),
        warnings=(),
    )

    chunks = chunk_parsed_document(
        parsed,
        document_id=uuid4(),
        version_number=1,
        target_tokens=TARGET_TOKENS,
        max_tokens=900,
        overlap_tokens=80,
    )

    assert len(chunks) >= 2
    assert chunks[0].token_count <= 900
    assert chunks[1].token_count <= 900
    assert chunks[0].section == "Section A"
    assert chunks[0].citation_id.endswith(":chunk:1")
    assert chunks[1].citation_id.endswith(":chunk:2")


def test_chunker_emits_table_chunks() -> None:
    parsed = ParsedDocument(
        title="Table Doc",
        authors=(),
        published_at=None,
        identifiers={},
        sections=(),
        pages=(),
        tables=(
            ParsedTable(
                caption="Metrics",
                cells=(("A", "B"), ("1", "2")),
                position=SourcePosition(section="table", page=1),
            ),
        ),
        figures=(),
        references=(),
        warnings=(),
    )

    chunks = chunk_parsed_document(parsed, document_id=uuid4(), version_number=1)

    assert len(chunks) == 1
    assert chunks[0].metadata_json["chunk_kind"] == "table"
    assert "Metrics" in chunks[0].text
    assert "A | B" in chunks[0].text


def test_chunker_is_deterministic() -> None:
    document_id = uuid4()
    parsed = ParsedDocument(
        title="Deterministic",
        authors=(),
        published_at=None,
        identifiers={},
        sections=(
            ParsedSection(
                title="Intro",
                text="Stable chunk text for hashing.",
                position=SourcePosition(section="Intro"),
            ),
        ),
        pages=("Stable chunk text for hashing.",),
        tables=(),
        figures=(),
        references=(),
        warnings=(),
    )

    first = chunk_parsed_document(parsed, document_id=document_id, version_number=1)
    second = chunk_parsed_document(parsed, document_id=document_id, version_number=1)

    assert [(chunk.ordinal, chunk.text_sha256, chunk.citation_id) for chunk in first] == [
        (chunk.ordinal, chunk.text_sha256, chunk.citation_id) for chunk in second
    ]
