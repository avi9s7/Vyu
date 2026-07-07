from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from src.vyu.connectors.pubmed.contracts import PubMedRecord, PubMedSearchPage, PubMedSearchRequest
from src.vyu.research_mcp.hashing import stable_hash


FETCH_BATCH_SIZE = 200
NORMALIZATION_SCHEMA_VERSION = "pubmed-record-v1"


def normalize_search_payload(payload: dict[str, Any], *, raw_body: bytes) -> PubMedSearchPage:
    result = payload.get("esearchresult", payload)
    ids = tuple(str(identifier) for identifier in result.get("idlist", result.get("ids", [])))
    retstart = int(result.get("retstart", 0))
    count = int(result.get("count", len(ids)))
    next_page_token: str | None = None
    if retstart + len(ids) < count and ids:
        next_page_token = str(retstart + len(ids))
    return PubMedSearchPage(
        ids=ids,
        next_page_token=next_page_token,
        total_count=count,
        raw_response_hash=_body_hash(raw_body),
    )


def normalize_fetch_payload(payload: dict[str, Any], *, raw_body: bytes) -> list[PubMedRecord]:
    if "articles" in payload:
        return [
            _record_from_article_dict(article, raw_body=raw_body)
            for article in payload["articles"]
            if isinstance(article, dict)
        ]
    if "xml" in payload:
        return parse_pubmed_xml(str(payload["xml"]), raw_body=raw_body)
    if "documents" in payload:
        return [
            _record_from_summary_dict(document, raw_body=raw_body)
            for document in payload["documents"]
            if isinstance(document, dict)
        ]
    return []


def parse_pubmed_xml(xml_text: str, *, raw_body: bytes | None = None) -> list[PubMedRecord]:
    root = ET.fromstring(xml_text)
    records: list[PubMedRecord] = []
    for article in root.findall(".//PubmedArticle"):
        records.append(_record_from_xml_article(article, raw_body=raw_body or xml_text.encode("utf-8")))
    return records


def pubmed_record_to_document_fields(record: PubMedRecord) -> dict[str, Any]:
    year = _year_from_date(record.publication_date)
    return {
        "document_id": record.document_id,
        "title": record.title,
        "year": year,
        "study_design": _study_design_from_publication_types(record.publication_types),
        "source_type": "pubmed",
        "publication_status": "retracted" if record.is_retracted else "peer_reviewed",
        "abstract": record.abstract,
        "authors": record.authors,
        "journal": record.journal,
        "doi": record.doi,
        "pmid": record.pmid,
        "is_retracted": record.is_retracted,
    }


def _record_from_xml_article(article: ET.Element, *, raw_body: bytes) -> PubMedRecord:
    pmid = _find_text(article, ".//PMID") or _find_article_id(article, "pubmed")
    title = _find_text(article, ".//ArticleTitle") or f"PubMed record {pmid}"
    abstract = _join_abstract_text(article)
    journal = (
        _find_text(article, ".//Journal/Title")
        or _find_text(article, ".//MedlineJournalInfo/MedlineTA")
        or "PubMed"
    )
    publication_date = _format_pubdate(article)
    authors = tuple(_author_name(author) for author in article.findall(".//Author"))
    publication_types = tuple(
        element.text.strip()
        for element in article.findall(".//PublicationType")
        if element.text
    )
    language = _find_text(article, ".//Language")
    correction_links = tuple(
        link
        for link in (
            _comments_link(article, "CorrectionIn"),
            _comments_link(article, "CorrectionOf"),
        )
        if link
    )
    retraction_links = tuple(
        link
        for link in (
            _comments_link(article, "RetractionIn"),
            _comments_link(article, "RetractionOf"),
        )
        if link
    )
    doi = _find_article_id(article, "doi")
    publication_status = (_find_text(article, ".//PublicationStatus") or "").lower()
    pubtypes_lower = {value.lower() for value in publication_types}
    is_retracted = (
        publication_status == "retracted"
        or "retracted publication" in pubtypes_lower
        or bool(retraction_links)
    )
    source_timestamp = datetime.now(timezone.utc).isoformat()
    normalized_payload = {
        "schema_version": NORMALIZATION_SCHEMA_VERSION,
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "publication_date": publication_date,
        "authors": authors,
        "publication_types": publication_types,
        "language": language,
        "correction_links": correction_links,
        "retraction_links": retraction_links,
        "is_retracted": is_retracted,
        "source_timestamp": source_timestamp,
        "metadata_only": True,
    }
    return PubMedRecord(
        pmid=pmid,
        doi=doi,
        title=title,
        abstract=abstract,
        journal=journal,
        publication_date=publication_date,
        authors=authors,
        publication_types=publication_types,
        language=language,
        correction_links=correction_links,
        retraction_links=retraction_links,
        is_retracted=is_retracted,
        raw_response_hash=_body_hash(raw_body),
        normalized_record_hash=stable_hash(normalized_payload),
        source_timestamp=source_timestamp,
        metadata_only=True,
    )


