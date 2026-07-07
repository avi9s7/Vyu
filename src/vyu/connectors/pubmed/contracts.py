from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RetractionPolicy(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    ALLOW = "allow"


@dataclass(frozen=True)
class PubMedSearchRequest:
    query: str
    limit: int = 10
    date_from: str | None = None
    date_to: str | None = None
    page_token: str | None = None
    sort: str = "relevance"
    filters: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_connector_request(cls, request: object) -> PubMedSearchRequest:
        from src.vyu.connectors.contracts import SearchRequest

        if not isinstance(request, SearchRequest):
            raise TypeError("Expected SearchRequest.")
        return cls(
            query=request.query,
            limit=request.limit,
            date_from=request.filters.get("date_from"),
            date_to=request.filters.get("date_to"),
            page_token=request.filters.get("page_token"),
            sort=request.filters.get("sort", "relevance"),
            filters=dict(request.filters),
        )


@dataclass(frozen=True)
class PubMedSearchPage:
    ids: tuple[str, ...]
    next_page_token: str | None
    total_count: int
    raw_response_hash: str


@dataclass(frozen=True)
class PubMedRecord:
    pmid: str
    doi: str | None
    title: str
    abstract: str
    journal: str
    publication_date: str
    authors: tuple[str, ...]
    publication_types: tuple[str, ...]
    language: str | None
    correction_links: tuple[str, ...]
    retraction_links: tuple[str, ...]
    is_retracted: bool
    raw_response_hash: str
    normalized_record_hash: str
    source_timestamp: str
    metadata_only: bool = True

    @property
    def document_id(self) -> str:
        return f"PUBMED-{self.pmid}"
