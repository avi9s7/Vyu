from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

PARSER_FAILURE_CODES = frozenset(
    {
        "encrypted_pdf",
        "macro_enabled_office",
        "embedded_executable",
        "malformed_archive",
        "excessive_compression_ratio",
        "excessive_page_count",
        "parser_timeout",
        "unsupported_format",
        "malformed_document",
        "invalid_encoding",
    }
)

_DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
_PMID_PATTERN = re.compile(r"\b(?:PMID|PubMed ID)[:\s]*(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SourcePosition:
    page: int | None = None
    section: str | None = None
    offset: int | None = None
    row: int | None = None
    col: int | None = None


@dataclass(frozen=True)
class ParsedSection:
    title: str | None
    text: str
    position: SourcePosition


@dataclass(frozen=True)
class ParsedTable:
    caption: str | None
    cells: tuple[tuple[str, ...], ...]
    position: SourcePosition


@dataclass(frozen=True)
class ParsedFigure:
    caption: str | None
    position: SourcePosition


@dataclass(frozen=True)
class ParsedReference:
    text: str
    identifiers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    title: str | None
    authors: tuple[str, ...]
    published_at: str | None
    identifiers: dict[str, str]
    sections: tuple[ParsedSection, ...]
    pages: tuple[str, ...]
    tables: tuple[ParsedTable, ...]
    figures: tuple[ParsedFigure, ...]
    references: tuple[ParsedReference, ...]
    warnings: tuple[str, ...]

    def to_metadata_summary(self) -> dict[str, object]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "published_at": self.published_at,
            "identifiers": dict(self.identifiers),
            "page_count": len(self.pages),
            "section_count": len(self.sections),
            "table_count": len(self.tables),
            "figure_count": len(self.figures),
            "reference_count": len(self.references),
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "authors": list(self.authors),
            "published_at": self.published_at,
            "identifiers": dict(self.identifiers),
            "sections": [
                {
                    "title": section.title,
                    "text": section.text,
                    "position": _position_to_dict(section.position),
                }
                for section in self.sections
            ],
            "pages": list(self.pages),
            "tables": [
                {
                    "caption": table.caption,
                    "cells": [list(row) for row in table.cells],
                    "position": _position_to_dict(table.position),
                }
                for table in self.tables
            ],
            "figures": [
                {
                    "caption": figure.caption,
                    "position": _position_to_dict(figure.position),
                }
                for figure in self.figures
            ],
            "references": [
                {"text": reference.text, "identifiers": dict(reference.identifiers)}
                for reference in self.references
            ],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ParsedDocument:
        return cls(
            title=_optional_str(payload.get("title")),
            authors=tuple(str(value) for value in _as_list(payload.get("authors"))),
            published_at=_optional_str(payload.get("published_at")),
            identifiers={
                str(key): str(value)
                for key, value in _as_dict(payload.get("identifiers")).items()
            },
            sections=tuple(
                ParsedSection(
                    title=_optional_str(section.get("title")),
                    text=str(section.get("text", "")),
                    position=_position_from_dict(_as_dict(section.get("position"))),
                )
                for section in _as_list(payload.get("sections"))
                if isinstance(section, dict)
            ),
            pages=tuple(str(page) for page in _as_list(payload.get("pages"))),
            tables=tuple(
                ParsedTable(
                    caption=_optional_str(table.get("caption")),
                    cells=tuple(
                        tuple(str(cell) for cell in _as_list(row))
                        for row in _as_list(table.get("cells"))
                    ),
                    position=_position_from_dict(_as_dict(table.get("position"))),
                )
                for table in _as_list(payload.get("tables"))
                if isinstance(table, dict)
            ),
            figures=tuple(
                ParsedFigure(
                    caption=_optional_str(figure.get("caption")),
                    position=_position_from_dict(_as_dict(figure.get("position"))),
                )
                for figure in _as_list(payload.get("figures"))
                if isinstance(figure, dict)
            ),
            references=tuple(
                ParsedReference(
                    text=str(reference.get("text", "")),
                    identifiers={
                        str(key): str(value)
                        for key, value in _as_dict(reference.get("identifiers")).items()
                    },
                )
                for reference in _as_list(payload.get("references"))
                if isinstance(reference, dict)
            ),
            warnings=tuple(str(value) for value in _as_list(payload.get("warnings"))),
        )


@dataclass(frozen=True)
class ParserFailure:
    code: str
    message: str


@dataclass(frozen=True)
class ParseResult:
    parser_name: str
    parser_version: str
    document: ParsedDocument | None = None
    failure: ParserFailure | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure is None and self.document is not None

    @classmethod
    def success(
        cls,
        *,
        parser_name: str,
        parser_version: str,
        document: ParsedDocument,
    ) -> ParseResult:
        return cls(parser_name=parser_name, parser_version=parser_version, document=document)

    @classmethod
    def failed(
        cls,
        *,
        parser_name: str,
        parser_version: str,
        code: str,
        message: str,
    ) -> ParseResult:
        return cls(
            parser_name=parser_name,
            parser_version=parser_version,
            failure=ParserFailure(code=code, message=message),
        )


class DocumentParser(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def supported_extensions(self) -> frozenset[str]: ...

    def parse(self, data: bytes, *, filename: str, media_type: str) -> ParseResult: ...


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")


def extract_identifiers_from_text(text: str) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    doi_match = _DOI_PATTERN.search(text)
    if doi_match is not None:
        identifiers["doi"] = doi_match.group(0)
    pmid_match = _PMID_PATTERN.search(text)
    if pmid_match is not None:
        identifiers["pmid"] = pmid_match.group(1)
    return identifiers


def get_parser_for_filename(filename: str) -> DocumentParser:
    extension = _extension_for(filename)
    if extension == ".pdf":
        from src.vyu.ingestion.parsers.pdf import PdfDocumentParser

        return PdfDocumentParser()
    if extension == ".docx":
        from src.vyu.ingestion.parsers.docx import DocxDocumentParser

        return DocxDocumentParser()
    if extension == ".txt":
        from src.vyu.ingestion.parsers.text import TextDocumentParser

        return TextDocumentParser()
    if extension == ".html":
        from src.vyu.ingestion.parsers.html import HtmlDocumentParser

        return HtmlDocumentParser()
    raise ValueError(f"unsupported parser extension: {extension}")


def _extension_for(filename: str) -> str:
    dot_index = filename.rfind(".")
    if dot_index <= 0:
        raise ValueError("filename has no extension")
    return filename[dot_index:].lower()


def _position_to_dict(position: SourcePosition) -> dict[str, int | str | None]:
    return {
        "page": position.page,
        "section": position.section,
        "offset": position.offset,
        "row": position.row,
        "col": position.col,
    }


def _position_from_dict(payload: dict[str, object]) -> SourcePosition:
    return SourcePosition(
        page=_optional_int(payload.get("page")),
        section=_optional_str(payload.get("section")),
        offset=_optional_int(payload.get("offset")),
        row=_optional_int(payload.get("row")),
        col=_optional_int(payload.get("col")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    return {}
