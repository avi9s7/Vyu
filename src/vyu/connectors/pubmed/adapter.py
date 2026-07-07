from __future__ import annotations

from typing import Any, Callable

from src.vyu.connectors.audit import JsonlAuditSink
from src.vyu.connectors.contracts import (
    ConnectorAuditEvent,
    ConnectorResult,
    SearchRequest,
)
from src.vyu.connectors.pubmed.contracts import (
    PubMedRecord,
    PubMedSearchRequest,
    RetractionPolicy,
)
from src.vyu.connectors.pubmed.normalization import (
    FETCH_BATCH_SIZE,
    NORMALIZATION_SCHEMA_VERSION,
    normalize_fetch_payload,
    normalize_search_payload,
    pubmed_record_to_document_fields,
    search_params,
)
from src.vyu.contracts import DocumentRecord, PassageRecord


Transport = Callable[[str, dict[str, object]], dict[str, Any]]


class PubMedRetractionBlockedError(ValueError):
    """Raised when a retracted PubMed record cannot be used under the active policy."""


class ProductionPubMedConnector:
    """Production PubMed connector using metadata-only search and bounded fetch batches."""

    source = "pubmed"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(
        self,
        transport: Transport,
        *,
        retraction_policy: RetractionPolicy = RetractionPolicy.BLOCK,
        audit_sink: JsonlAuditSink | None = None,
    ):
        self.transport = transport
        self.retraction_policy = retraction_policy
        self.audit_sink = audit_sink

    def search(self, request: SearchRequest) -> ConnectorResult:
        pubmed_request = PubMedSearchRequest.from_connector_request(request)
        search_payload = self.transport(
            f"{self.base_url}/esearch.fcgi",
            search_params(pubmed_request),
        )
        search_page = normalize_search_payload(
            search_payload,
            raw_body=_payload_bytes(search_payload),
        )
        records = self.fetch_records(list(search_page.ids))
        documents = [self._document_from_record(record) for record in records]
        passages = [self._passage_from_record(record) for record in records]
        self._audit(
            "search",
            request.query,
            [document.document_id for document in documents],
            "ok",
            message=(
                f"schema={NORMALIZATION_SCHEMA_VERSION};next_page={search_page.next_page_token};"
                f"total={search_page.total_count}"
            ),
        )
        return ConnectorResult(
            source=self.source,
            request=request,
            documents=documents,
            passages=passages,
        )

    def fetch(self, document_id: str) -> DocumentRecord:
        pmid = document_id.removeprefix("PUBMED-")
        records = self.fetch_records([pmid], strict=True)
        if not records:
            self._audit("fetch", None, [document_id], "not_found")
            raise KeyError(f"Unknown PubMed document: {document_id}")
        record = records[0]
        self._audit("fetch", None, [record.document_id], "ok")
        return self._document_from_record(record)

    def fetch_records(self, pmids: list[str], *, strict: bool = False) -> list[PubMedRecord]:
        if not pmids:
            return []
        records: list[PubMedRecord] = []
        for start in range(0, len(pmids), FETCH_BATCH_SIZE):
            batch = pmids[start : start + FETCH_BATCH_SIZE]
            payload, raw_body = self._fetch_batch(batch)
            batch_records = normalize_fetch_payload(payload, raw_body=raw_body)
            for record in batch_records:
                if self._should_include_record(record, strict=strict):
                    records.append(record)
        return records

    def _should_include_record(self, record: PubMedRecord, *, strict: bool) -> bool:
        if not record.is_retracted:
            return True
        if self.retraction_policy == RetractionPolicy.ALLOW:
            return True
        if self.retraction_policy == RetractionPolicy.WARN:
            self._audit(
                "retraction_warning",
                None,
                [record.document_id],
                "warn",
                message="retracted_record_included",
            )
            return True
        self._audit(
            "retraction_blocked",
            None,
            [record.document_id],
            "blocked",
            message="retracted_record_excluded",
        )
        if strict:
            raise PubMedRetractionBlockedError(
                f"PubMed record {record.document_id} is retracted and blocked by policy."
            )
        return False

    def _fetch_batch(self, pmids: list[str]) -> tuple[dict[str, Any], bytes]:
        params = {"mode": "fetch", "db": "pubmed", "ids": ",".join(pmids)}
        try:
            payload = self.transport(f"{self.base_url}/efetch.fcgi", params)
            return payload, _payload_bytes(payload)
        except KeyError:
            summary_payload = self.transport(
                f"{self.base_url}/esummary.fcgi",
                {"mode": "summary", "db": "pubmed", "ids": ",".join(pmids)},
            )
            return summary_payload, _payload_bytes(summary_payload)

    def _document_from_record(self, record: PubMedRecord) -> DocumentRecord:
        from src.vyu.contracts import DocumentRecord

        return DocumentRecord(**pubmed_record_to_document_fields(record))

    def _passage_from_record(self, record: PubMedRecord) -> PassageRecord:
        text = record.abstract or f"PubMed metadata record for {record.title}."
        return PassageRecord(
            passage_id=f"{record.document_id}-ABSTRACT",
            document_id=record.document_id,
            section="abstract",
            text=text,
        )

    def _audit(
        self,
        action: str,
        query: str | None,
        document_ids: list[str],
        status: str,
        *,
        message: str = "",
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
                message=message,
            )
        )


def _payload_bytes(payload: dict[str, Any]) -> bytes:
    import json

    if "xml" in payload:
        return str(payload["xml"]).encode("utf-8")
    return json.dumps(payload, sort_keys=True).encode("utf-8")
