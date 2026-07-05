from __future__ import annotations

from typing import Any, Callable

from src.vyu.connectors.audit import JsonlAuditSink
from src.vyu.connectors.contracts import (
    ConnectorAuditEvent,
    ConnectorResult,
    SearchRequest,
)
from src.vyu.contracts import DocumentRecord, PassageRecord, StudyDesign

Transport = Callable[[str, dict[str, object]], dict[str, Any]]


class PubMedConnector:
    source = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, transport: Transport, audit_sink: JsonlAuditSink | None = None):
        self.transport = transport
        self.audit_sink = audit_sink

    def search(self, request: SearchRequest) -> ConnectorResult:
        search_payload = self.transport(
            f"{self.base_url}/esearch.fcgi",
            {
                "mode": "search",
                "db": "pubmed",
                "term": request.query,
                "retmax": request.limit,
            },
        )
        ids = [str(identifier) for identifier in search_payload.get("ids", [])]
        summary_payload = self.transport(
            f"{self.base_url}/esummary.fcgi",
            {
                "mode": "summary",
                "db": "pubmed",
                "ids": ",".join(ids),
            },
        )
        documents = [_document_from_summary(item) for item in summary_payload.get("documents", [])]
        passages = [_passage_from_document(document) for document in documents]
        self._audit("search", request.query, [document.document_id for document in documents], "ok")
        return ConnectorResult(
            source=self.source,
            request=request,
            documents=documents,
            passages=passages,
        )

    def fetch(self, document_id: str) -> DocumentRecord:
        pubmed_id = document_id.removeprefix("PUBMED-")
        summary_payload = self.transport(
            f"{self.base_url}/esummary.fcgi",
            {
                "mode": "summary",
                "db": "pubmed",
                "ids": pubmed_id,
            },
        )
        documents = [_document_from_summary(item) for item in summary_payload.get("documents", [])]
        if not documents:
            self._audit("fetch", None, [document_id], "not_found")
            raise KeyError(f"Unknown PubMed document: {document_id}")
        self._audit("fetch", None, [documents[0].document_id], "ok")
        return documents[0]

    def _audit(
        self, action: str, query: str | None, document_ids: list[str], status: str
    ) -> None:
        if self.audit_sink is None:
            return
        self.audit_sink.append(
            ConnectorAuditEvent(
                source=self.source,
                action=action,
                query=query,
                document_ids=document_ids,
                status=status,
            )
        )


def _document_from_summary(item: dict[str, Any]) -> DocumentRecord:
    uid = str(item["uid"])
    year = _year_from_pubdate(str(item.get("pubdate", "")))
    return DocumentRecord(
        document_id=f"PUBMED-{uid}",
        title=str(item.get("title", f"PubMed record {uid}")),
        year=year,
        study_design=StudyDesign.UNKNOWN,
        source_type="pubmed",
        publication_status="peer_reviewed",
        abstract=str(item.get("abstract", "")),
        journal=str(item.get("source", "PubMed")),
        pmid=uid,
    )


def _passage_from_document(document: DocumentRecord) -> PassageRecord:
    text = document.abstract or f"PubMed summary record for {document.title}."
    return PassageRecord(
        passage_id=f"{document.document_id}-SUMMARY",
        document_id=document.document_id,
        section="summary",
        text=text,
    )


def _year_from_pubdate(pubdate: str) -> int:
    for token in pubdate.split():
        if token.isdigit() and len(token) == 4:
            return int(token)
    return 0
