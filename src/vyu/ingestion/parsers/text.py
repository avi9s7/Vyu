from __future__ import annotations

from dataclasses import dataclass

from src.vyu.ingestion.parsers.base import (
    ParseResult,
    ParsedDocument,
    ParsedSection,
    SourcePosition,
    extract_identifiers_from_text,
    normalize_unicode,
)

PARSER_NAME = "vyu_text"
PARSER_VERSION = "1.0.0"


@dataclass(frozen=True)
class TextDocumentParser:
    @property
    def name(self) -> str:
        return PARSER_NAME

    @property
    def version(self) -> str:
        return PARSER_VERSION

    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".txt"})

    def parse(self, data: bytes, *, filename: str, media_type: str) -> ParseResult:
        del filename, media_type
        if not data:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="malformed_document",
                message="Text document is empty.",
            )
        try:
            text = normalize_unicode(data.decode("utf-8"))
        except UnicodeDecodeError:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="invalid_encoding",
                message="Text document is not valid UTF-8.",
            )
        title = _title_from_text(text)
        identifiers = extract_identifiers_from_text(text)
        section = ParsedSection(
            title=None,
            text=text,
            position=SourcePosition(section="body", offset=0),
        )
        document = ParsedDocument(
            title=title,
            authors=(),
            published_at=None,
            identifiers=identifiers,
            sections=(section,),
            pages=(text,),
            tables=(),
            figures=(),
            references=(),
            warnings=(),
        )
        return ParseResult.success(
            parser_name=self.name,
            parser_version=self.version,
            document=document,
        )


def _title_from_text(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned[:500]
    return None
