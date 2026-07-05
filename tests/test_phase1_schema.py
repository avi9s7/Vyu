import sqlite3
import unittest

from src.vyu.storage import load_schema_sql


class Phase1SchemaTests(unittest.TestCase):
    def test_schema_creates_core_phase1_tables(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(load_schema_sql())
            tables = {
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type = 'table'"
                )
            }
        finally:
            connection.close()

        self.assertIn("documents", tables)
        self.assertIn("passages", tables)
        self.assertIn("evidence_profiles", tables)
        self.assertIn("golden_questions", tables)
        self.assertIn("audit_events", tables)


if __name__ == "__main__":
    unittest.main()
