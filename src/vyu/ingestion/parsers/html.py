from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup

from src.vyu.ingestion.parsers.base import (
    ParseResult,
    ParsedDocument,
    ParsedFigure,
    ParsedSection,
    ParsedTable,
    SourcePosition,
    extract_identifiers_from_text,
    normalize_unicode,
)

PARSER_NAME = "vyu_html"
PARSER_VERSION = "1.0.0"
_ACTIVE_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "link", "meta"})


@dataclass(frozen=True)
class HtmlDocumentParser:
    @property
    def name(self) -> str:
        return PARSER_NAME

    @property
    def version(self) -> str:
        return PARSER_VERSION

    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".html"})

    def parse(self, data: bytes, *, filename: str, media_type: str) -> ParseResult:
        del filename, media_type
        if not data:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="malformed_document",
                message="HTML document is empty.",
            )
        try:
            html = data.decode("utf-8")
        except UnicodeDecodeError:
            return ParseResult.failed(
                parser_name=self.name,
                parser_version=self.version,
                code="invalid_encoding",
                message="HTML document is not valid UTF-8.",
            )
        soup = BeautifulSoup(html, "html.parser")
        warnings: list[str] = []
        for tag_name in _ACTIVE_TAGS:
            if soup.find(tag_name) is not None:
                warnings.append(f"removed_active_tag:{tag_name}")
        for tag in soup.find_all(_ACTIVE_TAGS):
            tag.decompose()

        title = _extract_title(soup)
        body = soup.body or soup
        sections: list[ParsedSection] = []
        for index, heading in enumerate(body.find_all(["h1", "h2", "h3"])):
            heading_text = normalize_unicode(heading.get_text(" ", strip=True))
            section_text = normalize_unicode(_section_text_after_heading(heading))
            sections.append(
                ParsedSection(
                    title=heading_text or None,
                    text=section_text,
                    position=SourcePosition(section=heading_text or f"section_{index + 1}"),
                )
            )
        if not sections:
            body_text = normalize_unicode(body.get_text("\n", strip=True))
            sections.append(
                ParsedSection(
                    title=None,
                    text=body_text,
                    position=SourcePosition(section="body"),
                )
            )

        tables: list[ParsedTable] = []
        for table_index, table in enumerate(body.find_all("table")):
            rows: list[tuple[str, ...]] = []
            for row in table.find_all("tr"):
                cells = tuple(
                    normalize_unicode(cell.get_text(" ", strip=True))
                    for cell in row.find_all(["th", "td"])
                )
                if cells:
                    rows.append(cells)
            caption_tag = table.find("caption")
            caption = (
                normalize_unicode(caption_tag.get_text(" ", strip=True))
                if caption_tag is not None
                else None
            )
            tables.append(
                ParsedTable(
                    caption=caption,
                    cells=tuple(rows),
                    position=SourcePosition(section="table", row=table_index + 1),
                )
            )
            if not rows:
                warnings.append("unsupported_table:empty")

        figures: list[ParsedFigure] = []
        for figure_index, figure in enumerate(body.find_all("figure")):
            caption_tag = figure.find("figcaption")
            caption = (
                normalize_unicode(caption_tag.get_text(" ", strip=True))
                if caption_tag is not None
                else None
            )
            figures.append(
                ParsedFigure(
                    caption=caption,
                    position=SourcePosition(section="figure", row=figure_index + 1),
                )
            )
            if caption is None:
                warnings.append("unsupported_figure:missing_caption")

        page_text = normalize_unicode(body.get_text("\n", strip=True))
        identifiers = extract_identifiers_from_text(page_text)
        document = ParsedDocument(
            title=title,
            authors=(),
            published_at=None,
            identifiers=identifiers,
            sections=tuple(sections),
            pages=(page_text,),
            tables=tuple(tables),
            figures=tuple(figures),
            references=(),
            warnings=tuple(warnings),
        )
        return ParseResult.success(
            parser_name=self.name,
            parser_version=self.version,
            document=document,
        )


def _extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title is not None and soup.title.string:
        return normalize_unicode(str(soup.title.string).strip())[:500]
    heading = soup.find(["h1", "h2"])
    if heading is not None:
        return normalize_unicode(heading.get_text(" ", strip=True))[:500]
    return None


def _section_text_after_heading(heading: object) -> str:
    chunks: list[str] = []
    for sibling in getattr(heading, "next_siblings", []):
        name = getattr(sibling, "name", None)
        if name in {"h1", "h2", "h3"}:
            break
        text = getattr(sibling, "get_text", None)
        if callable(text):
            chunks.append(text("\n", strip=True))
    return "\n".join(chunk for chunk in chunks if chunk)
