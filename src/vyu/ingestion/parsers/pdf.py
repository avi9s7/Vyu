from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from src.vyu.ingestion.parsers.base import (
    ParseResult,
    ParsedDocument,
    ParsedSection,
    SourcePosition,
    extract_identifiers_from_text,
    normalize_unicode,
)

PARSER_NAME = "vyu_pdf"
PARSER_VERSION = "1.0.0"
_DEFAULT_MAX_PAGES = 500


@dataclass(frozen=True)
class PdfDocumentParser:
    max_pages: int = _DEFAULT_MAX_PAGES

    @property
    def name(self) -> str:
        return PARSER_NAME

    @property
    def version(self) -> str:
        return PARSER_VERSION

    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".pdf"})

    def parse(self, data: bytes, *, filename: str, media_type: str) -> ParseResult:
        del filename, media_type
        if not data:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="malformed_document",
                message="PDF document is empty.",
            )
        try:
            reader = PdfReader(BytesIO(data), strict=False)
        except PdfReadError:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="malformed_document",
                message="PDF document is malformed.",
            )
        if reader.is_encrypted:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="encrypted_pdf",
                message="Encrypted PDF files are not supported.",
            )
        if len(reader.pages) > self.max_pages:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="excessive_page_count",
                message="PDF exceeds the supported page count.",
            )

        pages: list[str] = []
        warnings: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            normalized = normalize_unicode(extracted)
            pages.append(normalized)
            if not normalized.strip():
                warnings.append(f"empty_page:{page_number}")

        metadata = reader.metadata or {}
        title = _metadata_value(metadata, "/Title")
        authors = tuple(
            author.strip()
            for author in (_metadata_value(metadata, "/Author") or "").split(";")
            if author.strip()
        )
        published_at = _metadata_value(metadata, "/CreationDate")
        combined_text = "\n\n".join(pages)
        identifiers = extract_identifiers_from_text(combined_text)
        if title is None:
            for line in combined_text.splitlines():
                cleaned = line.strip()
                if cleaned:
                    title = cleaned[:500]
                    break
        section = ParsedSection(
            title=title,
            text=combined_text,
            position=SourcePosition(page=1, section="body"),
        )
        document = ParsedDocument(
            title=title,
            authors=authors,
            published_at=published_at,
            identifiers=identifiers,
            sections=(section,),
            pages=tuple(pages),
            tables=(),
            figures=(),
            references=(),
            warnings=tuple(warnings),
        )
        return ParseResult.success(
            parser_name=self.name,
            parser_version=self.version,
            document=document,
        )


def _metadata_value(metadata: object, key: str) -> str | None:
    getter = getattr(metadata, "get", None)
    if not callable(getter):
        return None
    value = getter(key)
    if value is None:
        return None
    text = normalize_unicode(str(value).strip())
    return text or None
