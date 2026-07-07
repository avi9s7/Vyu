from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from src.vyu.ingestion.parsers.base import ParsedDocument, ParsedSection, ParsedTable

CHUNKER_NAME = "vyu_section_chunker"
CHUNKER_VERSION = "1.0.0"
TARGET_TOKENS = 600
MAX_TOKENS = 900
OVERLAP_TOKENS = 80

_TOKEN_PATTERN = re.compile(r"\S+")


@dataclass(frozen=True)
class ChunkDraft:
    ordinal: int
    citation_id: str
    text: str
    text_sha256: str
    token_count: int
    page_from: int | None
    page_to: int | None
    section: str | None
    metadata_json: dict[str, object]


def count_tokens(text: str) -> int:
    return len(_TOKEN_PATTERN.findall(text))


def build_citation_id(*, document_id: UUID, version_number: int, ordinal: int) -> str:
    return f"doc:{document_id}:v:{version_number}:chunk:{ordinal}"


def chunk_parsed_document(
    parsed: ParsedDocument,
    *,
    document_id: UUID,
    version_number: int,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> tuple[ChunkDraft, ...]:
    drafts: list[ChunkDraft] = []
    ordinal = 1

    for section_index, section in enumerate(parsed.sections):
        section_label = section.title or section.position.section or f"section_{section_index + 1}"
        section_text = _section_text(section)
        if section_text.strip():
            for chunk_text in _split_text(
                section_text,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
            ):
                drafts.append(
                    _build_chunk_draft(
                        document_id=document_id,
                        version_number=version_number,
                        ordinal=ordinal,
                        text=chunk_text,
                        section=section_label,
                        page_from=section.position.page,
                        page_to=section.position.page,
                        metadata_json={"chunk_kind": "section"},
                    )
                )
                ordinal += 1

    for table_index, table in enumerate(parsed.tables):
        table_text = _table_text(table)
        if not table_text.strip():
            continue
        for chunk_text in _split_text(
            table_text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            drafts.append(
                _build_chunk_draft(
                    document_id=document_id,
                    version_number=version_number,
                    ordinal=ordinal,
                    text=chunk_text,
                    section=table.position.section or f"table_{table_index + 1}",
                    page_from=table.position.page,
                    page_to=table.position.page,
                    metadata_json={"chunk_kind": "table"},
                )
            )
            ordinal += 1

    if not drafts and parsed.pages:
        page_text = "\n\n".join(page for page in parsed.pages if page.strip())
        for chunk_text in _split_text(
            page_text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        ):
            drafts.append(
                _build_chunk_draft(
                    document_id=document_id,
                    version_number=version_number,
                    ordinal=ordinal,
                    text=chunk_text,
                    section="body",
                    page_from=1,
                    page_to=len(parsed.pages),
                    metadata_json={"chunk_kind": "page_fallback"},
                )
            )
            ordinal += 1

    return tuple(drafts)


def _section_text(section: ParsedSection) -> str:
    if section.title and section.text:
        return f"{section.title}\n\n{section.text}"
    if section.title:
        return section.title
    return section.text


def _table_text(table: ParsedTable) -> str:
    lines: list[str] = []
    if table.caption:
        lines.append(table.caption)
    for row in table.cells:
        lines.append(" | ".join(cell for cell in row if cell))
    return "\n".join(lines)


def _split_text(
    text: str,
    *,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    tokens = _TOKEN_PATTERN.findall(text)
    if not tokens:
        return []
    if len(tokens) <= max_tokens:
        return [" ".join(tokens)]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        if end < len(tokens):
            preferred_end = min(start + target_tokens, end)
            if preferred_end > start:
                end = preferred_end
        chunk_tokens = tokens[start:end]
        chunks.append(" ".join(chunk_tokens))
        if end >= len(tokens):
            break
        start = max(end - overlap_tokens, start + 1)
    return chunks


def _build_chunk_draft(
    *,
    document_id: UUID,
    version_number: int,
    ordinal: int,
    text: str,
    section: str | None,
    page_from: int | None,
    page_to: int | None,
    metadata_json: dict[str, object],
) -> ChunkDraft:
    normalized_text = text.strip()
    return ChunkDraft(
        ordinal=ordinal,
        citation_id=build_citation_id(
            document_id=document_id,
            version_number=version_number,
            ordinal=ordinal,
        ),
        text=normalized_text,
        text_sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        token_count=count_tokens(normalized_text),
        page_from=page_from,
        page_to=page_to,
        section=section,
        metadata_json=metadata_json,
    )
