from __future__ import annotations

from src.vyu.connectors.audit import JsonlAuditSink
from src.vyu.connectors.contracts import (
    ConnectorAuditEvent,
    ConnectorResult,
    SearchRequest,
)
from src.vyu.contracts import DocumentRecord, LoadedCorpus, PassageRecord


class DummyConnector:
    source = "dummy"

    def __init__(self, corpus: LoadedCorpus, audit_sink: JsonlAuditSink | None = None):
        self.corpus = corpus
        self.audit_sink = audit_sink

    def search(self, request: SearchRequest) -> ConnectorResult:
        documents = self.corpus.find_documents(request.query)[: request.limit]
        document_ids = {document.document_id for document in documents}
        passages = [
            passage
            for passage in self.corpus.passages.values()
            if passage.document_id in document_ids
        ]
        result = ConnectorResult(
            source=self.source,
            request=request,
            documents=documents,
            passages=passages,
        )
        self._audit("search", request.query, [document.document_id for document in documents], "ok")
        return result

    def fetch(self, document_id: str) -> DocumentRecord:
        try:
            document = self.corpus.documents[document_id]
        except KeyError as exc:
            self._audit("fetch", None, [document_id], "not_found")
            raise KeyError(f"Unknown dummy document: {document_id}") from exc
        self._audit("fetch", None, [document_id], "ok")
        return document

    def fetch_passages(self, document_id: str) -> list[PassageRecord]:
        return [
            passage
            for passage in self.corpus.passages.values()
            if passage.document_id == document_id
        ]

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
