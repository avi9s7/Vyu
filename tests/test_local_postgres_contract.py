from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocalPostgresContractTests(unittest.TestCase):
    def test_compose_pins_postgres_and_declares_healthcheck(self) -> None:
        text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("pgvector/pgvector:0.8.0-pg17", text)
        self.assertIn("pg_isready", text)
        self.assertIn("vyu-postgres-data", text)

    def test_example_uses_postgresql_not_sqlite(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("VYU_DATABASE_URL=postgresql+psycopg://", text)
        self.assertNotIn("sqlite", text.lower())


if __name__ == "__main__":
    unittest.main()
