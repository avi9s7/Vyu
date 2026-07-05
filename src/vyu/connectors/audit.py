from __future__ import annotations

import json
from pathlib import Path

from src.vyu.connectors.contracts import ConnectorAuditEvent


class JsonlAuditSink:
    def __init__(self, path: Path):
        self.path = path

    def append(self, event: ConnectorAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_json(), sort_keys=True) + "\n")

    def read_events(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
