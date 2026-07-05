from __future__ import annotations

from src.vyu.connectors.audit import JsonlAuditSink
from src.vyu.connectors.contracts import ConnectorAuditEvent, ConnectorResult, SearchRequest
from src.vyu.contracts import DocumentRecord, PassageRecord


class StaticSearchConnector:
    """Deterministic connector shell for governed non-network source integrations.

    This class is used for production-shaped connector boundaries that are not yet
    allowed to call live external systems. It lets Vyu test source approval,
    research-tool registration, query planning, result normalization, audit, and
    replay without copying upstream connector code or making network requests.
    """

    source: str

    def __init__(
        self,
        source: str,
        documents: list[DocumentRecord] | None = None,
        passages: list[PassageRecord] | None = None,
        audit_sink: JsonlAuditSink | None = None,
    ):
        self.source = source
        self.documents = tuple(documents or ())
        self.passages = tuple(passages or ())
        self.audit_sink = audit_sink

    def search(self, request: SearchRequest) -> ConnectorResult:
        matched_documents = self._match_documents(request.query)[: request.limit]
        matched_document_ids = {document.document_id for document in matched_documents}
        matched_passages = [
            passage
            for passage in self.passages
            if passage.document_id in matched_document_ids
        ]
        self._audit(
            action="search",
            query=request.query,
            document_ids=[document.document_id for document in matched_documents],
            status="ok",
        )
        return ConnectorResult(
            source=self.source,
            request=request,
            documents=list(matched_documents),
            passages=matched_passages,
        )

    def fetch(self, document_id: str) -> DocumentRecord:
        for document in self.documents:
            if document.document_id == document_id:
                self._audit("fetch", None, [document_id], "ok")
                return document
        self._audit("fetch", None, [document_id], "not_found")
        raise KeyError(f"Unknown {self.source} document: {document_id}")

    def _match_documents(self, query: str) -> list[DocumentRecord]:
        terms = [term.casefold().strip('"') for term in query.split() if term.strip('"')]
        if not terms:
            return []
        matches: list[DocumentRecord] = []
        for document in self.documents:
            haystack = " ".join(
                [
                    document.document_id,
                    document.title,
                    document.abstract,
                    document.journal,
                    document.publication_status,
                ]
            ).casefold()
            if any(term in haystack for term in terms):
                matches.append(document)
        return matches

    def _audit(
        self,
        action: str,
        query: str | None,
        document_ids: list[str],
        status: str,
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


class SemanticScholarConnector(StaticSearchConnector):
    def __init__(
        self,
        documents: list[DocumentRecord] | None = None,
        passages: list[PassageRecord] | None = None,
        audit_sink: JsonlAuditSink | None = None,
    ):
        super().__init__(
            source="semantic_scholar",
            documents=documents,
            passages=passages,
            audit_sink=audit_sink,
        )


class ClinicalTrialsConnector(StaticSearchConnector):
    def __init__(
        self,
        documents: list[DocumentRecord] | None = None,
        passages: list[PassageRecord] | None = None,
        audit_sink: JsonlAuditSink | None = None,
    ):
        super().__init__(
            source="clinical_trials",
            documents=documents,
            passages=passages,
            audit_sink=audit_sink,
        )


class GuidelineSourceConnector(StaticSearchConnector):
    def __init__(
        self,
        documents: list[DocumentRecord] | None = None,
        passages: list[PassageRecord] | None = None,
        audit_sink: JsonlAuditSink | None = None,
    ):
        super().__init__(
            source="guidelines",
            documents=documents,
            passages=passages,
            audit_sink=audit_sink,
        )


class InternalDocumentConnector(StaticSearchConnector):
    def __init__(
        self,
        documents: list[DocumentRecord] | None = None,
        passages: list[PassageRecord] | None = None,
        audit_sink: JsonlAuditSink | None = None,
    ):
        super().__init__(
            source="internal_documents",
            documents=documents,
            passages=passages,
            audit_sink=audit_sink,
        )
