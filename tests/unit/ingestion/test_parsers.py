from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from pypdf import PdfWriter

from src.vyu.ingestion.parsers.docx import DocxDocumentParser
from src.vyu.ingestion.parsers.html import HtmlDocumentParser
from src.vyu.ingestion.parsers.isolated import parse_in_process, run_isolated_parse
from src.vyu.ingestion.parsers.pdf import PdfDocumentParser
from src.vyu.ingestion.parsers.text import TextDocumentParser
from tests.fixtures.ingestion.builders import (
    PUBLIC_ARTICLE_HTML,
    PUBLIC_ARTICLE_TEXT,
    build_macro_docx,
    build_minimal_pdf,
    build_sample_docx,
)


def test_text_parser_extracts_title_and_identifiers() -> None:
    parser = TextDocumentParser()
    result = parser.parse(
        PUBLIC_ARTICLE_TEXT.encode("utf-8"),
        filename="article.txt",
        media_type="text/plain",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.title == "Public Health Operations Review"
    assert result.document.identifiers["doi"] == "10.5555/public.article"
    assert "hospital operations" in result.document.pages[0]


def test_text_parser_rejects_invalid_utf8() -> None:
    parser = TextDocumentParser()

    result = parser.parse(b"\xff\xfe", filename="broken.txt", media_type="text/plain")

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "invalid_encoding"


def test_html_parser_strips_active_tags_and_extracts_table() -> None:
    parser = HtmlDocumentParser()
    result = parser.parse(
        PUBLIC_ARTICLE_HTML.encode("utf-8"),
        filename="article.html",
        media_type="text/html",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.title == "Public Health Operations Review"
    assert "removed_active_tag:script" in result.document.warnings
    assert result.document.tables[0].cells[1] == ("ICU", "24")
    assert result.document.figures[0].caption == "Figure 1. Ward layout schematic."


def test_docx_parser_extracts_title_table_and_identifiers() -> None:
    parser = DocxDocumentParser()
    payload = build_sample_docx()

    result = parser.parse(
        payload,
        filename="report.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.title == "VYU Sample Report"
    assert result.document.authors == ("VYU Fixtures",)
    assert result.document.identifiers["doi"] == "10.1234/vyu.test"
    assert result.document.identifiers["pmid"] == "12345678"
    assert result.document.tables[0].cells[1][1] == "42"


def test_docx_parser_blocks_macro_enabled_office() -> None:
    parser = DocxDocumentParser()

    result = parser.parse(
        build_macro_docx(),
        filename="macro.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "macro_enabled_office"


def test_pdf_parser_accepts_minimal_pdf() -> None:
    parser = PdfDocumentParser()
    payload = build_minimal_pdf()

    result = parser.parse(payload, filename="report.pdf", media_type="application/pdf")

    assert result.succeeded
    assert result.document is not None
    assert len(result.document.pages) == 1


def test_pdf_parser_blocks_malformed_pdf() -> None:
    parser = PdfDocumentParser()

    result = parser.parse(
        b"%PDF-1.4 not a real pdf",
        filename="broken.pdf",
        media_type="application/pdf",
    )

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "malformed_document"


def test_pdf_parser_blocks_encrypted_pdf() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    buffer = BytesIO()
    writer.write(buffer)
    parser = PdfDocumentParser()

    result = parser.parse(buffer.getvalue(), filename="secret.pdf", media_type="application/pdf")

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "encrypted_pdf"


def test_pdf_parser_blocks_excessive_page_count() -> None:
    parser = PdfDocumentParser(max_pages=2)
    payload = build_minimal_pdf(page_count=3)

    result = parser.parse(payload, filename="large.pdf", media_type="application/pdf")

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "excessive_page_count"


def test_isolated_parse_runs_in_subprocess() -> None:
    result = run_isolated_parse(
        PUBLIC_ARTICLE_TEXT.encode("utf-8"),
        filename="article.txt",
        media_type="text/plain",
        timeout_seconds=30.0,
    )

    assert result.succeeded
    assert result.document is not None
    assert result.document.title == "Public Health Operations Review"


def test_isolated_parse_timeout_returns_error() -> None:
    with patch(
        "src.vyu.ingestion.parsers.isolated.subprocess.run",
        side_effect=__import__("subprocess").TimeoutExpired(cmd="parse", timeout=0.01),
    ):
        result = run_isolated_parse(
            PUBLIC_ARTICLE_TEXT.encode("utf-8"),
            filename="article.txt",
            media_type="text/plain",
            timeout_seconds=0.01,
        )

    assert not result.succeeded
    assert result.failure is not None
    assert result.failure.code == "parser_timeout"


def test_parse_in_process_matches_direct_parser() -> None:
    direct = TextDocumentParser().parse(
        PUBLIC_ARTICLE_TEXT.encode("utf-8"),
        filename="article.txt",
        media_type="text/plain",
    )
    wrapped = parse_in_process(
        PUBLIC_ARTICLE_TEXT.encode("utf-8"),
        filename="article.txt",
        media_type="text/plain",
    )

    assert direct.document is not None
    assert wrapped.document is not None
    assert wrapped.document.title == direct.document.title
    assert wrapped.document.identifiers == direct.document.identifiers
