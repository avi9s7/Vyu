from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.vyu.policy.models import (
    ResearchToolPolicyRecord,
    ResearchToolPolicyVersion,
    SourcePolicyRecord,
    SourcePolicyVersion,
)
from src.vyu.research_mcp.contracts import ResearchToolDefinition
from src.vyu.sources import ProductionSourceRecord


def canonical_policy_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_approval_status(record: ProductionSourceRecord) -> str:
    return "approved" if record.approved else "draft"


def _tool_approval_status(record: ResearchToolDefinition) -> str:
    return "approved" if record.approved else "draft"


@dataclass(frozen=True)
class PolicyActivationResult:
    source_policy_version_id: UUID
    research_tool_policy_version_id: UUID
    source_count: int
    tool_count: int
    source_policy_hash: str
    tool_policy_hash: str


class PolicyRepository:
    def get_active_source_policy_version(self, session: Session) -> SourcePolicyVersion | None:
        row = session.scalar(
            select(SourcePolicyVersion)
            .where(SourcePolicyVersion.status == "active")
            .order_by(SourcePolicyVersion.version_number.desc())
            .limit(1)
        )
        return row if isinstance(row, SourcePolicyVersion) else None

    def get_active_research_tool_policy_version(
        self, session: Session
    ) -> ResearchToolPolicyVersion | None:
        row = session.scalar(
            select(ResearchToolPolicyVersion)
            .where(ResearchToolPolicyVersion.status == "active")
            .order_by(ResearchToolPolicyVersion.version_number.desc())
            .limit(1)
        )
        return row if isinstance(row, ResearchToolPolicyVersion) else None

    def list_sources_for_version(
        self,
        session: Session,
        policy_version_id: UUID,
    ) -> list[SourcePolicyRecord]:
        return list(
            session.scalars(
                select(SourcePolicyRecord).where(
                    SourcePolicyRecord.policy_version_id == policy_version_id
                )
            ).all()
        )

    def list_tools_for_version(
        self,
        session: Session,
        policy_version_id: UUID,
    ) -> list[ResearchToolPolicyRecord]:
        return list(
            session.scalars(
                select(ResearchToolPolicyRecord).where(
                    ResearchToolPolicyRecord.policy_version_id == policy_version_id
                )
            ).all()
        )

    def activate_policies(
        self,
        session: Session,
        *,
        sources: list[ProductionSourceRecord],
        tools: list[ResearchToolDefinition],
        actor_id: str,
    ) -> PolicyActivationResult:
        source_payload = {"sources": [source.to_json() for source in sources]}
        tool_payload = {"tools": [tool.to_json() for tool in tools]}
        source_hash = canonical_policy_hash(source_payload)
        tool_hash = canonical_policy_hash(tool_payload)

        next_source_version = int(session.scalar(select(func.max(SourcePolicyVersion.version_number))) or 0) + 1
        next_tool_version = int(
            session.scalar(select(func.max(ResearchToolPolicyVersion.version_number))) or 0
        ) + 1
        now = datetime.now(tz=UTC)

        session.execute(
            update(SourcePolicyVersion)
            .where(SourcePolicyVersion.status == "active")
            .values(status="retired")
        )
        session.execute(
            update(ResearchToolPolicyVersion)
            .where(ResearchToolPolicyVersion.status == "active")
            .values(status="retired")
        )

        source_version = SourcePolicyVersion(
            id=uuid4(),
            version_number=next_source_version,
            policy_hash=source_hash,
            status="active",
            activated_at=now,
            activated_by=actor_id,
        )
        tool_version = ResearchToolPolicyVersion(
            id=uuid4(),
            version_number=next_tool_version,
            policy_hash=tool_hash,
            status="active",
            activated_at=now,
            activated_by=actor_id,
        )
        session.add(source_version)
        session.add(tool_version)
        session.flush()

        for source in sources:
            session.add(
                SourcePolicyRecord(
                    id=uuid4(),
                    policy_version_id=source_version.id,
                    source_id=source.source_id,
                    record_json=source.to_json(),
                    approval_status=_source_approval_status(source),
                )
            )
        for tool in tools:
            session.add(
                ResearchToolPolicyRecord(
                    id=uuid4(),
                    policy_version_id=tool_version.id,
                    tool_id=tool.tool_id,
                    source_id=tool.source_id,
                    record_json=tool.to_json(),
                    approval_status=_tool_approval_status(tool),
                )
            )
        session.flush()
        return PolicyActivationResult(
            source_policy_version_id=source_version.id,
            research_tool_policy_version_id=tool_version.id,
            source_count=len(sources),
            tool_count=len(tools),
            source_policy_hash=source_hash,
            tool_policy_hash=tool_hash,
        )

    def quarantine_source(
        self,
        session: Session,
        *,
        source_id: str,
        actor_id: str,
        reason: str,
    ) -> SourcePolicyRecord | None:
        version = self.get_active_source_policy_version(session)
        if version is None:
            return None
        row = session.scalar(
            select(SourcePolicyRecord).where(
                SourcePolicyRecord.policy_version_id == version.id,
                SourcePolicyRecord.source_id == source_id,
            )
        )
        if row is None:
            return None
        row.approval_status = "quarantined"
        row.quarantined_at = datetime.now(tz=UTC)
        row.quarantined_by = actor_id
        row.quarantined_reason = reason
        session.flush()
        return row

    def quarantine_tool(
        self,
        session: Session,
        *,
        tool_id: str,
        actor_id: str,
        reason: str,
    ) -> ResearchToolPolicyRecord | None:
        version = self.get_active_research_tool_policy_version(session)
        if version is None:
            return None
        row = session.scalar(
            select(ResearchToolPolicyRecord).where(
                ResearchToolPolicyRecord.policy_version_id == version.id,
                ResearchToolPolicyRecord.tool_id == tool_id,
            )
        )
        if row is None:
            return None
        row.approval_status = "quarantined"
        row.quarantined_at = datetime.now(tz=UTC)
        row.quarantined_by = actor_id
        row.quarantined_reason = reason
        session.flush()
        return row
