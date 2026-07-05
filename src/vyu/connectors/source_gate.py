from __future__ import annotations

from typing import Any, Callable

from src.vyu.sources import SourceRegistry


Transport = Callable[[str, dict[str, object]], dict[str, Any]]


class SourceApprovalTransport:
    def __init__(
        self,
        source_id: str,
        intended_use: str,
        registry: SourceRegistry,
        transport: Transport,
    ):
        self.source_id = source_id
        self.intended_use = intended_use
        self.registry = registry
        self.transport = transport

    def __call__(self, url: str, params: dict[str, object]) -> dict[str, Any]:
        self.registry.require_approved(self.source_id, intended_use=self.intended_use)
        return self.transport(url, params)