def _record_from_summary_dict(item: dict[str, Any], *, raw_body: bytes) -> PubMedRecord:
    pmid = str(item.get("uid", item.get("pmid", "")))
    title = str(item.get("title", f"PubMed record {pmid}"))
    abstract = str(item.get("abstract", ""))
    journal = str(item.get("source", item.get("journal", "PubMed")))
    publication_date = str(item.get("pubdate", item.get("epubdate", "")))
    authors = tuple(str(author) for author in item.get("authors", ()))
    publication_types = tuple(str(value) for value in item.get("pubtype", ()))
    language = str(item.get("lang", "")) or None
    doi = str(item.get("elocationid", "")).removeprefix("doi: ") or None
    pubtypes_lower = {value.lower() for value in publication_types}
    is_retracted = "retracted publication" in pubtypes_lower
    source_timestamp = datetime.now(timezone.utc).isoformat()
    normalized_payload = {
        "schema_version": NORMALIZATION_SCHEMA_VERSION,
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "publication_date": publication_date,
        "authors": authors,
        "publication_types": publication_types,
        "language": language,
        "correction_links": (),
        "retraction_links": (),
        "is_retracted": is_retracted,
        "source_timestamp": source_timestamp,
        "metadata_only": True,
    }
    return PubMedRecord(
        pmid=pmid,
        doi=doi,
        title=title,
        abstract=abstract,
        journal=journal,
        publication_date=publication_date,
        authors=authors,
        publication_types=publication_types,
        language=language,
        correction_links=(),
        retraction_links=(),
        is_retracted=is_retracted,
        raw_response_hash=_body_hash(raw_body),
        normalized_record_hash=stable_hash(normalized_payload),
        source_timestamp=source_timestamp,
        metadata_only=True,
    )


def _record_from_article_dict(article: dict[str, Any], *, raw_body: bytes) -> PubMedRecord:
    return _record_from_summary_dict(article, raw_body=raw_body)


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _find_text(element: ET.Element, path: str) -> str | None:
    match = element.find(path)
    if match is None or match.text is None:
        return None
    return match.text.strip()


def _find_article_id(article: ET.Element, id_type: str) -> str | None:
    for article_id in article.findall(".//ArticleId"):
        if article_id.attrib.get("IdType") == id_type and article_id.text:
            return article_id.text.strip()
    return None


def _join_abstract_text(article: ET.Element) -> str:
    parts = []
    for element in article.findall(".//AbstractText"):
        label = element.attrib.get("Label")
        text = "".join(element.itertext()).strip()
        if not text:
            continue
        parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts)


def _author_name(author: ET.Element) -> str:
    last = _find_text(author, "LastName") or ""
    fore = _find_text(author, "ForeName") or ""
    collective = _find_text(author, "CollectiveName") or ""
    if collective:
        return collective
    return f"{fore} {last}".strip()


def _format_pubdate(article: ET.Element) -> str:
    pubdate = article.find(".//PubDate")
    if pubdate is None:
        return ""
    year = _find_text(pubdate, "Year") or ""
    month = _find_text(pubdate, "Month") or ""
    day = _find_text(pubdate, "Day") or ""
    medline = _find_text(pubdate, "MedlineDate") or ""
    if medline:
        return medline
    parts = [part for part in (year, month, day) if part]
    return " ".join(parts)


def _comments_link(article: ET.Element, ref_type: str) -> str | None:
    for comments in article.findall(".//CommentsCorrections"):
        if comments.attrib.get("RefType") == ref_type:
            pmid = _find_text(comments, "PMID")
            if pmid:
                return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return None


def _year_from_date(publication_date: str) -> int:
    for token in publication_date.replace("-", " ").split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return 0


def _study_design_from_publication_types(publication_types: tuple[str, ...]) -> Any:
    from src.vyu.contracts import StudyDesign

    lowered = {value.lower() for value in publication_types}
    if "randomized controlled trial" in lowered:
        return StudyDesign.RANDOMIZED_CONTROLLED_TRIAL
    if "systematic review" in lowered:
        return StudyDesign.SYSTEMATIC_REVIEW
    if "meta-analysis" in lowered:
        return StudyDesign.META_ANALYSIS
    if "guideline" in lowered:
        return StudyDesign.GUIDELINE
    return StudyDesign.UNKNOWN


def search_params(request: PubMedSearchRequest) -> dict[str, object]:
    params: dict[str, object] = {
        "mode": "search",
        "db": "pubmed",
        "term": request.query,
        "retmax": request.limit,
        "sort": request.sort,
    }
    if request.page_token:
        params["retstart"] = int(request.page_token)
    if request.date_from:
        params["mindate"] = request.date_from
    if request.date_to:
        params["maxdate"] = request.date_to
        params["datetype"] = "pdat"
    return params
