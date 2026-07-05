from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Protocol

from src.vyu.authz import AuthorizationPolicy, Principal, Role, WorkspaceMembership
from src.vyu.entrypoints.report_export import (
    ReportExportApiRequest,
    ReportExportApiResponse,
    ReportExportPayload,
    handle_report_export_api,
)
from src.vyu.generation import AnswerClaim, EvidenceContext, EvidenceItem, GroundedAnswer
from src.vyu.governance import GovernanceBox, TrustScore
from src.vyu.reports import ReportType
from src.vyu.review import ReviewTask
from src.vyu.storage import ProductionStorage


@dataclass(frozen=True)
class ReportExportRouteRequest:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    json_body: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportExportRouteResponse:
    status_code: int
    body: dict[str, object]


@dataclass(frozen=True)
class ReportExportArtifacts:
    answer: GroundedAnswer
    context: EvidenceContext
    trust_score: TrustScore
    governance_box: GovernanceBox


class ReportExportArtifactStore(Protocol):
    def load(self, review_task: ReviewTask) -> ReportExportArtifacts:
        ...


class PhaseOutputReportArtifactStore:
    """Load report-export artifacts from the local phase-output layout."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def load(self, review_task: ReviewTask) -> ReportExportArtifacts:
        del review_task  # The persisted phase-output directory currently holds one run.
        answer = _load_answer(self.output_dir / "phase4" / "grounded_answer.json")
        context = _load_context(self.output_dir / "phase4" / "evidence_context.json")
        governance_payload = _read_json(
            self.output_dir / "phase5" / "governance_audit_record.json"
        )
        trust_score = _load_trust_score(dict(governance_payload["trust_score"]))
        governance_box = _load_governance_box(
            dict(governance_payload["governance_box"]),
            trust_score,
        )
        return ReportExportArtifacts(
            answer=answer,
            context=context,
            trust_score=trust_score,
            governance_box=governance_box,
        )


class ReportExportRouteRuntime:
    def __init__(
        self,
        storage: ProductionStorage,
        artifact_store: ReportExportArtifactStore,
        policy: AuthorizationPolicy | None = None,
        audit_event_id_factory: Callable[[str, str], str] | None = None,
        audit_created_at: str | None = None,
    ) -> None:
        self.storage = storage
        self.artifact_store = artifact_store
        self.policy = policy
        self.audit_event_id_factory = audit_event_id_factory
        self.audit_created_at = audit_created_at

    def handle(self, request: ReportExportRouteRequest) -> ReportExportRouteResponse:
        method = request.method.upper()
        try:
            if method == "POST" and request.path == "/v1/report-exports":
                return _from_api_response(self._handle_export(request))
        except (KeyError, TypeError, ValueError) as exc:
            return ReportExportRouteResponse(
                status_code=400,
                body={
                    "reason": "route_bad_request",
                    "detail": str(exc),
                    "method": method,
                    "path": request.path,
                },
            )
        return ReportExportRouteResponse(
            status_code=404,
            body={
                "reason": "route_not_found",
                "method": method,
                "path": request.path,
            },
        )

    def _handle_export(
        self,
        request: ReportExportRouteRequest,
    ) -> ReportExportApiResponse:
        review_id = str(request.json_body["review_id"])
        review_task = self.storage.get_review_task(review_id)
        artifacts = self.artifact_store.load(review_task)
        return handle_report_export_api(
            ReportExportApiRequest(
                request_id=_request_id(request),
                payload=ReportExportPayload(
                    principal=_principal_from_headers(request.headers),
                    report_type=ReportType(str(request.json_body["report_type"])),
                    answer=artifacts.answer,
                    context=artifacts.context,
                    trust_score=artifacts.trust_score,
                    governance_box=artifacts.governance_box,
                    review_task=review_task,
                ),
            ),
            storage=self.storage,
            policy=self.policy,
            audit_event_id_factory=self.audit_event_id_factory,
            audit_created_at=self.audit_created_at,
        )


def _from_api_response(response: ReportExportApiResponse) -> ReportExportRouteResponse:
    return ReportExportRouteResponse(
        status_code=response.status_code,
        body=response.body,
    )


def _principal_from_headers(headers: dict[str, str]) -> Principal:
    return Principal(
        user_id=str(headers["x-vyu-user-id"]),
        memberships=(
            WorkspaceMembership(
                tenant_id=str(headers["x-vyu-tenant-id"]),
                workspace_id=str(headers["x-vyu-workspace-id"]),
                roles=(Role(str(headers["x-vyu-role"])),),
            ),
        ),
    )


def _request_id(request: ReportExportRouteRequest) -> str:
    return request.headers.get("x-vyu-request-id", "report-export-route")


def _load_answer(path: Path) -> GroundedAnswer:
    payload = _read_json(path)
    return GroundedAnswer(
        question=str(payload["question"]),
        answer_text=str(payload["answer_text"]),
        claims=tuple(
            AnswerClaim(
                claim_id=str(claim["claim_id"]),
                text=str(claim["text"]),
                citation_ids=tuple(str(citation_id) for citation_id in claim["citation_ids"]),
                material=bool(claim.get("material", True)),
            )
            for claim in payload["claims"]
        ),
        abstained=bool(payload["abstained"]),
        abstention_reason=(
            str(payload["abstention_reason"])
            if payload.get("abstention_reason") is not None
            else None
        ),
    )


def _load_context(path: Path) -> EvidenceContext:
    payload = _read_json(path)
    return EvidenceContext(
        question=str(payload["question"]),
        items=tuple(
            EvidenceItem(
                citation_id=str(item["citation_id"]),
                document_id=str(item["document_id"]),
                passage_id=str(item["passage_id"]),
                title=str(item["title"]),
                passage_text=str(item["passage_text"]),
                retrieval_score=float(item["retrieval_score"]),
                retrieval_source=str(item["retrieval_source"]),
                is_retracted=bool(item["is_retracted"]),
                is_preprint=bool(item["is_preprint"]),
            )
            for item in payload["items"]
        ),
    )


def _load_trust_score(payload: dict[str, object]) -> TrustScore:
    return TrustScore(
        overall=int(payload["overall"]),
        components={key: int(value) for key, value in dict(payload["components"]).items()},
        warnings=tuple(str(warning) for warning in payload["warnings"]),
    )


def _load_governance_box(payload: dict[str, object], trust_score: TrustScore) -> GovernanceBox:
    return GovernanceBox(
        question=str(payload["question"]),
        sources_searched=tuple(str(source) for source in payload["sources_searched"]),
        search_run_at=str(payload["search_run_at"]),
        retrieved_count=int(payload["retrieved_count"]),
        included_count=int(payload["included_count"]),
        excluded_count=int(payload["excluded_count"]),
        evidence_mix={key: int(value) for key, value in dict(payload["evidence_mix"]).items()},
        conflicts=tuple(str(conflict) for conflict in payload["conflicts"]),
        models={key: str(value) for key, value in dict(payload["models"]).items()},
        policy_versions={
            key: str(value) for key, value in dict(payload["policy_versions"]).items()
        },
        human_review_required=bool(payload["human_review_required"]),
        human_review_reason=str(payload["human_review_reason"]),
        trust_score=trust_score,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
